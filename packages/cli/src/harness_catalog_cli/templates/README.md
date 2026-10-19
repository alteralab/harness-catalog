# 하네스 카탈로그

팀의 **스킬**과 **도구**를 한 git 저장소에 모아 두고, 레지스트리(MCP 서버)가 `main`을 읽어 검색·적재 도구로 내줍니다. 게시는 브랜치 → PR → 병합이고, `main`에 있는 것이 곧 게시된 판입니다. 레지스트리는 쓰지 않고 읽기만 합니다 — 사람이 하는 쓰기는 전부 이 저장소의 PR입니다.

- **스킬**(`skills/<name>/`): 에이전트가 읽는 절차와 규약. [agentskills.io](https://agentskills.io) 형식의 `SKILL.md`와 그 옆 파일들.
- **도구**(`tools/<name>/`): 에이전트가 스키마로 부르는 호출 가능한 것. 카탈로그 안 스크립트이거나 팀 MCP 서버의 도구 하나.
- **MCP 서버 배선**(`mcp-servers/<name>/`): 도구가 참조하는 서버가 무엇이고 어떻게 띄우는지(MCP Registry `server.json` 형식).

이 저장소는 `harness-catalog init`(v<판>)이 만들었습니다. 두 번 돌려도 바뀌지 않습니다.

## 디렉토리 구조

```
.
├── .harness-catalog                 # 표지: layout = 1. 레지스트리가 이 저장소를 카탈로그로 인식하는 근거
├── .mcp.json                        # 이 클론에서 tools/의 도구를 MCP로 띄우는 toolbox 항목(hc toolbox ./tools)
├── .pre-commit-config.yaml          # 커밋 전 `harness-catalog check` (CLI 판 v<판>에 핀)
├── .gitignore                       # harbor 결과(jobs/)·파이썬 캐시·이 클론 안의 pin 사본(.agents/)은 커밋하지 않는다
├── .github/
│   ├── workflows/check.yml          # PR·main push마다 `harness-catalog check`, 선택 잡 evals
│   └── actions/code-repo-credentials/action.yml   # 코드 저장소가 비공개인 동안 CI가 CLI를 받을 deploy key
├── README.md
├── skills/                          # 스킬 하나 = 디렉토리 하나 (필수 디렉토리). 기본형은 세션·루프 공용: 코드는 tools/에, 스킬은 이름으로 참조
│   ├── pin/                         # 기본 스킬: 스킬·도구를 내 하네스 옆에 내려받는 절차(판단은 산문, 받기는 hc pin)
│   │   ├── SKILL.md
│   │   └── evals/<case>/            # Harbor 태스크: task.toml · instruction.md · environment/Dockerfile · tests/ · solution/
│   ├── write/                       # 기본 스킬: 새 스킬·도구의 뼈대와 팀 규약(판단과 결정적 부분을 가르기부터)
│   │   ├── SKILL.md
│   │   ├── references/conventions.md    # 스킬 규약 점검표
│   │   ├── references/tool-contract.md  # 도구 계약 점검표(결과 ABI)
│   │   └── evals/<case>/
│   └── review/                      # 기본 스킬: 있는 스킬 하나를 저작 지침·팀 규약으로 심사하고 다듬기
│       ├── SKILL.md
│       ├── references/checklist.md      # 심사 점검표(출처: agentskills 스펙·Anthropic·Codex·팀)
│       └── evals/<case>/
├── schemas/
│   └── tool.schema.json             # tool.json의 JSON Schema. init이 core 모델에서 생성; 낡으면 hc check가 경고하고 hc init <repo-url> --refresh가 다시 씁니다
├── tools/                           # 도구 하나 = 디렉토리 하나. 기본 도구 scaffold가 들어 있다
│   ├── scaffold/                    # 기본 도구: 새 스킬·도구의 뼈대(write 스킬이 부른다). tool.json + scripts/scaffold.py
│   └── <name>/
│       ├── tool.json                # $schema(선택) · name · description · inputSchema · outputSchema(선택) · runtime{kind: script|mcp}
│       └── scripts/<x>.py           # kind: script일 때 runtime.path가 가리키는 파일. 의존성은 이 안에만(PEP 723)
└── mcp-servers/                     # 선택. kind: mcp 도구가 참조하는 서버 배선
    └── <name>/server.json           # MCP Registry 형식: name · version · packages | remotes
```

`skills/`·`tools/`·`mcp-servers/` 바로 아래에는 디렉토리만 둡니다. 이름은 소문자·숫자·하이픈 1~64자이고, **스킬과 도구를 합쳐 저장소 전체에서 유일**합니다. 은퇴는 디렉토리 삭제이고, 같은 이름으로 다른 내용을 올리는 것은 은퇴가 아니라 갱신입니다.

## 쓰는 사람: 하네스에서 찾고 적재하기

**등록 두 줄, 로그인 한 번.** 레지스트리는 동적 클라이언트 등록을 쓰지 않아 하네스마다 미리 등록된 클라이언트 ID가 있습니다.

| 하네스 | 클라이언트 ID |
|---|---|
| Claude Code | `claude-code` |
| Codex | `codex` |
| Cursor | `cursor` |

Claude Code는 다음 한 줄 뒤, `~/.claude.json`(프로젝트에만 두려면 `.mcp.json`)의 그 항목에 `"oauth": {"clientId": "claude-code"}`를 더하고 새 세션을 시작합니다. 첫 호출에 로그인 창이 열리고 팀 LDAP 계정으로 한 번 로그인하면 됩니다.

```sh
claude mcp add --transport http --scope user harness-catalog https://<레지스트리 호스트>/mcp
```

레지스트리가 내는 도구는 넷이고 전부 읽기입니다. 전체 목록 도구는 없고 주제로 좁혀 검색합니다. 응답 필드와 오류 코드는 코드 저장소 `docs/using.md`에 있습니다.

| 도구 | 하는 일 |
|---|---|
| `search_skills(query)` | 스킬 검색(이름·설명의 BM25 + 설명 임베딩 — 바꿔 말한 질의도 잡힌다): 이름·설명·`sha`(판)·`compatibility`·`has_scripts` |
| `get_skill(id, sha?, path?, archive?)` | SKILL.md 본문과 파일 목록. `path`면 그 파일 하나, `archive=true`면 한 판 전체를 tar로 받는 다운로드 명세(URI + 5분 헤더 토큰 + sha256)를 함께 — 파일은 모델을 지나지 않습니다 |
| `search_tools(query)` | 도구 검색(엔진은 스킬과 같다): 이름·설명·`sha`·`kind`·`server` |
| `get_tool(id, sha?, archive?)` | `tool.json` 전체. `kind: mcp`면 참조하는 `server.json`을, `kind: script`이고 `archive=true`면 다운로드 명세를 함께 |

- **곁에 두기(pin).** 매일 쓰는 스킬은 `pin` 스킬을 따라 `.agents/skills/<name>/`(프로젝트) 또는 `~/.agents/skills/<name>/`(사용자)에 내려받습니다. 무엇을 어느 범위에 받을지는 대화로 정하고, 받기부터 PINNED까지는 `hc pin`이 한 번에 합니다. 사본이 낡았는지는 `search_skills(<name>)`의 `sha`와 사본의 `PINNED`를 견주면 압니다.
- **도구를 쓸 때.** `get_tool`은 정의와 배선을 줄 뿐 도구를 부르지 않습니다. `kind: mcp`면 그 서버를 하네스 설정(`.mcp.json`·`mcpServers`)에 붙이는 것은 사용자의 일입니다. `kind: script`면 `get_tool(archive=true)` 응답을 `hc pin --scope project`에 넘기고, 그 명령이 `.mcp.json`에 써 둔 `toolbox` 항목(`hc toolbox .agents/tools`)이 도구를 MCP로 띄웁니다. 이 카탈로그 저장소 안에서는 `init`이 둔 `.mcp.json`(`hc toolbox ./tools`)으로 `tools/`의 도구가 바로 MCP에 뜹니다.
- **검색어에 비밀을 넣지 마세요.** 검색어는 팀 Langfuse의 도구 호출 기록에 남습니다.

## 만드는 사람: 올리기

1. `main`을 최신으로 하고 브랜치를 땁니다. `main`에 직접 push하지 않고 강제 push도 하지 않습니다(브랜치 보호는 걸려 있지 않습니다 — 규율입니다).
2. 스킬이든 도구든 **`write` 스킬**을 따릅니다. 첫 단계는 절차를 판단과 결정적 부분으로 가르는 것입니다. 판단은 스킬 본문이고, 결정적 부분은 도구(`tools/<name>/`)입니다 — 이미 있으면 이름으로 엮고 없으면 새로 만듭니다. 세션과 루프가 같은 스킬을 쓰는 기본형입니다. 뼈대는 도구 `scaffold`가 만듭니다(이 저장소의 `.mcp.json`이 `hc toolbox ./tools`를 등록해 두어 하네스에서 MCP 도구로 뜹니다). 규약은 `skills/write/references/conventions.md`(스킬)와 `tool-contract.md`(도구). 손으로 쓸 때의 요지 — `tool.json`의 `name`은 디렉토리명, `inputSchema`는 `type: object`, `runtime`은 둘 중 하나:
   - `{"kind": "script", "path": "scripts/x.py", "command": ["uv", "run", "--script", "scripts/x.py"]}` — `command`는 argv 배열이고 `path`는 그 원소 정확히 하나, 디렉토리 안의 일반 파일. 의존성은 스크립트 안에만.
   - `{"kind": "mcp", "server": "<mcp-servers의 이름>", "tool": "<그 서버가 내는 도구 이름>"}` — 서버 레코드가 먼저 있어야 합니다.
   `mcp-servers/<name>/server.json`은 MCP Registry 형식(`name`·`version`·`packages` 또는 `remotes`)이고, 시크릿 값은 적지 않습니다(`isSecret: true` 항목에 `value`·`default` 금지).
3. 도구는 한 번 돌려 봅니다. 이 저장소 안에서는 toolbox가 띄운 MCP 도구로 부르거나, 터미널에서 `echo '{...}' | uv run --script tools/<name>/scripts/<x>.py`로 칩니다. 스킬은 `harbor run -p skills/<name>/evals -a oracle -e docker`로 evals 쌍이 모델 없이 reward 1인지 봅니다.
4. 커밋 전에 `pre-commit install`을 한 번 해 두면 `hc check`가 커밋마다 돕니다(`hc`는 `harness-catalog`의 짧은 이름이고 같은 명령입니다). `hc` 설치는 팀 Nexus 인덱스에서: `uv tool install --default-index https://ds923plus.tail2f9fe3.ts.net:8443/repository/pypi-public/simple/ harness-catalog-cli==<판>`. 같은 검사가 PR의 CI와 레지스트리의 색인에서도 돕니다. 붉으면 병합하지 않습니다.
5. PR을 열고 사람이 병합합니다. **병합한 사람이 그 판의 인증자**입니다. 레지스트리는 다음 fetch(기본 60초)에 새 판을 색인합니다.
6. 고치기는 같은 디렉토리를 바꿔 병합하는 것, 은퇴는 디렉토리 삭제입니다(스킬·도구 같음). 후속은 검색으로 찾습니다. 있는 스킬이 발동하지 않거나 다듬고 싶으면 **`review` 스킬**이 점검표(`skills/review/references/checklist.md`)로 심사해 표를 내고, 고른 항목을 브랜치에 고칩니다.

`hc check`의 항목(일곱): 1 저장소 구조 · 2 `skills/` 구조 · 3 SKILL.md 스펙 · 4 시크릿 없음(gitleaks) · 7 크기 상한(파일 50개·1 MB·합 5 MB) · 11 `tool.json` · 12 `server.json`. 번호 5·6·8·9·10은 뺀 규칙의 자리라 비어 있습니다.

## 운영하는 사람: 체크리스트

1. git 호스트에 빈 저장소를 만들고 `hc init <repo-url>`을 돌립니다(이 파일들이 그 결과입니다).
2. 읽기 전용 deploy key를 등록하고 레지스트리의 비밀 파일에 개인 키를 넣습니다. 확인: 레지스트리 컨테이너에서 `git fetch`는 되고 `git push --dry-run`은 거부됩니다.
3. 저자에게 저장소 write, 병합·설정을 할 사람에게 admin을 줍니다. 저장소 read 이상 명단과 LDAP 그룹 `harness-readers`를 같게 유지합니다 — 레지스트리의 읽기 권한은 그 그룹 하나로 정해집니다.
4. Dex에 하네스 제품의 정적 클라이언트(`claude-code`·`codex`·`cursor`)가 있는지, 첫 팀원이 `harness-readers`에 있는지 확인합니다(로그인 한 번으로 확인).
5. 레지스트리를 띄우고 `/readyz`가 200인지 봅니다. 503이면 본문의 사유대로 1·2를 다시 봅니다: `not_a_catalog`(표지 없음) · `unsupported_layout`(표지의 layout이 다른 판) · `no_main_branch` · `repo_unreachable`(deploy key) · `layout_mismatch`(구조 항목 1·2·11·12 위반, 본문에 어느 항목인지).
6. 코드 저장소 `alteralab/harness-catalog`가 비공개인 동안은 CI가 CLI를 설치할 수 있게 그 저장소의 읽기 전용 deploy key 개인 키를 이 저장소(또는 조직) 시크릿 `HARNESS_CATALOG_DEPLOY_KEY`에 넣습니다(`ssh-keygen -t ed25519`, `gh repo deploy-key add`, `gh secret set`). `.github/actions/code-repo-credentials`가 그것을 잡 환경으로만 건넵니다. 코드 저장소가 공개면 필요 없습니다.
7. CI evals는 Oracle입니다(모델·자격 없음). self-hosted 러너에 Docker가 있고 tailnet에 닿으면(eval 이미지가 NAS Nexus에서 `hc`를 받습니다) 그대로 돕니다. 이 잡은 PR의 Dockerfile과 검증기를 내부 러너에서 실행하므로 같은 저장소의 브랜치(쓰기 권한자)와 `main` push에서만 돌고 포크 PR에서는 돌지 않습니다. 모델 측정(스킬 있이·없이)은 저자가 자기 클론에서 자기 자격으로 합니다 — `write` 스킬 9단계.
8. CLI 판을 올릴 때는 `.pre-commit-config.yaml`과 `.github/workflows/check.yml`의 `@v<판>` 두 곳을 같은 태그로 바꿉니다. 검사 논리는 그 판을 따라옵니다.

GitLab용 워크플로(`.gitlab-ci.yml`)는 문면대로 작성만 되어 있고 아직 실제로 돌린 적이 없습니다. GitHub Actions가 먼저입니다.

## 더 읽기

코드 저장소 `alteralab/harness-catalog`의 `docs/using.md`(하네스에서 쓰기), `docs/authoring.md`(스킬·도구 올리기), `docs/operations.md`(레지스트리 운영), `DESIGN.md`(설계와 결정 원장).
