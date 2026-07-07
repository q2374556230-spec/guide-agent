# -*- coding: utf-8 -*-
"""
Web 后端(端口 8000)。一条命令启动整套可视化系统:
    python3 server.py
然后浏览器打开 http://localhost:8000 即可对话。

它做三件事:
  1) 本地模式下在后台线程启动三个业务微服务(8001/8002/8003);
  2) GET  /            返回前端页面 web/index.html;
  3) POST /api/chat    接收 {message,user_id},调用 Agent,返回 {reply,intent,trace}。
零依赖:仅用 Python 标准库。
"""
import os, sys, json, time, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---- 1. 本地模式:后台启动业务微服务 ----
# Docker Compose / Kubernetes 中由独立容器启动微服务,设置
# EMBEDDED_SERVICES=false 即可关闭这里的内嵌服务。
EMBEDDED_SERVICES = os.getenv("EMBEDDED_SERVICES", "true").lower() not in ("0", "false", "no")

if EMBEDDED_SERVICES:
    import services.order_service as s_order
    import services.product_service as s_prod
    import services.logistics_service as s_logi

    def _start(mod):
        HTTPServerThread = ThreadingHTTPServer(("127.0.0.1", mod.PORT), mod.H)
        threading.Thread(target=HTTPServerThread.serve_forever, daemon=True).start()

    for m in (s_order, s_prod, s_logi):
        _start(m)
    time.sleep(0.8)

# ---- 2. 业务依赖(在微服务起来后再导入)----
from app import serve_struct
from memory import Memory
SESSIONS = {}   # user_id -> Memory(每个用户一份会话记忆)

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
METRICS_LOCK = threading.Lock()
CHAT_BUCKETS = (0.5, 1, 2, 5, 10, 30, 60, 120)
METRICS = {
    "http_requests": {},
    "chat_requests": {},
    "chat_latency_sum": 0.0,
    "chat_latency_count": 0,
    "chat_latency_buckets": {bucket: 0 for bucket in CHAT_BUCKETS},
}


def _metric_inc(group, labels, value=1):
    key = tuple(sorted(labels.items()))
    with METRICS_LOCK:
        METRICS[group][key] = METRICS[group].get(key, 0) + value


def _observe_chat_latency(seconds):
    with METRICS_LOCK:
        METRICS["chat_latency_sum"] += seconds
        METRICS["chat_latency_count"] += 1
        for bucket in CHAT_BUCKETS:
            if seconds <= bucket:
                METRICS["chat_latency_buckets"][bucket] += 1


def _labels_to_text(items):
    if not items:
        return ""
    parts = [f'{key}="{str(value).replace(chr(34), chr(39))}"' for key, value in items]
    return "{" + ",".join(parts) + "}"


def _render_metrics():
    lines = [
        "# HELP service_agent_http_requests_total HTTP requests handled by the web gateway.",
        "# TYPE service_agent_http_requests_total counter",
    ]
    with METRICS_LOCK:
        http_requests = dict(METRICS["http_requests"])
        chat_requests = dict(METRICS["chat_requests"])
        latency_sum = METRICS["chat_latency_sum"]
        latency_count = METRICS["chat_latency_count"]
        latency_buckets = dict(METRICS["chat_latency_buckets"])

    for labels, value in sorted(http_requests.items()):
        lines.append(f"service_agent_http_requests_total{_labels_to_text(labels)} {value}")

    lines.extend([
        "# HELP service_agent_chat_requests_total Chat requests grouped by routed intent.",
        "# TYPE service_agent_chat_requests_total counter",
    ])
    for labels, value in sorted(chat_requests.items()):
        lines.append(f"service_agent_chat_requests_total{_labels_to_text(labels)} {value}")

    lines.extend([
        "# HELP service_agent_chat_latency_seconds Chat request latency in seconds.",
        "# TYPE service_agent_chat_latency_seconds histogram",
    ])
    cumulative = 0
    for bucket in CHAT_BUCKETS:
        cumulative = latency_buckets[bucket]
        lines.append(f'service_agent_chat_latency_seconds_bucket{{le="{bucket}"}} {cumulative}')
    lines.append(f'service_agent_chat_latency_seconds_bucket{{le="+Inf"}} {latency_count}')
    lines.append(f"service_agent_chat_latency_seconds_sum {latency_sum}")
    lines.append(f"service_agent_chat_latency_seconds_count {latency_count}")
    return "\n".join(lines) + "\n"

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        data = body.encode("utf-8") if isinstance(body, str) else body
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if self.path == "/metrics":
            _metric_inc("http_requests", {"method": "GET", "path": "/metrics", "status": "200"})
            return self._send(200, _render_metrics(), "text/plain; version=0.0.4; charset=utf-8")
        path = "index.html" if self.path in ("/", "") else self.path.lstrip("/")
        fp = os.path.join(WEB_DIR, os.path.basename(path))
        if os.path.isfile(fp):
            ctype = "text/html; charset=utf-8" if fp.endswith(".html") else "text/plain; charset=utf-8"
            with open(fp, "rb") as f:
                _metric_inc("http_requests", {"method": "GET", "path": "/" if self.path in ("/", "") else "/asset", "status": "200"})
                return self._send(200, f.read(), ctype)
        _metric_inc("http_requests", {"method": "GET", "path": "other", "status": "404"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/chat":
            return self._send(404, {"error": "unknown api"})
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(n) or "{}")
        except Exception:
            return self._send(400, {"error": "bad json"})
        uid = req.get("user_id", "u001")
        msg = (req.get("message") or "").strip()
        if not msg:
            _metric_inc("http_requests", {"method": "POST", "path": "/api/chat", "status": "400"})
            return self._send(400, {"error": "empty message"})
        mem = SESSIONS.setdefault(uid, Memory())
        started = time.perf_counter()
        try:
            result = serve_struct(uid, msg, memory=mem)
            elapsed = time.perf_counter() - started
            _observe_chat_latency(elapsed)
            _metric_inc("http_requests", {"method": "POST", "path": "/api/chat", "status": "200"})
            _metric_inc("chat_requests", {"intent": result.get("intent", "unknown")})
            self._send(200, result)
        except Exception as exc:
            elapsed = time.perf_counter() - started
            _observe_chat_latency(elapsed)
            _metric_inc("http_requests", {"method": "POST", "path": "/api/chat", "status": "500"})
            _metric_inc("chat_requests", {"intent": "error"})
            self._send(500, {"error": str(exc)})

if __name__ == "__main__":
    print("=" * 56)
    print("  智能服务助理 已启动")
    if EMBEDDED_SERVICES:
        print("  业务微服务:8001 / 8002 / 8003 (后台内嵌模式)")
    else:
        print("  业务微服务:使用外部 ORDER_URL / PRODUCT_URL / LOGISTICS_URL")
    print("  请用浏览器打开:  http://localhost:8000")
    print("  按 Ctrl+C 退出")
    print("=" * 56)
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
