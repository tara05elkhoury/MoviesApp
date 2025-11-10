pipeline {
    agent any

    triggers {
        // Poll GitHub every 2 minutes
        pollSCM('H/2 * * * *')
    }

    stages {
        stage('Checkout') {
            steps {
                git branch: 'main', url: 'https://github.com/tara05elkhoury/MoviesApp'
            }
        }

        stage('Build in Minikube Docker') {
            steps {
                bat '''
                    REM === Switch Docker to Minikube Docker ===
                    call minikube docker-env --shell=cmd > docker_env.bat
                    call docker_env.bat

                    REM === Build Django image inside Minikube Docker ===
                    docker build -t mydjangoapp:latest .
                '''
            }
        }

        stage('Deploy to Minikube') {
            steps {
                bat '''
                    REM === Apply the updated deployment manifest ===
                    kubectl apply -f deployment.yaml

                    REM === Ensure the rollout completes ===
                    kubectl rollout status deployment/django-deployment
                '''
            }
        }
    }
}
