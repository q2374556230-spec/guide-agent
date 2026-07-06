# -*- coding: utf-8 -*-
"""商品微服务(端口 8002)。
契约:
  GET /products            -> 全部商品列表
  GET /products/search?q=关键词&max_price=价格 -> 导购候选商品
  GET /products/detail/{product_id} -> 扩展商品详情
  GET /products/{name}     -> 单个商品 | 404"""
import json, sys, os, re, urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data import PRODUCTS, PRODUCTS_EXT

PORT = 8002

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
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        if path == "/products":
            return self._send(200, list(PRODUCTS.values()))
        if path == "/products/search":
            q = (qs.get("q", [""])[0] or "").strip()
            max_price = None
            if qs.get("max_price", [""])[0]:
                try:
                    max_price = float(qs["max_price"][0])
                except ValueError:
                    max_price = None
            return self._send(200, _search_products(q, max_price))
        m_detail = re.match(r"/products/detail/(.+)$", path)
        if m_detail:
            pid = urllib.parse.unquote(m_detail.group(1))
            p = next((item for item in PRODUCTS_EXT if item["product_id"] == pid), None)
            return self._send(200, p) if p else self._send(404, {"error": "无此商品"})
        m = re.match(r"/products/(.+)$", path)
        if m:
            name = urllib.parse.unquote(m.group(1))
            p = PRODUCTS.get(name)
            return self._send(200, p) if p else self._send(404, {"error": "无此商品"})
        self._send(404, {"error": "未知路径"})

def _search_products(q, max_price=None):
    words = [w for w in re.split(r"[\s,，、]+", q or "") if w]
    results = []
    for p in PRODUCTS_EXT:
        if max_price is not None and p.get("price", 0) > max_price:
            continue
        haystack = " ".join([
            p.get("name", ""),
            p.get("category", ""),
            " ".join(p.get("tags", [])),
            " ".join(p.get("scenarios", [])),
        ])
        if words and not any(w in haystack for w in words):
            continue
        results.append(p)
    return sorted(results, key=lambda p: (p.get("price", 0), -p.get("rating", 0), -p.get("monthly_sales", 0)))

if __name__ == "__main__":
    print(f"[product-service] 启动于 http://localhost:{PORT}")
    HTTPServer(("0.0.0.0", PORT), H).serve_forever()
