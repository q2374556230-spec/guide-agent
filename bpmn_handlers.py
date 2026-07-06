# -*- coding: utf-8 -*-
"""把 aftersale.bpmn 里的每个"任务"节点绑定到真实动作(调微服务 / RAG / 退款)。
这就是 BPMN 与系统的"接线":流程图的节点 id ←→ 这里的处理器函数。"""
import os
from tools import query_order, track_logistics, refund_order, search_policy

BPMN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flows", "aftersale.bpmn")

def h_query_order(ctx):
    o = query_order(ctx["order_id"])
    ctx["order"] = o
    ctx["amount"] = o.get("amount", 0)
    tl = track_logistics(ctx["order_id"])
    ctx["timed_out"] = bool(tl.get("timed_out"))
    return f"调订单+物流微服务 (状态={o.get('status')}, 金额={ctx['amount']}, 超时={ctx['timed_out']})"

def h_compensation(ctx):
    ctx["policy"] = search_policy("超时补偿")
    return "RAG检索→ " + ctx["policy"][0][:20] + "…"

def h_refund_policy(ctx):
    ctx["policy"] = search_policy("退款政策")
    return "RAG检索→ " + ctx["policy"][0][:20] + "…"

def h_manual_review(ctx):
    ctx["result"] = "金额较大,已转人工审核(待人工确认后退款)"
    return ctx["result"]

def h_auto_refund(ctx):
    r = refund_order(ctx["order_id"])
    ctx["result"] = f"已自动发起退款(状态={r.get('status')})"
    return ctx["result"]

def h_notify(ctx):
    pol = "；".join(ctx.get("policy", []))
    ctx["final"] = f"订单{ctx['order_id']}:{ctx.get('result', '')}。相关政策:{pol}"
    return "已通知用户"

# 处理器注册表:key = 节点上配置的实现名(.bpmn 里 camunda:delegateExpression="${名字}")。
# 引擎读到节点的实现引用后,按这个名字到这里找对应函数 —— 等价于 Camunda 按 bean 名/类名解析。
HANDLERS = {
    "h_query_order": h_query_order,       # serviceTask:节点上 delegateExpression="${h_query_order}"
    "h_compensation": h_compensation,
    "h_refund_policy": h_refund_policy,
    "h_auto_refund": h_auto_refund,
    "h_notify": h_notify,
    "人工审核": h_manual_review,           # userTask:人工节点,按节点名兜底(真实引擎中由人工完成)
}

def run_aftersale(order_id, user_id="u001"):
    """执行售后退款 BPMN 流程,返回 (最终答复, 执行轨迹列表)。"""
    from bpmn_engine import run_bpmn
    trace = []
    ctx = {"order_id": order_id, "user_id": user_id}
    run_bpmn(BPMN_FILE, HANDLERS, ctx, log=lambda s: trace.append("[BPMN] " + s))
    return ctx.get("final", "(流程未产生结果)"), trace

if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    for oid in ["20260601001", "20260601002"]:
        print(f"\n##### 售后流程:订单 {oid} #####")
        final, trace = run_aftersale(oid)
        for line in trace:
            print(" ", line)
        print("  最终答复:", final)
