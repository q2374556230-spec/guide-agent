# -*- coding: utf-8 -*-
"""Agent 的工具层:把微服务的 HTTP 接口包装成"工具",并给出工具契约(schema)。
工具契约 = 服务契约的"面向模型版本":描述写得越清楚,模型调用越准。"""
import os, json, re, urllib.parse, urllib.request
try:
    import requests
except ModuleNotFoundError:
    requests = None
from rag import retrieve
from data import ORDERS, PRODUCTS, PRODUCTS_EXT

POLICY_K = max(int(os.getenv("POLICY_K", "3")), 3)   # 检索条数,至少召回3条以覆盖退/换货政策

# 服务地址用环境变量配置:本地默认 localhost;容器/K8s 中用服务名(如 http://order-service:8001);
# 对接学生现有系统时,直接把这三个变量指向他们已有的微服务即可,无需改其它代码。
ORDER = os.getenv("ORDER_URL", "http://localhost:8001")
PRODUCT = os.getenv("PRODUCT_URL", "http://localhost:8002")
LOGISTICS = os.getenv("LOGISTICS_URL", "http://localhost:8003")

# ---- 工具实现:每个工具调用一个微服务 ----
def query_order(order_id: str) -> dict:
    try:
        return _http_get_json(f"{ORDER}/orders/{order_id}")
    except Exception as e:
        return ORDERS.get(order_id, {"error": f"订单服务不可用: {e}"})

def track_logistics(order_id: str) -> dict:
    try:
        return _http_get_json(f"{LOGISTICS}/track/{order_id}")
    except Exception as e:
        o = ORDERS.get(order_id)
        if not o:
            return {"error": f"物流服务不可用: {e}"}
        timed_out = o.get("type") == "外卖" and o.get("placed_min_ago", 0) > 30 \
                    and o.get("status") == "配送中"
        return {"order_id": order_id, "status": o.get("status"), "eta": o.get("eta"),
                "tracking": o.get("tracking"), "carrier": o.get("carrier"),
                "timed_out": timed_out}

def query_product(name: str) -> dict:
    try:
        return _http_get_json(f"{PRODUCT}/products/{urllib.parse.quote(name)}")
    except Exception as e:
        return PRODUCTS.get(name, {"error": f"商品服务不可用: {e}"})

def search_products(q: str, max_price=None) -> list:
    try:
        params = {"q": q}
        if max_price is not None:
            params["max_price"] = max_price
        return _http_get_json(f"{PRODUCT}/products/search", params=params)
    except Exception:
        return _local_search_products(q, max_price)

def get_product_detail(product_id: str) -> dict:
    try:
        return _http_get_json(f"{PRODUCT}/products/detail/{urllib.parse.quote(product_id)}")
    except Exception:
        return next((p for p in PRODUCTS_EXT if p["product_id"] == product_id), {"error": "无此商品"})

def recommend_products(user_need: str, user_id: str = "u001") -> dict:
    need = _parse_shopping_need(user_need)
    q = need["category"] or user_need
    candidates = search_products(q, need["budget"])
    if not candidates:
        candidates = search_products("", need["budget"])

    ranked = []
    for p in candidates:
        score, reasons, risks, not_for = _score_product(p, need)
        ranked.append({
            "product_id": p["product_id"],
            "name": p["name"],
            "brand": p["brand"],
            "price": p["price"],
            "rating": p["rating"],
            "monthly_sales": p["monthly_sales"],
            "store_name": p["store_name"],
            "score": round(score, 2),
            "reasons": reasons,
            "risk_warnings": risks,
            "not_recommend_reasons": not_for,
            "fit_scenarios": _matched(p.get("scenarios", []), need["scenarios"]),
            "not_fit_scenarios": not_for[:],
            "specs": p.get("specs", {}),
        })
    ranked.sort(key=lambda x: (-x["score"], x["price"]))
    return {"user_id": user_id, "parsed_need": need, "recommendations": ranked[:3], "candidate_count": len(candidates)}

def refund_order(order_id: str) -> dict:
    try:
        return _http_post_json(f"{ORDER}/orders/{order_id}/refund")
    except Exception as e:
        if order_id in ORDERS:
            ORDERS[order_id]["status"] = "退款中"
            return {"order_id": order_id, "status": "退款中", "msg": "退款申请已提交,1-3个工作日原路退回"}
        return {"error": f"退款失败: {e}"}

def search_policy(q: str) -> list:
    return retrieve(q, k=POLICY_K)

def _http_get_json(url, params=None):
    if requests:
        return requests.get(url, params=params, timeout=3).json()
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=3) as resp:
        return json.loads(resp.read().decode("utf-8"))

def _http_post_json(url):
    if requests:
        return requests.post(url, timeout=3).json()
    req = urllib.request.Request(url, data=b"", method="POST")
    with urllib.request.urlopen(req, timeout=3) as resp:
        return json.loads(resp.read().decode("utf-8"))

def _local_search_products(q, max_price=None):
    words = [w for w in re.split(r"[\s,，、]+", q or "") if w]
    results = []
    for p in PRODUCTS_EXT:
        if max_price is not None and p.get("price", 0) > float(max_price):
            continue
        haystack = " ".join([
            p.get("name", ""),
            p.get("category", ""),
            " ".join(p.get("tags", [])),
            " ".join(p.get("scenarios", [])),
        ])
        if words and not any(w in haystack for w in words):
            continue
        results.append(p)
    return sorted(results, key=lambda p: (p.get("price", 0), -p.get("rating", 0), -p.get("monthly_sales", 0)))

def _parse_shopping_need(text):
    m = re.search(r"(\d+(?:\.\d+)?)\s*元?\s*(?:以内|以下|内|左右|预算)?", text)
    budget = float(m.group(1)) if m else None
    categories = ["蓝牙耳机", "机械键盘", "充电宝", "鼠标", "显示器", "台灯"]
    prefs = ["降噪", "续航", "性价比", "轻便", "手感好", "静音", "安全", "快充", "护眼", "低漏音"]
    avoid = ["漏音", "连接不稳定", "售后差", "虚标容量", "太吵", "吵", "发热"]
    scenarios = ["宿舍", "图书馆", "写代码", "打游戏", "游戏", "通勤", "自习", "旅行", "网课"]
    category = next((c for c in categories if c in text), None)
    found_prefs = [p for p in prefs if p in text]
    if "别漏音" in text or "不漏音" in text or "漏音" in text:
        found_prefs.append("低漏音")
    if "声音别太吵" in text or "别太吵" in text or "不要太吵" in text:
        found_prefs.append("静音")
    if "续航别太差" in text:
        found_prefs.append("续航")
    found_avoid = [a for a in avoid if a in text]
    if re.search(r"太重|很重|别太重|不要太重|重量", text):
        found_avoid.append("重")
    found_scenarios = [s for s in scenarios if s in text]
    return {
        "raw": text,
        "budget": budget,
        "category": category,
        "preferences": sorted(set(found_prefs), key=found_prefs.index),
        "avoid_keywords": sorted(set(found_avoid), key=found_avoid.index),
        "scenarios": sorted(set(found_scenarios), key=found_scenarios.index),
    }

def _score_product(p, need):
    score = 0.0
    reasons, risks, not_for = [], [], []
    price = float(p.get("price", 0))
    if need["budget"]:
        if price <= need["budget"]:
            score += 18 + (need["budget"] - price) / max(need["budget"], 1) * 8
            reasons.append(f"价格{price:g}元,在预算{need['budget']:g}元以内")
        else:
            score -= 30
            risks.append(f"价格{price:g}元超出预算")
    score += float(p.get("rating", 0)) * 6
    score += min(float(p.get("monthly_sales", 0)) / 400, 8)
    score += float(p.get("store_score", 0)) * 2
    score += float(p.get("aftersale_score", 0)) * 2

    text = " ".join([
        p.get("name", ""),
        p.get("category", ""),
        " ".join(p.get("tags", [])),
        " ".join(p.get("scenarios", [])),
        p.get("review_summary", ""),
        json.dumps(p.get("specs", {}), ensure_ascii=False),
    ])
    for pref in need["preferences"]:
        if pref in text:
            score += 9
            reasons.append(f"匹配偏好:{pref}")
    matched_scenarios = _matched(p.get("scenarios", []), need["scenarios"])
    if matched_scenarios:
        score += len(matched_scenarios) * 5
        reasons.append("适合场景:" + "/".join(matched_scenarios))

    risk_text = " ".join(p.get("risk_points", []))
    for bad in need["avoid_keywords"]:
        if bad in risk_text and f"低{bad}" not in text:
            score -= 12
            risks.append(f"需避雷:{bad}")
            not_for.append(f"介意{bad}的用户要谨慎")
    for r in p.get("risk_points", []):
        if len(risks) < 3:
            risks.append(r)
    if not reasons:
        reasons.append("综合评分、销量和店铺服务表现较均衡")
    if not not_for:
        not_for.append("如果你对更专业参数有强要求,建议再对比详情页参数")
    return score, reasons[:4], risks[:3], not_for[:3]

def _matched(values, wanted):
    return [v for v in values if v in wanted]

FUNCS = {"query_order": query_order, "track_logistics": track_logistics,
         "query_product": query_product, "search_products": search_products,
         "get_product_detail": get_product_detail, "recommend_products": recommend_products,
         "refund_order": refund_order, "search_policy": search_policy}

# ---- 工具契约(OpenAI tools 规范)----
TOOLS = [
    {"type": "function", "function": {
        "name": "query_order", "description": "根据订单号查询订单详情(调用订单微服务)",
        "parameters": {"type": "object",
            "properties": {"order_id": {"type": "string", "description": "8位以上订单号"}},
            "required": ["order_id"]}}},
    {"type": "function", "function": {
        "name": "track_logistics", "description": "根据订单号查询配送/物流状态与是否超时",
        "parameters": {"type": "object",
            "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}}},
    {"type": "function", "function": {
        "name": "query_product", "description": "根据商品名查询价格、库存、评分",
        "parameters": {"type": "object",
            "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "search_products", "description": "按关键词和最高价格搜索导购候选商品",
        "parameters": {"type": "object",
            "properties": {
                "q": {"type": "string"},
                "max_price": {"type": "number"}
            }, "required": ["q"]}}},
    {"type": "function", "function": {
        "name": "get_product_detail", "description": "根据 product_id 查询导购商品完整详情",
        "parameters": {"type": "object",
            "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]}}},
    {"type": "function", "function": {
        "name": "recommend_products", "description": "根据用户购买需求、预算、使用场景、偏好和避雷点，进行个性化商品推荐。",
        "parameters": {"type": "object",
            "properties": {
                "user_need": {"type": "string"},
                "user_id": {"type": "string", "description": "用户ID,可选,默认u001"}
            }, "required": ["user_need"]}}},
    {"type": "function", "function": {
        "name": "search_policy", "description": "检索退货/退款/配送/发票等政策知识(RAG)",
        "parameters": {"type": "object",
            "properties": {"q": {"type": "string"}}, "required": ["q"]}}},
]
