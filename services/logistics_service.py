# -*- coding: utf-8 -*-
"""物流微服务(端口 8003)。
契约:
  GET /track/{order_id}  -> 配送状态/预计时间/快递单号 | 404"""
import json, sys, os, re
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data import ORDERS

PORT = 8003

class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

    def do_GET(self):
        m = re.match(r"/track/(\w+)$", self.path)
        if m:
            o = ORDERS.get(m.group(1))
            if not o:
                return self._send(404, {"error": "订单不存在"})
            timed_out = o.get("type") == "外卖" and o.get("placed_min_ago", 0) > 30 \
                        and o.get("status") == "配送中"
            return self._send(200, {"order_id": m.group(1), "status": o.get("status"),
                                    "eta": o.get("eta"), "tracking": o.get("tracking"),
                                    "carrier": o.get("carrier"), "timed_out": timed_out})
        self._send(404, {"error": "未知路径"})

if __name__ == "__main__":
    print(f"[logistics-service] 启动于 http://localhost:{PORT}")
    HTTPServer(("0.0.0.0", PORT), H).serve_forever()
