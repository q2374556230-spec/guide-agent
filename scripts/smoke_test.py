# -*- coding: utf-8 -*-
"""Deployment smoke tests for service-agent-lab.

Run after `docker compose up -d --build`:
    python scripts/smoke_test.py
"""
import json
import sys
import time
import urllib.request


BASE_URL = "http://127.0.0.1:8000"


def post_chat(message):
    body = json.dumps({"user_id": "u001", "message": message}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + "/api/chat",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wait_until_ready():
    last_error = None
    for _ in range(20):
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
        raise AssertionError(f"{name} missing expected keywords {keywords}: {text[:200]}")


def main():
    wait_until_ready()

    cases = [
        ("product", "蓝牙耳机多少钱？", ["蓝牙耳机", "售价", "库存"]),
        ("shopping", "我想买一个300元以内的蓝牙耳机，图书馆用，重视降噪和续航，不想漏音", ["推荐", "风险", "来源"]),
        ("aftersale", "我要对订单20260601001申请退款", ["退款", "订单"]),
    ]
    for name, message, keywords in cases:
        result = post_chat(message)
        reply = result.get("reply", "")
        trace = result.get("trace", "")
        assert_contains(name, reply + trace, keywords)
        print(f"[OK] {name}: intent={result.get('intent')} latency={result.get('latency')}")

    print("[OK] deployment smoke test passed")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        sys.exit(1)
