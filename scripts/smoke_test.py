# -*- coding: utf-8 -*-
"""Deployment smoke tests for service-agent-lab.

The shopping path may call a real LLM in Kubernetes, so the chat timeout is
configurable and intentionally longer than a normal local unit test.

Examples:
    python scripts/smoke_test.py
    SMOKE_CHAT_TIMEOUT=90 python scripts/smoke_test.py
"""
import json
import os
import sys
import time
import urllib.request


BASE_URL = os.getenv("SMOKE_BASE_URL", "http://127.0.0.1:8000")
READY_TIMEOUT = int(os.getenv("SMOKE_READY_TIMEOUT", "30"))
CHAT_TIMEOUT = int(os.getenv("SMOKE_CHAT_TIMEOUT", "90"))


def post_chat(message):
    body = json.dumps({"user_id": "u001", "message": message}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + "/api/chat",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=CHAT_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wait_until_ready():
    last_error = None
    deadline = time.time() + READY_TIMEOUT
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE_URL + "/", timeout=3) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"service not ready: {last_error}")


def assert_contains(name, text, keywords):
    if not any(k in text for k in keywords):
        raise AssertionError(f"{name} missing expected keywords {keywords}: {text[:300]}")


def main():
    print(f"[INFO] smoke base_url={BASE_URL} chat_timeout={CHAT_TIMEOUT}s")
    wait_until_ready()

    cases = [
        ("product", "蓝牙耳机多少钱？", ["蓝牙耳机", "售价", "库存", "价格"]),
        (
            "shopping",
            "我想买一个300元以内的蓝牙耳机，图书馆用，重视降噪和续航，不想漏音",
            ["推荐", "风险", "来源", "Top3"],
        ),
        ("aftersale", "我要对订单20260601001申请退款", ["退款", "订单", "售后"]),
    ]
    for name, message, keywords in cases:
        started = time.perf_counter()
        result = post_chat(message)
        elapsed = round(time.perf_counter() - started, 3)
        reply = result.get("reply", "")
        trace = result.get("trace", "")
        assert_contains(name, reply + trace, keywords)
        print(f"[OK] {name}: intent={result.get('intent')} elapsed={elapsed}s latency={result.get('latency')}")

    print("[OK] deployment smoke test passed")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        sys.exit(1)
