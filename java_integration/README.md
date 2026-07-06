# 与 Java 系统集成(参考示例)

本系统对外只用 **HTTP + JSON** 和 **标准 BPMN 2.0 文件**,所以与 Java 集成几乎零摩擦——
集成点在 HTTP 边界与 .bpmn 文件,**不用改 Agent 的 Python 代码**。

> 说明:以下为标准 Spring Boot / Camunda 参考代码,用于教学对接演示,未在本仓库环境编译。

## 方式一:Agent 调用你现有的 Java 微服务
Agent 的工具层(tools.py)只认 URL。把环境变量指向你的 Spring Boot 服务即可:
```bash
export ORDER_URL=http://localhost:8080      # 指向 OrderServiceController
export PRODUCT_URL=http://your-product:8080
python3 server.py                            # Agent 即调用你的 Java 服务
```
只要 Java 返回的 JSON 字段与契约一致(`order_id/amount/status/eta` 等)即可。
示例:`OrderServiceController.java`。

## 方式二:Java 后端调用 Agent 服务
`server.py` 的 `POST /api/chat` 是标准 REST。Java 用 JDK 自带 HttpClient 即可调用:
```bash
# 先启动 Agent
python3 server.py
# 再编译运行客户端
javac java_integration/AgentClient.java -d out
java -cp out com.example.AgentClient
```
示例:`AgentClient.java`(返回 `{reply,intent,trace,latency}`)。生产中建议用 Spring `WebClient` + Jackson。

## 方式三:用 Java BPMN 引擎运行 aftersale.bpmn
`flows/aftersale.bpmn` 是标准 BPMN 2.0,**Camunda / Flowable / Activiti 可直接加载**。
把流程里的"智能步骤"做成 ServiceTask,委托给 Java 类去调 Agent:
```xml
<bpmn:serviceTask id="Task_AutoRefund" name="自动发起退款"
                  camunda:class="com.example.RefundAgentDelegate"/>
```
示例:`RefundAgentDelegate.java`。这样 Camunda(Java)负责流程编排与治理,
AI/对话/RAG 步骤交给 Agent 服务——是 production 常见架构。

## 方式四(可选):纯 JVM 方案
若希望整条链路都在 Java 内,可用 **Spring AI** 或 **LangChain4j** 重写 Agent
(同样支持 OpenAI 兼容接口、工具调用、RAG、MCP)。一般无需如此,方式一/二成本最低。

## 对比
| 方式 | 集成点 | Java 侧技术 | 适用 |
|---|---|---|---|
| 一 Agent 调 Java 微服务 | 环境变量 URL | Spring Boot REST | 已有业务微服务 |
| 二 Java 调 Agent | POST /api/chat | HttpClient / WebClient | Java 为主应用 |
| 三 Java 引擎跑流程 | .bpmn + ServiceTask | Camunda / Flowable | 需要企业级流程治理 |
| 四 纯 JVM 重写 Agent | OpenAI 兼容 API | Spring AI / LangChain4j | 统一技术栈 |
