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
├── .pre-commit-config.yaml          # 커밋 전 `harness-catalog check` (CLI 판 v<판>에 핀)
├── .github/
│   ├── workflows/check.yml          # PR·main push마다 `harness-catalog ci check`, 선택 잡 evals
│   └── actions/code-repo-credentials/action.yml   # 코드 저장소가 비공개인 동안 CI가 CLI를 받을 deploy key
├── README.md
├── skills/                          # 스킬 하나 = 디렉토리 하나 (필수 디렉토리)
│   ├── pin-skill/                   # 기본 스킬: 스킬·도구를 내 하네스 옆에 내려받는 절차
│   │   ├── SKILL.md
│   │   └── evals/<case>/            # Harbor 태스크: task.toml · instruction.md · environment/Dockerfile · tests/ · solution/
│   └── write-skill/                 # 기본 스킬: 새 스킬의 뼈대와 팀 규약
│       ├── SKILL.md
│       ├── scripts/scaffold.py      # 결정적 뼈대 스크립트 (uv run --script)
│       ├── references/conventions.md
│       └── evals/<case>/
├── tools/                           # 선택. 도구 하나 = 디렉토리 하나
│   └── <name>/
│       ├── tool.json                # name · description · inputSchema · runtime{kind: script|mcp} · metadata
│       └── scripts/<x>.py           # kind: script일 때 runtime.path가 가리키는 파일
└── mcp-servers/                     # 선택. kind: mcp 도구가 참조하는 서버 배선
    └── <name>/server.json           # MCP Registry 형식: name · version · packages | remotes
```

`skills/`·`tools/`·`mcp-servers/` 바로 아래에는 디렉토리만 둡니다. 이름은 소문자·숫자·하이픈 1~64자이고, **스킬과 도구를 합쳐 저장소 전체에서 유일**합니다. 은퇴한 이름은 다시 쓰지 않습니다.

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

레지스트리가 내는 도구는 일곱이고 전부 읽기입니다.

| 도구 | 하는 일 |
|---|---|
| `list_skills()` · `search_skills(query)` | 스킬 목록·어휘 검색: 이름·설명·`sha`(판)·`replaced_by`·`requires_tools` |
| `load_skill(id, sha?)` | SKILL.md 본문과 파일 목록. `sha`를 주면 그 판 |
| `get_skill_file(id, path, sha?)` | 참조 파일·스크립트 하나 |
| `get_skill_archive(id, sha?)` | 한 판 전체를 tar로 받는 다운로드 기술자(URI + 5분 헤더 토큰 + sha256). 파일은 모델을 지나지 않습니다 |
| `search_tools(query)` | 도구 어휘 검색: 이름·설명·`sha`·`kind`·`server` |
| `get_tool(id, sha?)` | `tool.json` 전체. `kind: mcp`면 참조하는 `server.json`을, `kind: script`면 다운로드 기술자를 함께 |

- **곁에 두기(pin).** 매일 쓰는 스킬은 `pin-skill`을 따라 `.agents/skills/<name>/`(프로젝트) 또는 `~/.agents/skills/<name>/`(사용자)에 내려받습니다. 사본이 낡았는지는 `list_skills`의 `sha`와 사본의 `PINNED`를 견주면 압니다.
- **도구를 쓸 때.** `get_tool`은 정의와 배선을 줄 뿐 도구를 부르지 않습니다. `kind: mcp`면 그 서버를 하네스 설정(`.mcp.json`·`mcpServers`)에 붙이는 것은 사용자의 일이고, `kind: script`면 받은 디렉토리에서 `runtime.command`를 **셸 없이 argv로** 실행합니다(입력은 `inputSchema`에 맞는 JSON 하나를 stdin으로, 결과는 stdout, 종료 코드 0이 성공).
- **검색어에 비밀을 넣지 마세요.** 검색어는 팀 Langfuse의 도구 호출 기록에 남습니다.

## 만드는 사람: 올리기

1. `main`을 최신으로 하고 브랜치를 땁니다. `main`에 직접 push하지 않고 강제 push도 하지 않습니다(브랜치 보호는 걸려 있지 않습니다 — 규율입니다).
2. **스킬**은 `write-skill`을 따릅니다. `uv run --script skills/write-skill/scripts/scaffold.py <name> --description "<한 문장>"`이 `SKILL.md`와 Harbor 태스크 한 쌍(써야 하는 과제·쓰지 말아야 하는 과제)을 만들고, TODO만 채웁니다. 규약은 `skills/write-skill/references/conventions.md`.
3. **도구**는 `tools/<name>/tool.json`을 씁니다. `name`은 디렉토리명, `inputSchema`는 `type: object`, `runtime`은 둘 중 하나:
   - `{"kind": "script", "path": "scripts/x.py", "command": ["uv", "run", "--script", "scripts/x.py"]}` — `command`는 argv 배열이고 `path`는 그 원소 정확히 하나, 디렉토리 안의 일반 파일.
   - `{"kind": "mcp", "server": "<mcp-servers의 이름>", "tool": "<그 서버가 내는 도구 이름>"}` — 서버 레코드가 먼저 있어야 합니다.
   `mcp-servers/<name>/server.json`은 MCP Registry 형식(`name`·`version`·`packages` 또는 `remotes`)이고, 시크릿 값은 적지 않습니다(`isSecret: true` 항목에 `value`·`default` 금지).
4. 커밋 전에 `pre-commit install`을 한 번 해 두면 `harness-catalog check`가 커밋마다 돕니다. 같은 검사가 PR의 CI와 레지스트리의 색인에서도 돕니다. 붉으면 병합하지 않습니다.
5. PR을 열고 사람이 병합합니다. **병합한 사람이 그 판의 인증자**입니다. 레지스트리는 다음 fetch(기본 60초)에 새 판을 색인합니다.
6. 고치기는 같은 디렉토리를 바꿔 병합하는 것, 은퇴는 디렉토리 삭제, 대체는 지우기 전 판의 `metadata.replaced-by`에 새 이름을 적는 것입니다(스킬·도구 같음).

`harness-catalog check`의 항목: 1 저장소 구조 · 2 `skills/` 구조 · 3 SKILL.md 스펙 · 4 시크릿 없음(gitleaks) · 5 은퇴 이름 재사용 금지 · 6 `replaced-by` 대상 존재 · 7 크기 상한(파일 50개·1 MB·합 5 MB) · 8 `requires-tools` 문법 · 9 은퇴 때 `replaced-by` 권고(경고) · 10 복사 스크립트 드리프트(경고) · 11 `tool.json` · 12 `server.json`.

## 운영하는 사람: 체크리스트

1. git 호스트에 빈 저장소를 만들고 `harness-catalog init <repo-url>`을 돌립니다(이 파일들이 그 결과입니다).
2. 읽기 전용 deploy key를 등록하고 레지스트리의 비밀 파일에 개인 키를 넣습니다. 확인: 레지스트리 컨테이너에서 `git fetch`는 되고 `git push --dry-run`은 거부됩니다.
3. 저자에게 저장소 write, 병합·설정을 할 사람에게 admin을 줍니다. 저장소 read 이상 명단과 LDAP 그룹 `harness-readers`를 같게 유지합니다 — 레지스트리의 읽기 권한은 그 그룹 하나로 정해집니다.
4. Dex에 하네스 제품의 정적 클라이언트(`claude-code`·`codex`·`cursor`)가 있는지, 첫 팀원이 `harness-readers`에 있는지 확인합니다(로그인 한 번으로 확인).
5. 레지스트리를 띄우고 `/readyz`가 200인지 봅니다. 503이면 본문의 사유대로 1·2를 다시 봅니다: `not_a_catalog`(표지 없음) · `no_main_branch` · `repo_unreachable`(deploy key) · `layout_mismatch`(구조 항목 1·2·11·12 위반, 본문에 어느 항목인지).
6. 코드 저장소 `alteralab/harness-catalog`가 비공개인 동안은 CI가 CLI를 설치할 수 있게 그 저장소의 읽기 전용 deploy key 개인 키를 이 저장소(또는 조직) 시크릿 `HARNESS_CATALOG_DEPLOY_KEY`에 넣습니다(`ssh-keygen -t ed25519`, `gh repo deploy-key add`, `gh secret set`). `.github/actions/code-repo-credentials`가 그것을 잡 환경으로만 건넵니다. 코드 저장소가 공개면 필요 없습니다.
7. CI evals(선택): git 호스트 변수 `HARNESS_EVALS=true`로 켜고 `false`로 끕니다. 하네스 자격은 self-hosted 러너의 `.env`(변수 이름은 코드 저장소 `.github/runner.env.example`), 하네스 목록은 변수 `HARNESS_EVALS_AGENTS`(JSON 배열, 기본 `["claude-code", "codex"]`; GitLab은 `.gitlab-ci.yml`의 matrix 줄을 고칩니다).
8. CLI 판을 올릴 때는 `.pre-commit-config.yaml`과 `.github/workflows/check.yml`의 `@v<판>` 두 곳을 같은 태그로 바꿉니다. 검사 논리는 그 판을 따라옵니다.

GitLab용 워크플로(`.gitlab-ci.yml`)는 문면대로 작성만 되어 있고 아직 실제로 돌린 적이 없습니다. GitHub Actions가 먼저입니다.

## 더 읽기

코드 저장소 `alteralab/harness-catalog`의 `docs/using.md`(하네스에서 쓰기), `docs/authoring.md`(스킬·도구 올리기), `docs/operations.md`(레지스트리 운영), `DESIGN.md`(설계와 결정 원장).
