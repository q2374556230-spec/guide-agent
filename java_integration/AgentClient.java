package com.example;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

/**
 * 方式二:Java 后端调用 Python Agent 服务(POST /api/chat)。
 * 零第三方依赖,仅用 JDK 11+ 自带的 java.net.http。
 *
 * 运行:javac AgentClient.java && java com.example.AgentClient
 *      (需先启动 Agent:python3 server.py;可用 AGENT_URL 指定地址)
 */
public class AgentClient {

    private static final HttpClient HTTP = HttpClient.newHttpClient();
    private static final String AGENT =
            System.getenv().getOrDefault("AGENT_URL", "http://localhost:8000");

    /** 返回 Agent 的 JSON:{"reply":...,"intent":...,"trace":...,"latency":...} */
    public static String chat(String message, String userId) throws Exception {
        String body = "{\"message\":" + quote(message) + ",\"user_id\":" + quote(userId) + "}";
        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(AGENT + "/api/chat"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();
        HttpResponse<String> resp = HTTP.send(req, HttpResponse.BodyHandlers.ofString());
        return resp.body();
    }

    private static String quote(String s) {
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }

    public static void main(String[] args) throws Exception {
        // 生产中建议用 Spring WebClient + Jackson 解析 JSON;此处用内置 HttpClient 演示
        System.out.println(chat("订单20260601001超时有补偿吗?", "u001"));
    }
}
