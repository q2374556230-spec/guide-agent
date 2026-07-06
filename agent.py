# -*- coding: utf-8 -*-
"""
Agent 与多 Agent 编排。
- detect_intent: 自然语言进、结构化出(实验1)
- react_agent:   单 Agent ReAct 自主多步规划(实验2)
- router/experts + orchestrate: 多 Agent 路由 + 专家协作(实验3)
"""
import json
import sys
from llm import client, chat, CHAT_MODEL, BACKEND
from shopping_research_agent import shopping_research_agent
from tools import TOOLS, FUNCS, recommend_products

# ---------- 实验1:意图识别 ----------
INTENT_SYSTEM = """你是电商/外卖智能服务的意图识别入口。
只输出 JSON:{"intent": "...", "entities": {...}}
intent 取值:查订单/查物流/商品咨询/退款售后/其他。不要输出多余文字。"""

def detect_intent(text):
    msg = chat([{"role": "system", "content": INTENT_SYSTEM},
                {"role": "user", "content": text}],
               temperature=0, response_format={"type": "json_object"})
    try:
        return json.loads(msg.content)
    except json.JSONDecodeError:
        return {"intent": "其他", "entities": {}}

# ---------- 实验2:ReAct 自主多步 Agent ----------
PLAN_SYSTEM = """你是电商/外卖智能服务助理。面对复杂问题:
先把它拆成多个步骤,每次只调用一个最必要的工具;拿到结果后再判断下一步;
信息齐全后才综合回答。不要编造未查到的信息。"""

def react_agent(user_text, max_steps=6, verbose=True, extra_msgs=None):
    msgs = [{"role": "system", "content": PLAN_SYSTEM}]
    if extra_msgs:
        msgs += extra_msgs
    msgs.append({"role": "user", "content": user_text})
    for step in range(1, max_steps + 1):
        m = client.chat.completions.create(model=CHAT_MODEL, messages=msgs,
                                           tools=TOOLS).choices[0].message
        msgs.append(m.model_dump() if hasattr(m, "model_dump") else m)
        if not m.tool_calls:
            if verbose:
                print(f"  [第{step}步] 思考→信息已齐全,生成最终答复")
            return m.content
        for tc in m.tool_calls:
            args = json.loads(tc.function.arguments)
            obs = FUNCS[tc.function.name](**args)
            if verbose:
                print(f"  [第{step}步] 行动→调用 {tc.function.name}({args})")
                print(f"           观察← {json.dumps(obs, ensure_ascii=False)[:90]}")
            msgs.append({"role": "tool", "tool_call_id": tc.id,
                         "content": json.dumps(obs, ensure_ascii=False)})
    return "(已达最大步数,请缩小问题范围)"

# ---------- 实验3:多 Agent 路由 + 专家 ----------
def router(text):
    """路由 Agent:判断诉求类别(对应业务流程的第一个网关)。"""
    intent = chat([{"role": "system", "content": "判断用户意图,只回一个词:售后/物流/导购/其他"},
                   {"role": "user", "content": text}], temperature=0).content.strip()
    return _normalize_route_intent(intent)

def expert_logistics(text, ctx=None, verbose=False):
    return "【物流专家】" + react_agent(text, verbose=verbose, extra_msgs=ctx)

def expert_aftersale(text, ctx=None, verbose=False):
    # 售后专家:若带订单号,走【BPMN 流程引擎】执行 aftersale.bpmn(业务流程真正驱动系统);
    # 否则退回 ReAct。这就是 BPMN 与系统的集成点。
    import re
    oids = re.findall(r"\d{8,}", text)
    if oids:
        from bpmn_handlers import run_aftersale
        final, trace = run_aftersale(oids[0])
        if verbose:
            for line in trace:
                print(_console_text("  " + line))
        return "【售后专家·BPMN流程】" + final
    return "【售后专家】" + react_agent(text, verbose=verbose, extra_msgs=ctx)

def expert_shopping(text, ctx=None, verbose=False):
    if _is_purchase_decision(text):
        result = shopping_research_agent(text, user_id="u001", verbose=verbose)
        if verbose:
            for line in result.get("trace", []):
                print(_console_text("  " + line))
        return "【导购专家】" + result.get("answer", "")
    return "【导购专家】" + react_agent(text, verbose=verbose, extra_msgs=ctx)

def _is_purchase_decision(text):
    decision_kw = ["买", "购买", "推荐", "选", "预算", "以内", "适合"]
    product_kw = ["耳机", "键盘", "充电宝", "鼠标", "显示器", "台灯"]
    simple_query_kw = ["多少钱", "价格", "库存", "有货"]
    if any(k in text for k in simple_query_kw) and not any(k in text for k in decision_kw):
        return False
    return any(k in text for k in decision_kw) and any(k in text for k in product_kw)

def _router_backend_label():
    return "real-llm" if str(BACKEND).startswith("real:") else "mock-llm"

def _normalize_route_intent(intent):
    for name in ("售后", "物流", "导购", "其他"):
        if name in intent:
            return name
    return "其他"

def _console_text(text):
    encoding = getattr(sys.stdout, "encoding", None)
    if not encoding:
        return text
    return str(text).encode(encoding, errors="replace").decode(encoding, errors="replace")

def _format_recommendation(result):
    need = result.get("parsed_need", {})
    recs = result.get("recommendations", [])
    if not recs:
        return "暂时没有找到足够匹配的商品。建议放宽预算或减少限制条件后再试。"
    parts = []
    category = need.get("category") or "商品"
    budget = f"{need['budget']:g}元以内" if need.get("budget") else "未指定预算"
    prefs = "、".join(need.get("preferences") or ["综合体验"])
    avoids = "、".join(need.get("avoid_keywords") or ["明显短板"])
    parts.append(f"我按「{category} / {budget} / 偏好:{prefs} / 避雷:{avoids}」做了多维评分。")
    parts.append("Top3 推荐:")
    for i, r in enumerate(recs, 1):
        specs = r.get("specs", {})
        spec_txt = "；".join(f"{k}:{v}" for k, v in specs.items()) if specs else "参数未补充"
        fit = "、".join(r.get("fit_scenarios") or ["日常使用"])
        not_fit = "、".join(r.get("not_fit_scenarios") or ["暂无明显不适合场景"])
        reasons = "；".join(r.get("reasons") or ["综合表现均衡"])
        risks = "；".join(r.get("risk_warnings") or ["暂无明显风险"])
        parts.append(
            f"{i}. {r['name']}({r['brand']}) - {r['price']}元,评分{r['rating']},月销{r['monthly_sales']},店铺:{r['store_name']}。\n"
            f"   推荐理由:{reasons}。\n"
            f"   风险提醒:{risks}。\n"
            f"   适合场景:{fit};不适合场景/不推荐理由:{not_fit}。\n"
            f"   关键参数:{spec_txt}。"
        )
    return "\n".join(parts)

EXPERTS = {"物流": expert_logistics, "售后": expert_aftersale, "导购": expert_shopping}

def orchestrate(text, memory=None, verbose=True):
    """编排:路由 → 分派专家。对应'编排者+专家'架构。"""
    ctx = None
    if memory is not None:
        ctx = memory.build("")[1:]  # 带上画像/摘要/历史(去掉空 system)
    intent = router(text)
    if intent == "其他" and _is_purchase_decision(text):
        intent = "导购"
    if verbose:
        print(f"  [路由] 后端={_router_backend_label()}")
        print(f"  [路由] 判定意图={intent}")
    expert = EXPERTS.get(intent)
    answer = expert(text, ctx, verbose) if expert else "您好,我可以帮您查订单、查物流、查商品或处理售后。"
    return {"intent": intent, "answer": answer}
