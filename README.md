# 校园电商/外卖智能服务助理 —— 可运行参考系统

本仓库是《基于 Agent 的服务工程应用实践》四次课的**完整可运行参考系统**。
三层架构:**业务流程(BPMN)→ 微服务(http.server)→ Agent 智能编排**。

## 特点:零依赖、离线可跑、可复现
- 仅用 **Python 标准库 + numpy + requests**(沙箱/无外网环境也能跑)。
- 大模型默认走 `MockLLM` 教学桩(确定性、可复现);配置 `OPENAI_API_KEY` 后**同一套代码**自动切换为真实大模型。

## 目录
```
service-agent-lab/
├── data.py                  # 模拟业务数据(订单/商品/物流/政策)
├── llm.py                   # LLM 客户端(真实 OpenAI 兼容 / MockLLM 自动切换)
├── services/                # 微服务(标准库 http.server,各占一端口)
│   ├── order_service.py     #   8001  订单(查询/退款)
│   ├── product_service.py   #   8002  商品
│   └── logistics_service.py #   8003  物流
├── tools.py                 # 工具层:把微服务包装成 Agent 工具 + 工具契约
├── rag.py                   # RAG:numpy 字符 n-gram 向量检索
├── memory.py                # 会话记忆:滑动窗口/摘要/长期画像
├── agent.py                 # 意图识别 / ReAct / 多Agent 路由+专家
├── guardrails.py            # 护栏:防注入/防越权/PII脱敏
├── evaluate.py              # 离线评测 + LLM-as-judge
└── app.py                   # 端到端集成:护栏→编排→脱敏→追踪
```

## 快速开始
```bash
# 1) 启动三个微服务(后台)
python3 services/order_service.py &
python3 services/product_service.py &
python3 services/logistics_service.py &

# 2) 跑各层演示
python3 agent.py        # 不直接运行;在实验中按需 import
python3 rag.py          # RAG 检索排序
python3 evaluate.py     # 评测打分(默认 80%)
POLICY_K=3 python3 evaluate.py   # 调大检索→100%(评测驱动改进)
python3 app.py          # 端到端:护栏+多Agent+脱敏+追踪
```

## 切换到真实大模型(学生在自己电脑上)
```bash
export OPENAI_API_KEY=sk-xxxx
export OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export CHAT_MODEL=qwen-plus
# 之后所有脚本调用的就是真实模型,代码无需改动
```

## 云原生 & 对接现有系统
所有地址/密钥都用环境变量注入(12-Factor),易容器化、易集成:
```bash
docker compose up --build        # 每个微服务一个容器,按服务名互相发现
```
- 对接你已有的系统:把 `ORDER_URL / PRODUCT_URL / LOGISTICS_URL` 指向你的真实微服务即可,上层不动。
- 用企业模型网关:把 `OPENAI_BASE_URL` 指向网关地址。
- 已提供 `Dockerfile`、`docker-compose.yml`、`k8s/order-service.yaml`(部署示例)。

## 升级到生产栈(可选)
- 微服务 `http.server` → **FastAPI**(契约/校验/文档更完善)。
- 向量检索 numpy n-gram → **嵌入模型 + Chroma/FAISS**。
- 多 Agent 编排手写 → **LangGraph**(显式状态图、检查点、人审)。
- 工具接入 → **MCP**(标准化、可复用)。
概念与代码骨架一一对应,迁移成本低。
