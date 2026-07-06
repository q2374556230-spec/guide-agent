# -*- coding: utf-8 -*-
"""
更能体现 Agent 优势的开放式业务流程:智能售后管家。
入口是一句【模糊、无订单号、可能多诉求】的话,例如:
  "我最近买的东西有点问题,有个外卖好像超时了,还有个耳机不太满意,帮我看看都怎么处理,能退尽量退"

这类诉求传统微服务/固定 BPMN 做不了,因为:
  - 没有订单号,得先"自己去找"用户的订单;
  - 不知道有几个问题,步骤数量随数据而变(动态规划);
  - "怎么处理"没有固定分支,要按每单的诊断 + 政策来判断(自动/澄清/转人工);
  - 最终要把多件事综合成一份处置方案,并主动追问缺失信息。

本模块用当前技术栈真实跑通(调微服务 + RAG)。判断逻辑此处用规则模拟,
接入真实大模型后,这些"诊断/判断/综合"步骤即由 LLM 完成,结构不变。
"""
import os, requests
from rag import retrieve

ORDER = os.getenv("ORDER_URL", "http://localhost:8001")
LOGI = os.getenv("LOGISTICS_URL", "http://localhost:8003")

def list_user_orders(uid):
    return requests.get(f"{ORDER}/users/{uid}/orders", timeout=3).json()

def smart_resolve(user_id, text, log=print):
    log(f"用户诉求:{text}")
    log("[理解] 开放式售后诉求、无订单号、可能多诉求 → 先检索该用户订单")
    wants_refund = ("退" in text)
    unsat = any(k in text for k in ["不满意", "问题", "不好", "毛病"])

    orders = list_user_orders(user_id)
    log(f"[规划] 查到该用户 {len(orders)} 个订单,逐单动态诊断(步骤随订单数变化)")

    plan, clarify, actions = [], [], []
    for o in orders:
        oid, typ, amt, st = o["order_id"], o.get("type"), o.get("amount", 0), o.get("status")
        log(f"  ├ 订单{oid}({typ},¥{amt},{st})")
        if typ == "外卖":
            tl = requests.get(f"{LOGI}/track/{oid}", timeout=3).json()
            if tl.get("timed_out"):
                pol = retrieve("超时补偿", 1)[0]
                log("  │   诊断=配送超时 → RAG政策命中 → 判定:小额可自动补偿 → 执行")
                actions.append(f"已为外卖订单{oid}自动发放超时红包补偿(依据:{pol[:18]}…)")
                plan.append(f"订单{oid}(外卖·超时):✅ 已自动补偿。")
            else:
                log("  │   诊断=未超时 → 无需处理")
        else:  # 电商
            if unsat or wants_refund:
                pol = retrieve("退货 换货 政策", 1)[0]
                if amt >= 100:
                    log("  │   诊断=数码类+金额较大 → 7天无理由可退/可换,需澄清且退款转人工")
                    clarify.append(f"耳机订单{oid}(¥{amt}):支持7天无理由退货,也可换新。你要『退货退款』还是『换货』?")
                    plan.append(f"订单{oid}(耳机·不满意):⏳ 待你确认退/换;退款金额较大将转人工复核。")
                else:
                    plan.append(f"订单{oid}:✅ 可直接退货退款。")
            else:
                log("  │   未表达不满 → 暂不处理")
    log("[综合] 汇总处置方案,并主动追问缺失信息")

    reply = "我看了你名下的订单,帮你这样处理:\n" + "\n".join("· " + p for p in plan)
    if actions:
        reply += "\n已自动完成:" + ";".join(actions) + "。"
    if clarify:
        reply += "\n还需你确认一下:\n" + "\n".join("? " + c for c in clarify)
    return {"plan": plan, "actions": actions, "clarify": clarify, "reply": reply}

if __name__ == "__main__":
    complaint = "我最近买的东西有点问题,有个外卖好像超时了,还有个耳机不太满意,帮我看看都怎么处理,能退尽量退"
    print("=" * 66)
    r = smart_resolve("u001", complaint)
    print("-" * 66)
    print("【助理最终回复】\n" + r["reply"])
    print("=" * 66)
