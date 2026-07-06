# -*- coding: utf-8 -*-
"""个性化导购 Agent: 给 LLM 配备导购工具集,基于商品证据进行推荐推理。

本文件只增强购买决策路径。真实 LLM 可用时,把 evidence 交给模型推理;
不可用或失败时,回退到已有 recommend_products,保证演示稳定。
"""
import json
import os
import re
from typing import Any, Dict, List

from data import PRODUCTS_EXT
from llm import chat
from tools import get_product_detail, recommend_products, search_products, _parse_shopping_need


SOURCE_NOTE = "当前演示使用 demo_data/product_service，真实部署可替换为平台 API 或合规采集接口"


def shopping_research_agent(text: str, user_id: str = "u001", verbose: bool = True) -> dict:
    trace: List[str] = ["[导购] 进入个性化导购 Agent"]

    trace.append("[导购] 需求理解")
    parsed_need = _understand_need(text, trace)
    trace[-1] = "[导购] 需求理解：" + _format_need_trace(parsed_need)

    trace.append("[工具] collect_product_candidates：检索候选商品")
    candidates = collect_product_candidates(text, parsed_need)

    trace.append("[工具] collect_review_summary：收集评价摘要")
    review_summary, risk_points = collect_review_summary(candidates)

    trace.append("[工具] collect_sales_signal：收集销量信号")
    sales_signal = collect_sales_signal(candidates)

    trace.append("[工具] collect_store_profile：收集店铺售后信息")
    store_profile = collect_store_profile(candidates)

    trace.append("[导购] 构造 evidence 证据包")
    evidence = {
        "user_need": text,
        "parsed_need": parsed_need,
        "candidates": candidates,
        "review_summary": review_summary,
        "sales_signal": sales_signal,
        "store_profile": store_profile,
        "risk_points": risk_points,
        "source_note": SOURCE_NOTE,
    }

    if not evidence.get("candidates"):
        trace.append("[导购] 真实LLM不可用，回退到规则推荐")
        return _fallback(text, user_id, trace, evidence)

    if _has_real_llm():
        try:
            trace.append("[导购] 调用真实 LLM 基于证据推理")
            answer = _reason_with_llm(text, evidence)
            trace.append("[导购] 生成 Top3 推荐、风险提醒和不推荐项")
            return {"answer": answer, "trace": trace, "evidence": evidence, "mode": "real_llm"}
        except Exception as e:
            trace.append(f"[导购] 真实LLM调用失败：{e}")

    trace.append("[导购] 真实LLM不可用，回退到规则推荐")
    return _fallback(text, user_id, trace, evidence)


def collect_product_candidates(text: str, parsed_need: Dict[str, Any]) -> List[Dict[str, Any]]:
    """导购工具: 从 product_service/search_products 获取候选商品并补齐详情。"""
    product_source = os.getenv("PRODUCT_SOURCE", "demo").lower()
    q = parsed_need.get("category") or text
    budget = parsed_need.get("budget")
    candidates = search_products(q, budget)
    if not candidates and q != text:
        candidates = search_products(text, budget)
    if not candidates:
        candidates = search_products("", budget)

    detailed = []
    for item in candidates[:8]:
        pid = item.get("product_id")
        has_demo_detail = "review_summary" in item and "store_score" in item
        detail = item if has_demo_detail else (get_product_detail(pid) if pid else item)
        if not isinstance(detail, dict) or detail.get("error"):
            detail = item
        merged = {**item, **detail}
        merged["source"] = _candidate_source(product_source, merged)
        detailed.append(_compact_product(merged))
    return detailed


def collect_review_summary(candidates: List[Dict[str, Any]]):
    """导购工具: 整理评价摘要和风险点。"""
    reviews = {}
    risks = {}
    for p in candidates:
        pid = p.get("product_id") or p.get("name")
        reviews[pid] = {
            "product_id": p.get("product_id"),
            "name": p.get("name"),
            "review_summary": p.get("review_summary", ""),
            "source": p.get("source", "demo_data"),
        }
        risks[pid] = {
            "product_id": p.get("product_id"),
            "name": p.get("name"),
            "risk_points": p.get("risk_points", []),
            "source": p.get("source", "demo_data"),
        }
    return reviews, risks


def collect_sales_signal(candidates: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """导购工具: 整理价格、评分和月销量等热度信号。"""
    signals = {}
    for p in candidates:
        pid = p.get("product_id") or p.get("name")
        signals[pid] = {
            "product_id": p.get("product_id"),
            "name": p.get("name"),
            "price": p.get("price"),
            "rating": p.get("rating"),
            "monthly_sales": p.get("monthly_sales"),
            "source": p.get("source", "demo_data"),
        }
    return signals


def collect_store_profile(candidates: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """导购工具: 整理店铺评分和售后评分。"""
    stores = {}
    for p in candidates:
        pid = p.get("product_id") or p.get("name")
        stores[pid] = {
            "product_id": p.get("product_id"),
            "name": p.get("name"),
            "store_name": p.get("store_name"),
            "store_score": p.get("store_score"),
            "aftersale_score": p.get("aftersale_score"),
            "source": p.get("source", "demo_data"),
        }
    return stores


def _understand_need(text: str, trace: List[str]) -> Dict[str, Any]:
    if not _has_real_llm():
        return _rules_need(text)
    system = (
        "你是电商导购需求理解器。只输出 JSON,不要输出多余文字。字段:"
        "category,budget,scenario,prefer,avoid,need_clarify。"
    )
    try:
        msg = chat(
            [{"role": "system", "content": system}, {"role": "user", "content": text}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return _normalize_llm_need(_safe_json(msg.content), text)
    except Exception as e:
        trace.append(f"[导购] LLM需求理解失败，使用规则抽取：{e}")
        return _rules_need(text)


def _reason_with_llm(text: str, evidence: Dict[str, Any]) -> str:
    system = (
        "你是严谨的个性化电商导购专家。必须只基于 evidence 中出现的数据推荐,"
        "不要编造 evidence 中没有的价格、销量、评价、店铺评分、售后评分或参数。"
        "如果数据来自 demo_data,必须明确说明“当前基于演示数据/样例数据”。"
        "推荐结论必须对应用户预算、场景、偏好和避雷点。"
        "输出必须包含:Top3 推荐、推荐理由、风险提醒、不推荐商品、适合/不适合场景、数据来源说明。"
    )
    prompt = "用户需求:\n{}\n\nevidence:\n{}".format(
        text, json.dumps(evidence, ensure_ascii=False, indent=2)
    )
    msg = chat(
        [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return msg.content


def _fallback(text: str, user_id: str, trace: List[str], evidence: Dict[str, Any]) -> dict:
    result = recommend_products(text, user_id=user_id)
    fallback_evidence = evidence or {
        "user_need": text,
        "parsed_need": result.get("parsed_need", {}),
        "candidates": [],
        "review_summary": {},
        "sales_signal": {},
        "store_profile": {},
        "risk_points": {},
        "source_note": SOURCE_NOTE,
    }
    for r in result.get("recommendations", []):
        r.setdefault("source", "fallback")
    if not fallback_evidence.get("candidates"):
        fallback_evidence["candidates"] = result.get("recommendations", [])
    return {
        "answer": _format_fallback_answer(result),
        "trace": trace,
        "evidence": fallback_evidence,
        "mode": "fallback_rules",
    }


def _format_fallback_answer(result: dict) -> str:
    need = result.get("parsed_need", {})
    recs = result.get("recommendations", [])
    if not recs:
        return (
            "Top3 推荐: 暂时没有找到足够匹配的商品。\n"
            "推荐理由: 规则推荐未检索到有效候选。\n"
            "风险提醒: 建议放宽预算或减少限制条件后再试。\n"
            "不推荐商品: 暂无。\n"
            "适合/不适合场景: 信息不足。\n"
            "数据来源说明: 当前基于演示数据/样例数据和 fallback 规则推荐。"
        )

    budget = f"{need['budget']:g}元以内" if need.get("budget") else "未指定预算"
    prefs = "、".join(need.get("preferences") or ["综合体验"])
    avoids = "、".join(need.get("avoid_keywords") or ["明显短板"])
    parts = ["Top3 推荐:"]
    for i, r in enumerate(recs, 1):
        fit = "、".join(r.get("fit_scenarios") or ["日常使用"])
        not_fit = "、".join(r.get("not_fit_scenarios") or r.get("not_recommend_reasons") or ["暂无明显不适合场景"])
        parts.append(
            f"{i}. {r['name']}({r['brand']}) - {r['price']}元，评分{r['rating']}，月销{r['monthly_sales']}。"
            f"适合:{fit}; 不适合:{not_fit}。"
        )
    parts.append(f"推荐依据: 规则推荐按预算 {budget}、偏好 {prefs}、避雷点 {avoids}、评分、销量和店铺售后表现综合排序。")
    parts.append("推荐理由:")
    for i, r in enumerate(recs, 1):
        reasons = "；".join(r.get("reasons") or ["综合表现均衡"])
        parts.append(f"{i}. {r['name']}: {reasons}")
    parts.append("风险提醒:")
    for i, r in enumerate(recs, 1):
        risks = "；".join(r.get("risk_warnings") or ["暂无明显风险"])
        parts.append(f"{i}. {r['name']}: {risks}")
    parts.append("不推荐商品: 超预算、明显命中避雷点或场景不匹配的商品会被降权；对漏音敏感时不优先推荐安静环境大音量可能漏音的款式。")
    parts.append("数据来源说明: 当前基于演示数据/样例数据、product_service 候选检索结果和 fallback 规则推荐。")
    return "\n".join(parts)


def _has_real_llm() -> bool:
    mode = os.getenv("SHOPPING_AGENT_MODE", "auto").lower()
    if mode in ("rules", "fallback", "mock"):
        return False
    return bool(os.getenv("OPENAI_API_KEY"))


def _rules_need(text: str) -> Dict[str, Any]:
    need = _parse_shopping_need(text)
    need.setdefault("need_clarify", False)
    return need


def _normalize_llm_need(data: Dict[str, Any], text: str) -> Dict[str, Any]:
    rules = _rules_need(text)
    budget = data.get("budget", rules.get("budget"))
    try:
        budget = float(budget) if budget not in (None, "", "null") else None
    except (TypeError, ValueError):
        budget = rules.get("budget")
    return {
        "raw": text,
        "category": data.get("category") or rules.get("category"),
        "budget": budget,
        "scenarios": _as_list(data.get("scenario")) or rules.get("scenarios", []),
        "preferences": _as_list(data.get("prefer")) or rules.get("preferences", []),
        "avoid_keywords": _as_list(data.get("avoid")) or rules.get("avoid_keywords", []),
        "need_clarify": bool(data.get("need_clarify", False)),
    }


def _format_need_trace(need: Dict[str, Any]) -> str:
    budget = f"{need['budget']:g}以内" if need.get("budget") else "未指定"
    scenarios = "/".join(need.get("scenarios") or ["未指定"])
    prefs = "/".join(need.get("preferences") or ["综合体验"])
    avoids = "/".join(need.get("avoid_keywords") or ["未指定"])
    return f"预算={budget}，场景={scenarios}，偏好={prefs}，避雷={avoids}"


def _compact_product(p: Dict[str, Any]) -> Dict[str, Any]:
    keys = [
        "product_id", "name", "category", "brand", "price", "stock", "rating",
        "monthly_sales", "tags", "scenarios", "specs", "review_summary",
        "risk_points", "store_name", "store_score", "aftersale_score", "source",
    ]
    return {k: p.get(k) for k in keys if k in p}


def _candidate_source(product_source: str, p: Dict[str, Any]) -> str:
    if product_source == "demo":
        return "demo_data"
    if any(x.get("product_id") == p.get("product_id") for x in PRODUCTS_EXT):
        return "product_service"
    return "fallback"


def _safe_json(content: str) -> Dict[str, Any]:
    try:
        return json.loads(content)
    except Exception:
        m = re.search(r"\{.*\}", content or "", re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [x.strip() for x in re.split(r"[,，/、\s]+", value) if x.strip()]
    return [str(value)]
