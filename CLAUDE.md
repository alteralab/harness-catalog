# harness-catalog

- 위치·시그니처·호출 관계·영향 범위는 Graft(`graft ask/grep/skeleton/callers`, MCP `graft_*`) 또는 소스로 확인한다. OpenWiki 페이지의 `file:line`은 작업 전 상태다.
- 설계 이유·흐름·실패 양상은 OpenWiki(`openwiki_search` → `openwiki_read`)를 먼저 검색한다. 작업 시작에 미리 읽지 않고, 근거를 얻으면 멈춘다.
- 세션 시작에 `openwiki: 마지막 갱신 이후 커밋 N개`가 뜨면 그 사이 바뀐 파일은 위키 대신 소스를 본다.
- 설계 결정의 정본은 DESIGN.md와 `plans/*.md`의 원장이다. 계약을 바꾸는 변경은 DESIGN §11 행이 먼저다.
- 개발 절차는 docs/development.md, 명령은 `make help`.
