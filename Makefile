# 자주 치는 명령의 이름. `make help`가 목록이다. 실제 절차는 docs/ 가 정본이고 이 파일은 그 줄임이다.
.DEFAULT_GOAL := help
COMPOSE_QS  := docker compose -f docker-compose.quickstart.yml
COMPOSE_DEV := docker compose -f docker-compose.dev.yml

.PHONY: help quickstart quickstart-logs quickstart-down dev-up dev-down serve test typecheck gates check image

help: ## 이 목록
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-16s\033[0m %s\n", $$1, $$2}'

quickstart: ## 레지스트리 전체를 로컬에 띄운다(평가용, 비밀은 공개 값). 끝나면 접속 안내를 찍는다
	$(COMPOSE_QS) up -d --build --wait
	$(COMPOSE_QS) logs welcome --no-log-prefix

quickstart-logs: ## 빠른 시작 스택의 로그
	$(COMPOSE_QS) logs -f

quickstart-down: ## 빠른 시작 스택을 지운다(볼륨 포함)
	$(COMPOSE_QS) down -v

dev-up: ## 개발용 postgres + dex (.env 필요). 레지스트리는 `make serve`
	$(COMPOSE_DEV) up -d --wait

dev-down: ## 개발용 스택 정지(볼륨 유지)
	$(COMPOSE_DEV) down

serve: ## 레지스트리를 호스트에서 띄운다(.env를 환경으로 읽는다)
	set -a; . ./.env; set +a; uv run harness-catalog-server serve --port 8000

test: ## pytest (pg 표시 시험은 docker, http 표시 시험은 dev 스택이 필요)
	uv run pytest -q tests

typecheck: ## pyright strict
	uv run pyright packages tests tools

gates: ## altera-rules 게이트 넷(ruff · ast-grep · shellcheck · 선언)
	uvx pre-commit run --all-files

check: gates typecheck test ## 게이트 + 타입 + 시험 (CI와 같다)

image: ## 레지스트리 이미지를 로컬 태그로 빌드한다
	docker build -t harness-catalog:current .
