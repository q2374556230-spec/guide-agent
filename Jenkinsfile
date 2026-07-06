pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '20'))
  }

  parameters {
    choice(name: 'DEPLOY_TARGET', choices: ['k8s', 'compose', 'none'], description: 'Deployment target after tests.')
    string(name: 'IMAGE_REGISTRY', defaultValue: 'registry.example.com/service-agent-lab', description: 'Docker image repository, for example docker.io/yourname/service-agent-lab.')
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

    stage('Prepare') {
      steps {
        script {
          def shortCommit = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
          env.IMAGE_TAG = "${env.BUILD_NUMBER}-${shortCommit}"
          env.IMAGE_FULL = "${params.IMAGE_REGISTRY}:${env.IMAGE_TAG}"
          env.IMAGE_LATEST = "${params.IMAGE_REGISTRY}:latest"
          echo "Image: ${env.IMAGE_FULL}"
        }
      }
    }

    stage('Install') {
      steps {
        sh 'python3 -m pip install --user -r requirements.txt'
      }
    }

    stage('Static Check') {
      steps {
        sh 'python3 -m py_compile agent.py tools.py shopping_research_agent.py evaluate.py server.py scripts/smoke_test.py'
      }
    }

    stage('Test') {
      steps {
        sh 'python3 evaluate.py'
      }
    }

    stage('Build Image') {
      steps {
        sh '''
          docker build -t "$IMAGE_FULL" -t "$IMAGE_LATEST" .
        '''
      }
    }

    stage('Push Image') {
      when {
        expression { params.DEPLOY_TARGET == 'k8s' }
      }
      steps {
        withCredentials([usernamePassword(credentialsId: env.DOCKER_CREDENTIALS_ID, usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASS')]) {
          sh '''
            echo "$DOCKER_PASS" | docker login "$(echo "$IMAGE_REGISTRY" | cut -d/ -f1)" -u "$DOCKER_USER" --password-stdin
            docker push "$IMAGE_FULL"
            docker push "$IMAGE_LATEST"
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
          sh '''
            export KUBECONFIG="$KUBECONFIG_FILE"
            kubectl apply -f k8s/namespace.yaml
            kubectl -n "$K8S_NAMESPACE" apply -k k8s
            kubectl -n "$K8S_NAMESPACE" set image deployment/order-service order-service="$IMAGE_FULL"
            kubectl -n "$K8S_NAMESPACE" set image deployment/product-service product-service="$IMAGE_FULL"
            kubectl -n "$K8S_NAMESPACE" set image deployment/logistics-service logistics-service="$IMAGE_FULL"
            kubectl -n "$K8S_NAMESPACE" set image deployment/agent-app agent-app="$IMAGE_FULL"
            kubectl -n "$K8S_NAMESPACE" rollout status deployment/order-service --timeout=120s
            kubectl -n "$K8S_NAMESPACE" rollout status deployment/product-service --timeout=120s
            kubectl -n "$K8S_NAMESPACE" rollout status deployment/logistics-service --timeout=120s
            kubectl -n "$K8S_NAMESPACE" rollout status deployment/agent-app --timeout=120s
          '''
        }
      }
    }

    stage('Deploy with Compose') {
      when {
        expression { params.DEPLOY_TARGET == 'compose' }
      }
      steps {
        sh 'docker compose up -d --build'
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
              sh '''
                export KUBECONFIG="$KUBECONFIG_FILE"
                kubectl -n "$K8S_NAMESPACE" port-forward svc/agent-app 8000:8000 >/tmp/service-agent-lab-port-forward.log 2>&1 &
                PF_PID=$!
                sleep 5
                python3 scripts/smoke_test.py
                kill "$PF_PID"
              '''
            }
          } else {
            sh 'python3 scripts/smoke_test.py'
          }
        }
      }
    }
  }

  post {
    always {
      sh 'docker logout || true'
    }
    success {
      echo "CI/CD finished successfully: ${env.IMAGE_FULL}"
    }
  }
}
