# -*- coding: utf-8 -*-
"""离线评测:固定问题集 + LLM-as-judge 自动打分(实验4)。"""
import json, time
from llm import chat
from agent import orchestrate

EVAL = [
    {"q": "订单20260601001到哪了?", "must": ["配送中"]},
    {"q": "外卖超时了有没有补偿?", "must": ["补偿"]},
    {"q": "蓝牙耳机多少钱?", "must": ["199"]},
    {"q": "耳机能退货吗?", "must": ["换货"]},
    {"q": "我要查订单20260601002的物流", "must": ["顺丰"]},
    {"q": "我想买一个300元以内的蓝牙耳机，主要在宿舍和图书馆用，想要降噪好一点，别漏音，续航别太差",
     "must": ["推荐", "理由", "风险"]},
    {"q": "500元以内机械键盘，写代码和打游戏，声音别太吵",
     "must": ["推荐", "理由", "风险"]},
    {"q": "轻便安全的充电宝，不想买虚标容量的",
     "must": ["推荐", "理由", "风险"]},
]

def judge(answer, must):
    prompt = (f'判断回答是否覆盖了所有要点。要点:{must}\n回答:{answer}\n'
              '只输出 JSON: {"pass": true/false}')
    try:
        return json.loads(chat([{"role": "user", "content": prompt}],
                               temperature=0,
                               response_format={"type": "json_object"}).content)
    except Exception:
        return {"pass": False}

def run_eval(verbose=True):
    passed, rows = 0, []
    for c in EVAL:
        t0 = time.time()
        ans = orchestrate(c["q"], verbose=False)["answer"]
        r = judge(ans, c["must"])
        ok = bool(r.get("pass"))
        passed += ok
        rows.append((c["q"], ok, round(time.time()-t0, 3), ans))
        if verbose:
            print(f"[{'PASS' if ok else 'FAIL'}] {c['q']}")
            print(f"        答:{ans[:70]}")
    print(f"\n==== 通过率: {passed}/{len(EVAL)} = {passed/len(EVAL)*100:.0f}% ====")
    return rows

if __name__ == "__main__":
    run_eval()
