pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '20'))
  }

  parameters {
    choice(name: 'DEPLOY_TARGET', choices: ['none', 'compose', 'k8s'], description: 'Deployment target after tests.')
    string(name: 'IMAGE_REGISTRY', defaultValue: 'docker.io/yourname/service-agent-lab', description: 'Docker image repository.')
    string(name: 'K8S_NAMESPACE', defaultValue: 'service-agent-lab', description: 'Kubernetes namespace.')
  }

  environment {
    DOCKER_CREDENTIALS_ID = 'docker-registry-credentials'
    KUBECONFIG_CREDENTIALS_ID = 'kubeconfig-service-agent-lab'
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
      }
    }

    stage('Check Tools') {
      steps {
        bat 'git --version'
        bat 'py -3.12 --version'
        bat 'docker version'
        bat 'kubectl version --client'
      }
    }

    stage('Prepare') {
      steps {
        script {
          def shortCommit = bat(script: '@git rev-parse --short HEAD', returnStdout: true).trim()
          env.IMAGE_TAG = "${env.BUILD_NUMBER}-${shortCommit}"
          env.IMAGE_FULL = "${params.IMAGE_REGISTRY}:${env.IMAGE_TAG}"
          env.IMAGE_LATEST = "${params.IMAGE_REGISTRY}:latest"
          echo "Image: ${env.IMAGE_FULL}"
        }
      }
    }

    stage('Install') {
      steps {
        bat '''
          py -3.12 -m venv .venv
          .\\.venv\\Scripts\\python.exe -m pip install --upgrade pip
          .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt
        '''
      }
    }

    stage('Static Check') {
      steps {
        bat '.\\.venv\\Scripts\\python.exe -m py_compile agent.py tools.py shopping_research_agent.py evaluate.py server.py scripts\\smoke_test.py'
      }
    }

    stage('Test') {
      steps {
        bat '.\\.venv\\Scripts\\python.exe evaluate.py'
      }
    }

    stage('Build Image') {
      steps {
        bat 'docker build -t "%IMAGE_FULL%" -t "%IMAGE_LATEST%" .'
      }
    }

    stage('Push Image') {
      when {
        expression { params.DEPLOY_TARGET == 'k8s' }
      }
      steps {
        withCredentials([usernamePassword(credentialsId: env.DOCKER_CREDENTIALS_ID, usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASS')]) {
          powershell '''
            $ErrorActionPreference = "Stop"
            $registry = $env:IMAGE_REGISTRY.Split("/")[0]
            $env:DOCKER_PASS | docker login $registry -u $env:DOCKER_USER --password-stdin
            docker push $env:IMAGE_FULL
            docker push $env:IMAGE_LATEST
          '''
        }
      }
    }

    stage('Deploy to Kubernetes') {
      when {
        expression { params.DEPLOY_TARGET == 'k8s' }
      }
      steps {
        withCredentials([file(credentialsId: env.KUBECONFIG_CREDENTIALS_ID, variable: 'KUBECONFIG_FILE')]) {
          powershell '''
            $ErrorActionPreference = "Stop"
            $env:KUBECONFIG = $env:KUBECONFIG_FILE
            kubectl apply -f k8s\\namespace.yaml
            kubectl -n $env:K8S_NAMESPACE apply -k k8s
            kubectl -n $env:K8S_NAMESPACE set image deployment/order-service order-service=$env:IMAGE_FULL
            kubectl -n $env:K8S_NAMESPACE set image deployment/product-service product-service=$env:IMAGE_FULL
            kubectl -n $env:K8S_NAMESPACE set image deployment/logistics-service logistics-service=$env:IMAGE_FULL
            kubectl -n $env:K8S_NAMESPACE set image deployment/agent-app agent-app=$env:IMAGE_FULL
            kubectl -n $env:K8S_NAMESPACE rollout status deployment/order-service --timeout=120s
            kubectl -n $env:K8S_NAMESPACE rollout status deployment/product-service --timeout=120s
            kubectl -n $env:K8S_NAMESPACE rollout status deployment/logistics-service --timeout=120s
            kubectl -n $env:K8S_NAMESPACE rollout status deployment/agent-app --timeout=120s
          '''
        }
      }
    }

    stage('Deploy with Compose') {
      when {
        expression { params.DEPLOY_TARGET == 'compose' }
      }
      steps {
        bat 'docker compose up -d --build'
      }
    }

    stage('Smoke Test') {
      when {
        expression { params.DEPLOY_TARGET != 'none' }
      }
      steps {
        script {
          if (params.DEPLOY_TARGET == 'k8s') {
            withCredentials([file(credentialsId: env.KUBECONFIG_CREDENTIALS_ID, variable: 'KUBECONFIG_FILE')]) {
              powershell '''
                $ErrorActionPreference = "Stop"
                $env:KUBECONFIG = $env:KUBECONFIG_FILE
                $namespace = $env:K8S_NAMESPACE
                $job = Start-Job -ScriptBlock {
                  param($ns)
                  kubectl -n $ns port-forward svc/agent-app 8000:8000
                } -ArgumentList $namespace
                Start-Sleep -Seconds 8
                try {
                  .\\.venv\\Scripts\\python.exe scripts\\smoke_test.py
                } finally {
                  Stop-Job $job -ErrorAction SilentlyContinue
                  Remove-Job $job -ErrorAction SilentlyContinue
                }
              '''
            }
          } else {
            bat '.\\.venv\\Scripts\\python.exe scripts\\smoke_test.py'
          }
        }
      }
    }
  }

  post {
    always {
      bat 'docker logout || exit /b 0'
    }
    success {
      echo "CI/CD finished successfully: ${env.IMAGE_FULL}"
    }
  }
}
