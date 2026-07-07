# Guide Agent: 电商服务智能体实验项目

本项目是一个面向《服务工程与应用实践》的电商服务 Agent 实验系统。项目在原有订单查询、物流查询、商品咨询、售后 BPMN 流程的基础上，新增了“基于商品证据包的真实 LLM 个性化导购 Agent”，并补充了 Docker、Jenkins、Kubernetes、Secret 注入和自动化部署验证流程。

项目重点不是重写原系统，而是在保留原有功能的前提下，增强“购买决策/导购”路径：给 LLM 配备导购工具集，让模型基于商品信息、评价摘要、销量信号、店铺售后信息和用户偏好进行推荐推理。

## 核心功能

- 订单查询：查询订单状态、金额、商品等信息。
- 物流查询：通过工具调用查询物流进度和超时补偿说明。
- 普通商品咨询：查询商品价格、库存、基础信息。
- 售后流程：保留 `aftersale.bpmn`，通过 BPMN 引擎执行退款/售后流程。
- 增强导购：基于 `shopping_research_agent.py` 构造 evidence 证据包，再由真实 LLM 或 fallback 规则输出个性化推荐。
- Web Trace：Web 页面展示 Agent 路由、工具调用、导购证据收集和推理链路。
- DevOps：支持 Docker Compose、Jenkins Pipeline、Kubernetes 部署和 Smoke Test。

## 导购创新路径

用户输入购买需求后，例如：

```text
我想买一个300元以内的蓝牙耳机，主要在宿舍和图书馆用，想要降噪好一点，别漏音，续航别太差
```

系统执行链路：

```text
Web 输入
→ server.py
→ app.py / agent.py
→ expert_shopping
→ shopping_research_agent.py
→ 需求理解
→ collect_product_candidates
→ collect_review_summary
→ collect_sales_signal
→ collect_store_profile
→ 构造 evidence 证据包
→ 真实 LLM 基于证据推理
→ 输出 Top3 推荐、风险提醒、不推荐项和数据来源说明
```

如果没有配置真实 LLM，或 LLM 调用失败，系统会自动回退到 `tools.recommend_products` 规则推荐，保证演示稳定。

## 运行环境

建议环境：

- Python 3.11 或 3.12
- Docker Desktop
- kubectl
- Jenkins on Windows
- 可选：OpenAI-compatible LLM API Key

安装依赖：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 本地运行

启动 Web 服务：

```powershell
.\.venv\Scripts\python.exe server.py
```

访问：

```text
http://127.0.0.1:8000
```

常用验证命令：

```powershell
.\.venv\Scripts\python.exe -m py_compile agent.py tools.py shopping_research_agent.py evaluate.py server.py
.\.venv\Scripts\python.exe evaluate.py
```

单独测试导购 Agent：

```powershell
.\.venv\Scripts\python.exe -c "from shopping_research_agent import shopping_research_agent; r=shopping_research_agent('我想买一个300元以内的蓝牙耳机，图书馆用，重视降噪和续航，不想漏音'); print('\n'.join(r['trace'])); print(r['answer'])"
```

## 真实 LLM 配置

本地开发可创建 `.env`，但不要提交到 GitHub：

```text
OPENAI_API_KEY=你的真实Key
OPENAI_BASE_URL=https://api.deepseek.com
CHAT_MODEL=deepseek-v4-flash
SHOPPING_AGENT_MODE=auto
PRODUCT_SOURCE=demo
```

`llm.py` 会根据环境变量自动切换：

```text
有 OPENAI_API_KEY → real LLM
无 OPENAI_API_KEY → MockLLM / 规则 fallback
```

## Docker Compose

本机容器化运行：

```powershell
docker compose up -d --build
```

Compose 会启动：

```text
agent-app
order-service
product-service
logistics-service
```

查看状态：

```powershell
docker compose ps
```

## Kubernetes 部署

K8s 资源位于 `k8s/`：

```text
k8s/
  namespace.yaml
  config.yaml
  agent-app.yaml
  order-service.yaml
  product-service.yaml
  logistics-service.yaml
  kustomization.yaml
  llm-secret.example.yaml
```

部署后查看状态：

```powershell
kubectl -n service-agent-lab get pods
kubectl -n service-agent-lab get svc
kubectl -n service-agent-lab get deploy
```

访问 Web：

```powershell
kubectl -n service-agent-lab port-forward svc/agent-app 8000:8000
```

浏览器打开：

```text
http://127.0.0.1:8000
```

K8s 中启用真实 LLM：

```powershell
kubectl -n service-agent-lab create secret generic service-agent-llm-secret --from-env-file=.env --dry-run=client -o yaml | kubectl apply -f -
kubectl -n service-agent-lab rollout restart deployment/agent-app
kubectl -n service-agent-lab rollout status deployment/agent-app
```

验证容器内 LLM 后端：

```powershell
kubectl -n service-agent-lab exec deploy/agent-app -- python -c "import os,llm; print('key已读取=', bool(os.getenv('OPENAI_API_KEY'))); print('后端=', llm.BACKEND)"
```

## Jenkins 自动化部署

`Jenkinsfile` 已适配 Windows Jenkins，核心流程：

```text
Checkout
→ Check Tools
→ Prepare image tag
→ 创建 .venv
→ pip install
→ py_compile
→ evaluate.py
→ docker build
→ 按 DEPLOY_TARGET 部署
→ smoke test
```

流水线参数：

```text
DEPLOY_TARGET=none     只测试和构建镜像
DEPLOY_TARGET=compose  部署到 Docker Compose
DEPLOY_TARGET=k8s      推送镜像并部署到 Kubernetes
```

Jenkins 需要的凭据：

```text
docker-registry-credentials
kubeconfig-service-agent-lab
```

如果本地 Jenkins 没有公网地址，可以先手动点击 `Build with Parameters` 完成课程演示。

## 服务质量评价

项目提供轻量级监控脚本和评价说明，用于完成课程中的服务质量评价实践。

运行监控：

```powershell
.\.venv\Scripts\python.exe scripts\quality_monitor.py --base-url http://127.0.0.1:8000 --rounds 5 --concurrency 2
```

脚本会采集：

```text
请求总数、成功率、状态码分布、平均延迟、P50/P95 延迟、最大延迟、吞吐率
```

并尝试读取：

```text
docker compose ps
docker stats --no-stream
kubectl get pods/svc/deploy
kubectl top pods
```

结果输出到：

```text
reports/quality/<timestamp>/summary.md
reports/quality/<timestamp>/metrics.json
```

详细说明见 `docs/SERVICE_QUALITY.md`。

## 目录结构

```text
service-agent-lab/
  agent.py                    # 意图路由、专家分流、ReAct/工具路径
  app.py                      # Web 后端调用入口封装
  server.py                   # Web 服务入口
  llm.py                      # 真实 LLM / MockLLM 自动切换
  tools.py                    # 工具契约和业务工具
  shopping_research_agent.py  # 个性化导购 Agent
  bpmn_engine.py              # BPMN 执行引擎
  bpmn_handlers.py            # 售后 BPMN handlers
  shopping_bpmn_handlers.py   # 实验三导购 BPMN handlers
  data.py                     # Demo 业务数据
  evaluate.py                 # 自动化评测
  Jenkinsfile                 # Jenkins CI/CD Pipeline
  Dockerfile
  docker-compose.yml
  requirements.txt

  services/                   # 订单、商品、物流微服务
  flows/                      # BPMN 流程文件
  web/                        # Web 页面和展示资源
  k8s/                        # Kubernetes 部署资源
  scripts/                    # 部署和 smoke test 脚本
  docs/                       # 运行、部署、BPMN、CI/CD 文档
  reports/                    # 实验报告
  skills/                     # 项目形式化 Skill 材料
  java_integration/           # Java 集成示例
```

## 安全说明

- `.env` 不应提交到 GitHub。
- API Key 使用本地 `.env` 或 K8s Secret 注入。
- 如果 Key 曾经出现在聊天记录、截图或终端公开日志中，建议在供应商后台轮换。

## 项目总结

本项目实现了一个可运行、可展示、可部署的服务工程 Agent 系统：原有订单、物流、商品咨询和售后 BPMN 功能保持不变；新增导购 Agent 通过工具集收集商品证据，并由真实 LLM 基于 evidence 进行个性化推荐推理；工程侧补齐了 Docker、Jenkins、Kubernetes、Secret 管理和自动化测试部署链路，形成从开发到运行维护的完整闭环。
