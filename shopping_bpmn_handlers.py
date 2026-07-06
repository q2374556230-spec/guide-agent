# -*- coding: utf-8 -*-
"""个性化导购 BPMN 处理器。

流程文件: flows/shopping_guide.bpmn
作用:把导购 Agent 的"需求理解 -> 检索 -> 评分 -> 风险 -> 推荐"落成可执行 BPMN。
"""
import os
import re
from tools import search_products, recommend_products

BPMN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flows", "shopping_guide.bpmn")

USER_PROFILES = {
    "u001": {
        "preferred_categories": ["数码"],
        "preferred_scenarios": ["宿舍", "图书馆"],
        "risk_sensitive": ["漏音", "售后差", "虚标容量"],
    }
}

def h_parse_need(ctx):
    text = ctx["text"]
    need = _parse_need(text)
    missing = []
    if not need["category"]:
        missing.append("商品类别")
    if need["budget"] is None:
        missing.append("预算")
    if not need["scenarios"]:
        missing.append("使用场景")
    if not need["preferences"] and not need["avoid_keywords"]:
        missing.append("偏好或避雷点")
    ctx["need"] = need
    ctx["missing_fields"] = missing
    ctx["missing_info"] = bool(missing)
    return "需求解析→ " + _need_brief(need) + ("; 缺少:" + "/".join(missing) if missing else "; 信息完整")

def h_ask_preference(ctx):
    fields = ctx.get("missing_fields") or ["预算", "用途", "偏好"]
    ctx["ask"] = "为了给你更准的推荐,请补充:" + "、".join(fields) + "。例如:预算300元以内,图书馆用,重视降噪和续航,不想漏音。"
    ctx["final"] = ctx["ask"]
    return "追问用户→ " + ctx["ask"]

def h_load_user_profile(ctx):
    ctx["profile"] = USER_PROFILES.get(ctx.get("user_id", "u001"), {})
    return "读取画像→ " + (str(ctx["profile"]) if ctx["profile"] else "无历史画像")

def h_search_products(ctx):
    need = ctx["need"]
    q = need["category"] or ctx["text"]
    ctx["candidates"] = search_products(q, need["budget"])
    return f"商品检索→ q={q}, 候选{len(ctx['candidates'])}个"

def h_score_products(ctx):
    result = recommend_products(ctx["text"], ctx.get("user_id", "u001"))
    ctx["recommend_result"] = result
    ctx["has_risk"] = _has_obvious_risk(result, ctx.get("need", {}))
    return f"多维评分→ Top{len(result.get('recommendations', []))}, 明显风险={ctx['has_risk']}"

def h_mark_risk(ctx):
    result = ctx.get("recommend_result", {})
    avoid = ctx.get("need", {}).get("avoid_keywords", [])
    for item in result.get("recommendations", []):
        joined = " ".join(item.get("risk_warnings", []) + item.get("not_recommend_reasons", []))
        if any(k in joined for k in avoid):
            item["score"] = round(item.get("score", 0) - 8, 2)
            item.setdefault("risk_warnings", []).insert(0, "已命中用户避雷点,推荐权重已降低")
    result.get("recommendations", []).sort(key=lambda x: (-x.get("score", 0), x.get("price", 0)))
    return "风险处理→ 已标记风险商品并降低权重"

def h_generate_recommendation(ctx):
    result = ctx.get("recommend_result", {})
    need = result.get("parsed_need", ctx.get("need", {}))
    recs = result.get("recommendations", [])
    if not recs:
        ctx["recommend_text"] = "暂时没有找到足够匹配的商品,建议放宽预算或补充更多使用场景。"
        return "生成推荐→ 无候选"
    lines = []
    budget = f"{need['budget']:g}元以内" if need.get("budget") else "未指定预算"
    prefs = "、".join(need.get("preferences") or ["综合体验"])
    avoids = "、".join(need.get("avoid_keywords") or ["明显短板"])
    lines.append(f"我按「{need.get('category') or '商品'} / {budget} / 偏好:{prefs} / 避雷:{avoids}」生成 Top3 推荐。")
    for i, r in enumerate(recs[:3], 1):
        reasons = "；".join(r.get("reasons") or ["综合表现均衡"])
        risks = "；".join(r.get("risk_warnings") or ["暂无明显风险"])
        fit = "、".join(r.get("fit_scenarios") or ["日常使用"])
        not_fit = "、".join(r.get("not_recommend_reasons") or ["暂无明确不适合场景"])
        lines.append(
            f"{i}. {r['name']}({r['brand']}) - {r['price']}元,评分{r['rating']},月销{r['monthly_sales']}。\n"
            f"   推荐理由:{reasons}。\n"
            f"   风险提示:{risks}。\n"
            f"   适合场景:{fit};不适合/不推荐理由:{not_fit}。"
        )
    ctx["recommend_text"] = "\n".join(lines)
    return "生成推荐→ Top3推荐与风险提示已生成"

def h_save_preference(ctx):
    uid = ctx.get("user_id", "u001")
    need = ctx.get("need", {})
    profile = USER_PROFILES.setdefault(uid, {})
    if need.get("category"):
        profile["last_category"] = need["category"]
    if need.get("preferences"):
        profile["last_preferences"] = need["preferences"]
    if need.get("avoid_keywords"):
        profile["risk_sensitive"] = sorted(set(profile.get("risk_sensitive", []) + need["avoid_keywords"]))
    ctx["saved_profile"] = profile
    return "保存偏好→ " + str(profile)

def h_notify_user(ctx):
    ctx["final"] = ctx.get("recommend_text") or ctx.get("ask") or "导购流程已完成。"
    return "通知用户"

HANDLERS = {
    "h_parse_need": h_parse_need,
    "h_ask_preference": h_ask_preference,
    "h_load_user_profile": h_load_user_profile,
    "h_search_products": h_search_products,
    "h_score_products": h_score_products,
    "h_mark_risk": h_mark_risk,
    "h_generate_recommendation": h_generate_recommendation,
    "h_save_preference": h_save_preference,
    "h_notify_user": h_notify_user,
}

def run_shopping_guide(text, user_id="u001"):
    """执行导购 BPMN 流程,返回 (最终答复, 执行轨迹列表)。"""
    from bpmn_engine import run_bpmn
    trace = []
    ctx = {"text": text, "user_id": user_id}
    run_bpmn(BPMN_FILE, HANDLERS, ctx, log=lambda s: trace.append("[BPMN-导购] " + _safe_trace(s)))
    return ctx.get("final", "(流程未产生结果)"), trace

def _parse_need(text):
    m = re.search(r"(\d+(?:\.\d+)?)\s*元?\s*(?:以内|以下|内|左右|预算)?", text)
    budget = float(m.group(1)) if m else None
    category_aliases = [
        ("蓝牙耳机", ["蓝牙耳机", "耳机"]),
        ("机械键盘", ["机械键盘", "键盘"]),
        ("充电宝", ["充电宝", "移动电源"]),
        ("鼠标", ["鼠标"]),
        ("显示器", ["显示器"]),
        ("台灯", ["台灯"]),
    ]
    category = None
    for name, aliases in category_aliases:
        if any(a in text for a in aliases):
            category = name
            break
    prefs = ["降噪", "续航", "性价比", "轻便", "手感好", "静音", "安全", "快充", "护眼", "低漏音"]
    avoid = ["漏音", "连接不稳定", "售后差", "虚标容量", "太吵", "吵", "发热"]
    scenarios = ["宿舍", "图书馆", "写代码", "打游戏", "游戏", "通勤", "自习", "旅行", "网课"]
    found_prefs = [p for p in prefs if p in text]
    if "漏音" in text:
        found_prefs.append("低漏音")
    if "别太吵" in text or "不要太吵" in text or "声音别太吵" in text:
        found_prefs.append("静音")
    if "续航别太差" in text:
        found_prefs.append("续航")
    return {
        "raw": text,
        "budget": budget,
        "category": category,
        "preferences": _dedupe(found_prefs),
        "avoid_keywords": _dedupe([a for a in avoid if a in text] + (["重"] if re.search(r"太重|很重|别太重|不要太重|重量", text) else [])),
        "scenarios": _dedupe([s for s in scenarios if s in text]),
    }

def _has_obvious_risk(result, need):
    avoid = need.get("avoid_keywords", [])
    for item in result.get("recommendations", []):
        joined = " ".join(item.get("risk_warnings", []) + item.get("not_recommend_reasons", []))
        if any(k in joined for k in avoid):
            return True
    return False

def _need_brief(need):
    budget = f"{need['budget']:g}元" if need.get("budget") else "未给预算"
    return f"品类={need.get('category') or '未知'},预算={budget},场景={need.get('scenarios')},偏好={need.get('preferences')},避雷={need.get('avoid_keywords')}"

def _dedupe(items):
    out = []
    for item in items:
        if item not in out:
            out.append(item)
    return out

def _safe_trace(text):
    return text.replace("▶", ">").replace("■", "#")

if __name__ == "__main__":
    demos = [
        "我想买一个300元以内的蓝牙耳机，图书馆用，重视降噪和续航，不想漏音",
        "帮我推荐个耳机",
    ]
    for q in demos:
        print(f"\n##### 导购流程:{q} #####")
        final, trace = run_shopping_guide(q)
        for line in trace:
            print(" ", line)
        print("  最终答复:", final)
