# Jenkins + GitHub + Kubernetes CI/CD 接入说明

本项目已提供真实 CI/CD 所需的项目侧文件:

```text
Jenkinsfile
Dockerfile
requirements.txt
docker-compose.yml
k8s/
scripts/smoke_test.py
```

目标链路:

```text
GitHub push / 手动触发
-> Jenkins Pipeline
-> 安装依赖
-> 静态检查
-> 自动测试
-> Docker 镜像构建
-> 推送镜像仓库
-> 部署到 Kubernetes
-> rollout 等待
-> 冒烟测试
```

## 1. Jenkins 节点要求

Jenkins Agent 需要安装:

```text
git
python3
pip
docker
kubectl
```

Jenkins Agent 还需要有权限执行:

```text
docker build
docker push
kubectl apply
kubectl rollout status
```

推荐使用 Linux Jenkins Agent。当前 `Jenkinsfile` 使用 `sh` 命令。

## 2. Jenkins 凭据

在 Jenkins 的 `Manage Credentials` 中创建以下凭据:

| Credentials ID | 类型 | 用途 |
|---|---|---|
| `docker-registry-credentials` | Username with password | 登录 Docker Hub / Harbor / 其他镜像仓库 |
| `kubeconfig-service-agent-lab` | Secret file | Kubernetes 集群 kubeconfig 文件 |

不要把 API Key、Docker 密码或 kubeconfig 写进 Git 仓库。

## 3. Jenkins Job 配置

创建 Pipeline Job:

1. 新建 Item。
2. 选择 Pipeline。
3. Pipeline Definition 选择 `Pipeline script from SCM`。
4. SCM 选择 Git。
5. 填写 GitHub 仓库地址。
6. Branch 设置为 `*/main` 或 `*/master`。
7. Script Path 填写 `Jenkinsfile`。

## 4. GitHub 触发 Jenkins

推荐方式:

1. 在 Jenkins Job 中启用 GitHub hook trigger。
2. 在 GitHub 仓库 `Settings -> Webhooks` 中添加 Jenkins webhook。
3. Payload URL 示例:

```text
http://<jenkins-host>/github-webhook/
```

Content type:

```text
application/json
```

之后每次 push 到目标分支, Jenkins 会自动拉取代码并执行流水线。

如果不能配置 webhook,也可以在 Jenkins 中使用轮询 SCM 或手动点击 `Build with Parameters`。

## 5. Pipeline 参数

`Jenkinsfile` 支持以下参数:

| 参数 | 示例 | 说明 |
|---|---|---|
| `DEPLOY_TARGET` | `k8s` | 可选 `k8s` / `compose` / `none` |
| `IMAGE_REGISTRY` | `docker.io/yourname/service-agent-lab` | 镜像仓库地址 |
| `K8S_NAMESPACE` | `service-agent-lab` | Kubernetes 命名空间 |

推荐真实 CI/CD 使用:

```text
DEPLOY_TARGET=k8s
```

## 6. Kubernetes 部署

流水线会执行:

```text
kubectl apply -f k8s/namespace.yaml
kubectl -n service-agent-lab apply -k k8s
kubectl -n service-agent-lab set image ...
kubectl -n service-agent-lab rollout status ...
```

当前 K8s 资源包括:

```text
k8s/namespace.yaml
k8s/config.yaml
k8s/order-service.yaml
k8s/product-service.yaml
k8s/logistics-service.yaml
k8s/agent-app.yaml
k8s/kustomization.yaml
k8s/llm-secret.example.yaml
```

`agent-app` 默认通过 `NodePort 30080` 暴露。

## 7. LLM 密钥管理

`k8s/llm-secret.example.yaml` 提供了 `service-agent-llm-secret` 模板,但它不会被 `k8s/kustomization.yaml` 默认部署,避免 CI/CD 覆盖集群中的真实密钥。演示环境可以不创建该 Secret,系统会 fallback 到规则推荐。

真实环境建议使用以下方式之一管理:

1. 在集群中手动创建 Secret。
2. 使用 Jenkins Credentials 在部署前创建/更新 Secret。
3. 使用云厂商 Secret Manager 或 External Secrets。

手动创建示例:

```powershell
kubectl -n service-agent-lab create secret generic service-agent-llm-secret `
  --from-literal=OPENAI_API_KEY=替换为真实值 `
  --from-literal=OPENAI_BASE_URL=https://your-gateway/v1 `
  --from-literal=OPENAI_MODEL=your-model `
  --dry-run=client -o yaml | kubectl apply -f -
```

## 8. 冒烟测试

Jenkins 部署完成后会执行:

```text
python3 scripts/smoke_test.py
```

K8s 模式下 Jenkins 会先执行:

```text
kubectl -n service-agent-lab port-forward svc/agent-app 8000:8000
```

然后测试:

1. 普通商品查询。
2. 增强导购。
3. 售后退款路径。

## 9. 当前实现边界

已经实现:

```text
GitHub 仓库可接 Jenkinsfile
Jenkins 可构建并推送镜像
Jenkins 可部署到 K8s
K8s 有完整多服务资源
部署后有自动冒烟测试
```

需要你在外部平台完成:

```text
创建 GitHub 仓库
创建 Jenkins Pipeline Job
配置 Docker 镜像仓库凭据
配置 kubeconfig 凭据
配置 GitHub webhook
准备可访问的 Kubernetes 集群
```
