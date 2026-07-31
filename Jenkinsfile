// 쫄래쫄래 CI/CD 파이프라인 (Jenkins, EC2 단일 호스트 배포)
// 흐름: 백엔드 테스트 → 이미지 빌드(BE/FE) → docker compose 배포
// 필요한 Jenkins 자격증명:
//   - choll-app-env (Secret file): 배포용 .env (DB_*, MQTT_* 등 — 노션 참조)
pipeline {
	agent any

	options {
		disableConcurrentBuilds()
		timestamps()
	}

	stages {
		stage('Backend Test') {
			steps {
				withCredentials([file(credentialsId: 'choll-app-env', variable: 'ENV_FILE')]) {
					sh '''
						set -a; . "$ENV_FILE"; set +a
						# 테스트는 브로커 없이 돈다 (contextLoads가 MQTT 연결을 시도하지 않도록)
						export MQTT_ENABLED=false
						export WS_POSITION_TEST_ENABLED=false
						cd backend && chmod +x gradlew && ./gradlew test --no-daemon
					'''
				}
			}
		}

		stage('Build Images') {
			steps {
				sh 'docker build -t choll-backend:latest backend'
				sh 'docker build -t choll-web:latest frontend'
			}
		}

		stage('Deploy') {
			steps {
				withCredentials([file(credentialsId: 'choll-app-env', variable: 'ENV_FILE')]) {
					sh '''
						cp "$ENV_FILE" infra/.env
						docker compose -p choll-app -f infra/docker-compose.app.yml up -d
						rm -f infra/.env
					'''
				}
			}
		}

		stage('Cleanup') {
			steps {
				// 태그가 밀려난 옛 이미지 정리 (디스크 보호)
				sh 'docker image prune -f'
			}
		}
	}
}
