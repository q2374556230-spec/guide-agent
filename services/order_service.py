# -*- coding: utf-8 -*-
"""订单微服务(端口 8001)。仅用标准库 http.server,零依赖。
契约:
  GET  /orders/{order_id}          -> 订单详情 | 404
  POST /orders/{order_id}/refund   -> 发起退款,状态置为"退款中"
生产中可平滑替换为 FastAPI;这里用标准库以保证零配置即可运行。"""
import json, sys, os, re
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data import ORDERS

PORT = 8001

class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # 静音默认日志
        pass

    def do_GET(self):
        mu = re.match(r"/users/(\w+)/orders$", self.path)   # 按用户查全部订单
        if mu:
            uid = mu.group(1)
            return self._send(200, [o for o in ORDERS.values() if o.get("user") == uid])
        m = re.match(r"/orders/(\w+)$", self.path)
        if m:
            o = ORDERS.get(m.group(1))
            return self._send(200, o) if o else self._send(404, {"error": "订单不存在"})
        self._send(404, {"error": "未知路径"})

    def do_POST(self):
        m = re.match(r"/orders/(\w+)/refund$", self.path)
        if m:
            o = ORDERS.get(m.group(1))
            if not o:
                return self._send(404, {"error": "订单不存在"})
            o["status"] = "退款中"
            return self._send(200, {"order_id": m.group(1), "status": "退款中",
                                    "msg": "退款申请已提交,1-3个工作日原路退回"})
        self._send(404, {"error": "未知路径"})

if __name__ == "__main__":
    print(f"[order-service] 启动于 http://localhost:{PORT}")
    HTTPServer(("0.0.0.0", PORT), H).serve_forever()
