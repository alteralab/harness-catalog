# 자주 치는 명령의 이름. `make help`가 목록이다. 실제 절차는 docs/ 가 정본이고 이 파일은 그 줄임이다.
.DEFAULT_GOAL := help
COMPOSE_QS  := docker compose -f docker/compose.quickstart.yml
COMPOSE_DEV := docker compose -f docker/compose.dev.yml


.PHONY: mcp-pin
.PHONY: help quickstart quickstart-logs quickstart-down dev-up dev-down serve test typecheck gates check image graft graft-init wiki-claims wiki-install

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
	set -a; . ./docker/.env; set +a; uv run harness-catalog-server serve --port 8000

test: ## pytest (pg 표시 시험은 docker, http 표시 시험은 dev 스택이 필요)
	uv run pytest -q tests

typecheck: ## pyright strict
	uv run pyright packages tests tools

gates: ## altera-rules 게이트 넷(ruff · ast-grep · shellcheck · 선언)
	uvx pre-commit run --all-files

check: gates typecheck test ## 게이트 + 타입 + 시험 (CI와 같다)

image: ## 레지스트리 이미지를 로컬 태그로 빌드한다
	docker build -t harness-catalog:current .

graft: ## Graft 코드 그래프를 (다시) 만든다 — 판은 package.json에 고정(npm ci로 받는다). 이미지와 무관
	npm ci --silent
	npx graft build

graft-init: ## Claude Code 배선을 다시 쓴다(init은 .mcp.json을 판 없이 쓰므로 뒤에 다시 고정한다). 전역 설정·statusLine은 건드리지 않는다
	npm ci --silent
	DO_NOT_TRACK=1 GRAFT_MCP_NPX=1 npx graft init --agents claude --no-global --no-statusline
	$(MAKE) mcp-pin

mcp-pin: ## .mcp.json의 graft·openwiki 서버를 package.json의 판으로 다시 고정한다(init 도구들이 판 없이 쓰므로)
	python3 -c "import json,pathlib; p=pathlib.Path('.mcp.json'); d=json.loads(p.read_text()); dv=json.load(open('package.json'))['devDependencies']; d['mcpServers']['graft']={'command':'npx','args':['-y','@nanonets/graft@'+dv['@nanonets/graft'],'mcp']}; d['mcpServers']['openwiki']={'command':'npx','args':['-y','openwiki@'+dv['openwiki'],'mcp','--host','claude']}; p.write_text(json.dumps(d,indent=2)+'\n'); print('.mcp.json pinned:', dv)"

wiki-install: ## OpenWiki의 Claude Code 배선(.claude/skills/openwiki, .mcp.json)을 다시 쓴다
	npm ci --silent
	npx openwiki integrations install claude --project . --force
	$(MAKE) mcp-pin

wiki-claims: ## 지금 브랜치가 바꾼 파일을 인용하는 OpenWiki claim — MR 올리기 전에 어느 페이지가 낡는지 본다(모델 없음)
	@test -d openwiki/.claims || { echo "openwiki/ 가 없다 — Claude Code에서 'Initialize OpenWiki for this repository' 부터"; exit 0; }
	@for f in $$(git diff --name-only $$(git merge-base origin/main HEAD) HEAD; git diff --name-only); do grep -l "repo://$$f[\"#]" openwiki/.claims/*.json 2>/dev/null; done | sort -u | sed 's|^|page claims citing changed files: |'
