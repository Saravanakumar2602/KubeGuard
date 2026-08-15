.PHONY: test cli-test helm-lint helm-template docker-build

test:
	pytest prediction-service/tests/ -v

cli-test:
	pytest cli/kubeguard_cli/tests/ -v

helm-lint:
	helm lint helm/kubeguard

helm-template:
	helm template kubeguard helm/kubeguard --namespace kubeguard

docker-build:
	docker build -t kubeguard-prediction-service:0.1.6 -f prediction-service/Dockerfile .

