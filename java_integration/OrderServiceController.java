package com.example;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.util.*;

/**
 * 方式一:用你的 Java(Spring Boot)微服务替换演示微服务。
 * 只要返回的 JSON 字段与契约一致(order_id/amount/status/eta…),
 * Python Agent 把环境变量 ORDER_URL 指向本服务即可直接调用,Agent 代码无需改动。
 *
 * 运行:Spring Boot 项目中放入本类,启动后监听如 8080;
 *      在 Agent 侧:export ORDER_URL=http://localhost:8080
 */
@RestController
@RequestMapping("/orders")
public class OrderServiceController {

    private final Map<String, Map<String, Object>> orders = new HashMap<>();

    public OrderServiceController() {
        Map<String, Object> o = new HashMap<>();
        o.put("order_id", "20260601001");
        o.put("user", "u001");
        o.put("amount", 32.5);
        o.put("status", "配送中");
        o.put("eta", "12分钟");
        o.put("type", "外卖");
        orders.put("20260601001", o);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Object> get(@PathVariable String id) {
        Map<String, Object> o = orders.get(id);
        if (o == null) {
            return ResponseEntity.status(404).body(Map.of("error", "订单不存在"));
        }
        return ResponseEntity.ok(o);
    }

    @PostMapping("/{id}/refund")
    public Map<String, Object> refund(@PathVariable String id) {
        Map<String, Object> o = orders.get(id);
        if (o != null) {
            o.put("status", "退款中");
        }
        return Map.of("order_id", id, "status", "退款中",
                      "msg", "退款申请已提交,1-3个工作日原路退回");
    }
}
