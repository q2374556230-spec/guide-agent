# 服务质量监控与评价说明

本实践用于完成“服务质量评价”部分：利用工具监控服务关键指标参数，并基于监控数据评价服务效率、可用性、健壮性和吞吐率。

## 1. 监控工具

本项目采用自动化监控工具组合，适合课程演示和截图取证。

- `Prometheus`: 自动抓取服务 `/metrics` 指标，包括请求量、成功率、接口延迟、不同意图调用量等。
- `Grafana`: 连接 Prometheus 并展示服务质量仪表盘。
- `cAdvisor`: 采集 Docker 容器 CPU、内存、网络等资源消耗指标。
- `scripts/quality_monitor.py`: 项目自带压测/采样脚本，主动产生订单、物流、售后、导购请求，并生成 `metrics.json` 与 `summary.md`。
- `docker compose ps`: 查看 Docker Compose 服务运行状态。
- `docker stats --no-stream`: 获取容器 CPU、内存、网络、Block I/O 等资源消耗。
- `kubectl get pods/svc/deploy`: 查看 Kubernetes 服务、Pod、Deployment 可用状态。
- `kubectl top pods`: 获取 K8s Pod CPU、内存指标。该命令依赖 metrics-server；如果本机集群没有启用 metrics-server，可截图 `kubectl get pods` 和监控脚本结果作为替代。
- Jenkins Console Output: 查看自动化构建、测试、镜像构建、部署和 smoke test 结果。

## 2. 指标数据获取方式

先确保服务已经运行。

本地运行：

```powershell
.\.venv\Scripts\python.exe server.py
```

Kubernetes 运行：

```powershell
kubectl -n service-agent-lab port-forward svc/agent-app 8000:8000
```

启动自动化监控工具：

Docker Compose 方式运行业务服务和监控工具：

```powershell
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d --build
```

如果业务服务运行在 Kubernetes 中，则先执行上面的 `kubectl port-forward`，再只启动监控工具：

```powershell
docker compose -f docker-compose.monitoring.yml up -d
```

访问监控界面：

```text
Prometheus: http://127.0.0.1:9090
Grafana:    http://127.0.0.1:3000  用户名/密码 admin/admin
cAdvisor:  http://127.0.0.1:8081
```

Prometheus Targets 页面：

```text
http://127.0.0.1:9090/targets
```

可查看 `guide-agent-app-compose`、`guide-agent-app-k8s-port-forward`、`cadvisor` 等监控目标是否为 `UP`。

执行服务质量监控：

```powershell
.\.venv\Scripts\python.exe scripts\quality_monitor.py --base-url http://127.0.0.1:8000 --rounds 5 --concurrency 2 --timeout 90
```

输出文件位置示例：

```text
reports/quality/20260707_153000/
  metrics.json
  summary.md
```

其中：

- `metrics.json`: 原始监控数据，包含每次请求的成功/失败、状态码、延迟、intent、资源命令输出。
- `summary.md`: 服务质量评价摘要，适合直接放入报告。

Docker 资源数据：

```powershell
docker compose ps
docker stats --no-stream
```

Kubernetes 运行状态：

```powershell
kubectl -n service-agent-lab get pods -o wide
kubectl -n service-agent-lab get svc
kubectl -n service-agent-lab get deploy
kubectl -n service-agent-lab top pods
```

Prometheus 常用查询语句：

```promql
sum(rate(service_agent_http_requests_total[1m]))
histogram_quantile(0.95, service_agent_chat_latency_seconds_bucket)
sum by (intent) (increase(service_agent_chat_requests_total[10m]))
sum(rate(service_agent_http_requests_total{status="200"}[5m])) / sum(rate(service_agent_http_requests_total[5m]))
```

Grafana 已预置仪表盘：

```text
Guide Agent / Guide Agent 服务质量监控
```

仪表盘展示 HTTP 吞吐率、对话接口延迟、各意图调用量、接口成功率、容器 CPU 使用和容器内存使用。

Jenkins 数据：

```text
Jenkins Job -> Build -> Console Output
```

重点截图 `Static Check`、`Test`、`Build Image`、`Deploy to Kubernetes`、`Smoke Test` 阶段通过。

## 3. 监控指标说明

| 指标类型 | 指标项 | 获取方式 | 评价含义 |
| --- | --- | --- | --- |
| 资源参数 | CPU 使用率 | Grafana / Prometheus / cAdvisor / `docker stats` / `kubectl top pods` | 判断服务资源消耗是否过高 |
| 资源参数 | 内存使用量 | Grafana / Prometheus / cAdvisor / `docker stats` / `kubectl top pods` | 判断服务是否存在明显内存压力 |
| 调用参数 | 总请求数 | Prometheus / Grafana / `quality_monitor.py` | 压测/监控样本规模 |
| 调用参数 | 成功请求数 | Prometheus / Grafana / `quality_monitor.py` | 计算服务可用性 |
| 调用参数 | 失败请求数和状态码 | Prometheus / Grafana / `quality_monitor.py` | 分析错误分布和健壮性 |
| 时间参数 | 平均延迟 | Prometheus / Grafana / `quality_monitor.py` | 评价整体响应效率 |
| 时间参数 | P50/P95 延迟 | Prometheus / Grafana / `quality_monitor.py` | 评价典型响应和尾部延迟 |
| 吞吐参数 | RPS | Prometheus / Grafana / `quality_monitor.py` | 评价单位时间处理能力 |
| 可用状态 | Pod Ready/Restart | `kubectl get pods` | 判断服务实例是否稳定运行 |
| 部署状态 | Deployment Ready | `kubectl get deploy` | 判断滚动部署是否成功 |

## 4. 服务质量评价方法

### 4.1 效率

效率主要看接口响应时间。

评价公式：

```text
平均延迟 = 所有请求耗时总和 / 请求数
P95 延迟 = 95% 请求能够完成的最大耗时
```

建议评价标准：

- P95 <= 2000ms: 效率较好。
- 2000ms < P95 <= 5000ms: 可接受，真实 LLM 调用可能导致延迟升高。
- P95 > 5000ms: 需要优化，例如减少 LLM 调用、增加缓存或异步处理。

### 4.2 可用性

可用性主要看成功率。

评价公式：

```text
可用性 = 成功请求数 / 总请求数
```

建议评价标准：

- >= 99%: 优秀。
- >= 95%: 良好。
- < 95%: 需要排查服务异常、网络错误或 LLM fallback。

### 4.3 健壮性

健壮性主要看失败请求、错误类型和 fallback 能力。

本项目的健壮性设计：

- 无真实 LLM Key 时自动使用 MockLLM / 规则推荐。
- 导购真实 LLM 调用失败时回退到 `tools.recommend_products`。
- K8s 使用 Deployment 管理 Pod，异常后可自动重启。
- Jenkins 中执行 `evaluate.py` 和 smoke test，避免错误版本部署。

评价方式：

```text
失败请求数越少越好；
出现 LLM 异常时，系统仍能 fallback 并返回可用结果，说明健壮性较好。
```

### 4.4 吞吐率

吞吐率表示单位时间处理能力。

评价公式：

```text
吞吐率 RPS = 总请求数 / 总耗时秒数
```

课程演示阶段不追求高并发，主要证明系统能稳定处理订单、物流、售后和导购多类请求。真实生产环境可进一步使用 Locust、JMeter 或 K6 做并发压测。

## 5. 建议截图清单

报告中建议放以下截图：

1. `scripts/quality_monitor.py` 运行完成的终端输出，显示成功率、吞吐率和 P95 延迟。
2. Prometheus `Targets` 页面，显示 `guide-agent` 和 `cadvisor` 采集目标状态。
3. Prometheus Graph 页面，展示 P95 延迟或 RPS 查询结果。
4. Grafana `Guide Agent 服务质量监控` 仪表盘。
5. cAdvisor 容器资源页面。
6. `reports/quality/.../summary.md` 打开的结果页面。
7. `reports/quality/.../metrics.json` 中 `call_metrics` 部分。
8. `docker stats --no-stream` 输出，显示 CPU、内存资源消耗。
9. `kubectl -n service-agent-lab get pods -o wide`，显示 Pod Ready 和 Restart 次数。
10. `kubectl -n service-agent-lab get svc`，显示服务暴露情况。
11. Jenkins Pipeline 成功页面，显示自动测试、构建、部署、Smoke Test 均通过。
12. Web 页面导购 trace，显示真实 LLM 或 fallback 导购链路。

## 6. 报告可用结论模板

本项目通过 `quality_monitor.py`、Docker、Kubernetes 和 Jenkins 对服务进行监控和评价。监控数据覆盖资源参数、调用参数和时间参数，包括 CPU/内存使用量、请求成功率、状态码分布、平均延迟、P95 延迟和吞吐率。基于监控结果，可以从效率、可用性、健壮性和吞吐率四个方面评价系统质量。系统通过 Jenkins 自动测试和 Smoke Test 保证版本质量，通过 Kubernetes Deployment 提供部署稳定性，通过 LLM fallback 机制保证导购服务在真实模型不可用时仍能返回可用结果，因此具备较好的课程演示级可用性和健壮性。
