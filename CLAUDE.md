# harness-catalog

- 위치·시그니처·호출 관계·영향 범위는 Trail(`trail ask/grep/skeleton/callers`, MCP `trail_*`; 코드 지도는 `.trail/cache/`) 또는 소스로 확인한다. OpenWiki 페이지의 `file:line`은 작업 전 상태다.
- 이 저장소의 현재 Trail 코드 지도가 색인하는 것은 python·typescript·tsx·javascript 넷이다(`trail build` 가 끝에 찍는다). 셸 스크립트, Compose·워크플로 YAML, TOML, JSON, SQL, Dockerfile, Markdown은 색인 밖이므로 `trail grep` 0건을 저장소 전체의 부재로 해석하지 말고 원본 경로를 Grep으로 확인한다. 설정의 컴포넌트 간 연결은 OpenWiki에서 맥락을 찾고 현재 소스로 검증한다.
- 지도는 **구조 계층만**이라 노드가 든 것은 이름과 시그니처뿐이고 요약(`summary`·`crux`)은 비어 있다(의미 층은 `--deep`, 이 저장소는 키 없이 쓰기로 했다 — PLAN.md 2026-10-10). 그래서 **한국어로 물 때는 `ask` 가 아니라 `grep` 이다**: `trail ask` 는 이름·시그니처만 보므로 한국어 평문("인가")이 0건이지만, `trail grep "볼록 결합"` 은 원문을 훑어 주석·독스트링까지 심볼별로 묶어 낸다(2026-10-20 실측: 5개 파일 8건). `ask` 는 영어 식별자나 영어 평문으로 쓴다.
- 설계 이유·흐름·실패 양상은 OpenWiki(`openwiki_search` → `openwiki_read`)를 먼저 검색한다. 작업 시작에 미리 읽지 않고, 근거를 얻으면 멈춘다.
- 세션 시작에 `openwiki: 마지막 갱신 이후 커밋 N개`가 뜨면 그 사이 바뀐 파일은 위키 대신 소스를 본다.
- 설계 결정의 정본은 DESIGN.md와 `plans/*.md`의 원장이다. 계약을 바꾸는 변경은 DESIGN §11 행이 먼저다.
- 개발 절차는 docs/development.md, 명령은 `make help`.
- **Harbor는 둘이다.** `harbor run`·`harbor_langfuse`·evals 러너는 Terminal-Bench 쪽 **Harbor(evals 프레임워크)**, 이미지 push/pull·`ds923plus.tail2f9fe3.ts.net:9443`·portainer `stacks/harbor`는 **goharbor(NAS 이미지 레지스트리)**다. 문서와 대화에서 레지스트리는 "NAS Harbor"라고 부른다. 둘은 아무 관계가 없다.

<!-- OPENWIKI:START -->

## OpenWiki

@AGENTS.md

<!-- OPENWIKI:END -->
