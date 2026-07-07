# -*- coding: utf-8 -*-
"""Collect service quality metrics for the guide-agent demo.

The script measures:
- call metrics: total requests, success count, status codes
- time metrics: avg / p50 / p95 / max latency
- throughput: requests per second
- resource hints: docker stats and kubectl pod status when available

Example:
    python scripts/quality_monitor.py --base-url http://127.0.0.1:8000 --rounds 5
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


DEFAULT_CASES = [
    ("product_query", "蓝牙耳机多少钱？"),
    ("logistics_query", "订单20260601001什么时候到？超时有补偿吗？"),
    ("aftersale_bpmn", "我要对订单20260601001申请退款"),
    (
        "shopping_agent",
        "我想买一个300元以内的蓝牙耳机，主要在宿舍和图书馆用，想要降噪好一点，别漏音，续航别太差",
    ),
]


def percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    index = int(round((pct / 100) * (len(ordered) - 1)))
    return ordered[index]


def run_command(args, timeout=10):
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {
            "available": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except FileNotFoundError:
        return {"available": False, "error": f"command not found: {args[0]}"}
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def wait_until_ready(base_url, timeout_seconds):
    deadline = time.time() + timeout_seconds
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base_url + "/", timeout=3) as resp:
                if resp.status == 200:
                    return True, None
        except Exception as exc:
            last_error = str(exc)
            time.sleep(1)
    return False, last_error


def post_chat(base_url, case_name, message, timeout):
    body = json.dumps({"user_id": "u001", "message": message}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base_url + "/api/chat",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    started = time.perf_counter()
    record = {
        "case": case_name,
        "success": False,
        "status": None,
        "latency_ms": None,
        "intent": None,
        "reply_size": 0,
        "error": None,
    }
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            elapsed_ms = (time.perf_counter() - started) * 1000
            payload = json.loads(raw)
            record.update(
                {
                    "success": 200 <= resp.status < 300,
                    "status": resp.status,
                    "latency_ms": round(elapsed_ms, 2),
                    "intent": payload.get("intent"),
                    "reply_size": len(payload.get("reply", "")),
                }
            )
    except urllib.error.HTTPError as exc:
        record["status"] = exc.code
        record["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        record["error"] = str(exc)
    except Exception as exc:
        record["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        record["error"] = str(exc)
    return record


def collect_call_metrics(base_url, rounds, concurrency, timeout):
    jobs = []
    for _ in range(rounds):
        jobs.extend(DEFAULT_CASES)

    started = time.perf_counter()
    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(post_chat, base_url, name, msg, timeout) for name, msg in jobs]
        for future in as_completed(futures):
            results.append(future.result())
    elapsed = time.perf_counter() - started

    latencies = [r["latency_ms"] for r in results if r.get("latency_ms") is not None]
    successes = [r for r in results if r.get("success")]
    status_codes = {}
    for item in results:
        status = str(item.get("status") or "client_error")
        status_codes[status] = status_codes.get(status, 0) + 1

    return {
        "total_requests": len(results),
        "success_requests": len(successes),
        "failed_requests": len(results) - len(successes),
        "success_rate": round(len(successes) / len(results), 4) if results else 0,
        "throughput_rps": round(len(results) / elapsed, 4) if elapsed > 0 else 0,
        "elapsed_seconds": round(elapsed, 4),
        "latency_ms": {
            "avg": round(statistics.mean(latencies), 2) if latencies else None,
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "max": max(latencies) if latencies else None,
        },
        "status_codes": status_codes,
        "case_results": results,
    }


def collect_resource_metrics(namespace):
    return {
        "docker_compose_ps": run_command(["docker", "compose", "ps"], timeout=10),
        "docker_stats": run_command(["docker", "stats", "--no-stream"], timeout=15),
        "k8s_pods": run_command(["kubectl", "-n", namespace, "get", "pods", "-o", "wide"], timeout=10),
        "k8s_services": run_command(["kubectl", "-n", namespace, "get", "svc"], timeout=10),
        "k8s_deployments": run_command(["kubectl", "-n", namespace, "get", "deploy"], timeout=10),
        "k8s_top_pods": run_command(["kubectl", "-n", namespace, "top", "pods"], timeout=10),
    }


def evaluate_quality(call_metrics):
    success_rate = call_metrics["success_rate"]
    p95 = call_metrics["latency_ms"]["p95"] or 0
    throughput = call_metrics["throughput_rps"]
    failed = call_metrics["failed_requests"]

    if success_rate >= 0.99:
        availability = "excellent"
    elif success_rate >= 0.95:
        availability = "good"
    else:
        availability = "needs_improvement"

    if p95 <= 2000:
        efficiency = "good"
    elif p95 <= 5000:
        efficiency = "acceptable"
    else:
        efficiency = "needs_improvement"

    robustness = "good" if failed == 0 else "needs_attention"
    throughput_level = "demo_ok" if throughput >= 1 else "low"

    return {
        "availability": availability,
        "efficiency": efficiency,
        "robustness": robustness,
        "throughput": throughput_level,
        "method": {
            "availability": "success_requests / total_requests",
            "efficiency": "p95 latency; lower is better",
            "robustness": "failed request count and error distribution",
            "throughput": "total_requests / elapsed_seconds",
        },
    }


def write_reports(output_dir, payload):
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = output_dir / "metrics.json"
    summary_path = output_dir / "summary.md"
    metrics_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    calls = payload["call_metrics"]
    quality = payload["quality_evaluation"]
    summary = [
        "# 服务质量监控结果",
        "",
        f"- 采集时间: {payload['timestamp']}",
        f"- 目标服务: `{payload['base_url']}`",
        f"- 总请求数: {calls['total_requests']}",
        f"- 成功率: {calls['success_rate'] * 100:.2f}%",
        f"- 吞吐率: {calls['throughput_rps']} req/s",
        f"- 平均延迟: {calls['latency_ms']['avg']} ms",
        f"- P50 延迟: {calls['latency_ms']['p50']} ms",
        f"- P95 延迟: {calls['latency_ms']['p95']} ms",
        f"- 最大延迟: {calls['latency_ms']['max']} ms",
        "",
        "## 质量评价",
        "",
        f"- 可用性: {quality['availability']}",
        f"- 效率: {quality['efficiency']}",
        f"- 健壮性: {quality['robustness']}",
        f"- 吞吐率: {quality['throughput']}",
        "",
        "详细原始数据见 `metrics.json`。",
        "",
    ]
    summary_path.write_text("\n".join(summary), encoding="utf-8")
    return metrics_path, summary_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("QUALITY_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--rounds", type=int, default=int(os.getenv("QUALITY_ROUNDS", "5")))
    parser.add_argument("--concurrency", type=int, default=int(os.getenv("QUALITY_CONCURRENCY", "2")))
    parser.add_argument("--timeout", type=int, default=int(os.getenv("QUALITY_TIMEOUT", "90")))
    parser.add_argument("--namespace", default=os.getenv("K8S_NAMESPACE", "service-agent-lab"))
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    ready, error = wait_until_ready(args.base_url, 30)
    if not ready:
        print(f"[FAIL] service not ready: {error}", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir or f"reports/quality/{timestamp}")
    call_metrics = collect_call_metrics(args.base_url, args.rounds, args.concurrency, args.timeout)
    resource_metrics = collect_resource_metrics(args.namespace)
    payload = {
        "timestamp": timestamp,
        "base_url": args.base_url,
        "rounds": args.rounds,
        "concurrency": args.concurrency,
        "call_metrics": call_metrics,
        "resource_metrics": resource_metrics,
        "quality_evaluation": evaluate_quality(call_metrics),
    }
    metrics_path, summary_path = write_reports(output_dir, payload)

    print("[OK] service quality metrics collected")
    print(f"summary: {summary_path}")
    print(f"metrics: {metrics_path}")
    print(
        "success_rate={:.2f}% throughput={}req/s p95={}ms".format(
            call_metrics["success_rate"] * 100,
            call_metrics["throughput_rps"],
            call_metrics["latency_ms"]["p95"],
        )
    )
    return 0 if call_metrics["failed_requests"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
