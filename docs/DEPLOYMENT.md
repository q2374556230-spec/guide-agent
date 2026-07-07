# 部署与运维说明

本项目已提供本地运行、Docker Compose、Jenkins Pipeline 和 Kubernetes 示例配置。真实 LLM API Key 不写入镜像或仓库,通过环境变量、Compose `.env`、Jenkins Credentials 或 Kubernetes Secret 注入。

## 1. 本地运行

```powershell
.\.venv\Scripts\python.exe server.py
```

浏览器打开:

```text
http://localhost:8000
```

本地模式下 `server.py` 会内嵌启动订单、商品、物流三个微服务。

## 2. Docker Compose 部署

推荐使用脚本:

```powershell
.\scripts\deploy_compose.ps1
```

也可以手动执行:

```powershell
docker compose up -d --build
docker compose ps
```

访问:

```text
http://localhost:8000
```

部署后冒烟测试:

```powershell
python scripts\smoke_test.py
```

停止服务:

```powershell
.\scripts\stop_compose.ps1
```

## 3. Jenkins Pipeline

仓库根目录提供 `Jenkinsfile`,主要阶段包括:

```text
Checkout -> Install -> Static Check -> Test -> Build Image -> Deploy Compose -> Smoke Test
```

真实 Jenkins 环境中建议通过 Jenkins Credentials 注入:

```text
OPENAI_API_KEY
OPENAI_BASE_URL
OPENAI_MODEL
```

无真实 LLM Key 时系统仍会使用 Mock/规则 fallback,保证部署验证可通过。

## 4. Kubernetes 部署

先构建本地镜像:

```powershell
docker build -t service-agent-lab:latest .
```

部署资源:

```powershell
kubectl apply -f k8s/
kubectl get pods
kubectl get svc
```

示例配置包含:

```text
k8s/config.yaml
k8s/order-service.yaml
k8s/product-service.yaml
k8s/logistics-service.yaml
k8s/agent-app.yaml
k8s/llm-secret.example.yaml
```

默认 `agent-app` 使用 NodePort `30080` 暴露服务。具体访问地址取决于本地或集群环境。
`llm-secret.example.yaml` 只是密钥模板,不参与默认 `kubectl apply -k k8s` 部署。真实 API Key 应通过 Kubernetes Secret 或 Jenkins Credentials 注入。

## 5. 运维观测建议

演示阶段可重点截图:

1. `docker compose ps` 显示四个服务运行。
2. `python scripts\smoke_test.py` 通过。
3. Web 页面 `http://localhost:8000` 可访问。
4. 导购 trace 显示 evidence 工具链。
5. `kubectl get pods` / `kubectl get svc` 显示 K8s 资源。

生产级扩展可增加 LLM 调用次数、fallback 比例、服务响应耗时、BPMN 执行成功率等指标。
