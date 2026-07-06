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
from http.server import BaseHTTPRequestHandler, HTTPServer

# ---- 1. 本地模式:后台启动业务微服务 ----
# Docker Compose / Kubernetes 中由独立容器启动微服务,设置
# EMBEDDED_SERVICES=false 即可关闭这里的内嵌服务。
EMBEDDED_SERVICES = os.getenv("EMBEDDED_SERVICES", "true").lower() not in ("0", "false", "no")

if EMBEDDED_SERVICES:
    import services.order_service as s_order
    import services.product_service as s_prod
    import services.logistics_service as s_logi

    def _start(mod):
        HTTPServerThread = HTTPServer(("127.0.0.1", mod.PORT), mod.H)
        threading.Thread(target=HTTPServerThread.serve_forever, daemon=True).start()

    for m in (s_order, s_prod, s_logi):
        _start(m)
    time.sleep(0.8)

# ---- 2. 业务依赖(在微服务起来后再导入)----
from app import serve_struct
from memory import Memory
SESSIONS = {}   # user_id -> Memory(每个用户一份会话记忆)

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = "index.html" if self.path in ("/", "") else self.path.lstrip("/")
        fp = os.path.join(WEB_DIR, os.path.basename(path))
        if os.path.isfile(fp):
            ctype = "text/html; charset=utf-8" if fp.endswith(".html") else "text/plain; charset=utf-8"
            with open(fp, "rb") as f:
                return self._send(200, f.read(), ctype)
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
            return self._send(400, {"error": "empty message"})
        mem = SESSIONS.setdefault(uid, Memory())
        result = serve_struct(uid, msg, memory=mem)
        self._send(200, result)

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
    HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
