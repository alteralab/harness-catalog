# 검색 벤치마크 — `search_skills`·`search_tools`가 규모에서 버티는가

`uv run python -m bench.search --n 100 1000` (Docker 필요: Postgres 를 testcontainers 로 띄운다. `DATABASE_URL` 을 주면 그 DB 를 쓴다.)

## 왜

검색은 세션(사람)과 kata(루프 조립기) 둘 다의 관문이다. kata 는 상위 3만 보므로 거기서 틀리면 끝이다. 스킬·도구가 수백·수천이 되기 전에
엔진을 숫자로 고르려고 측정 장치를 먼저 만든다(§11 2026-10-19). 엔진 변경 PR 은 이 숫자가 좋아져야 병합한다.

## 무엇을 잰다

- 합성 말뭉치(`corpus.py`): 8개 영역 × 대상 × 동작 × 한정어를 시드로 결정적으로 돌려 스킬(한국어 설명)·도구(영어 설명)를 만든다.
  같은 영역에서 대상·동작만 다른 near-duplicate 묶음이 어려운 경우다. description 은 두 벌 — 좋은 것(발동 낱말·쓰지 말 상황 포함)과 막연한 것.
- 질의(항목마다 넷): `exact` 설명의 언어로 발동 낱말 그대로 · `synonym` 동의어로 바꿔 · `cross-lang` 다른 언어로 · `task` kata 가 쓸 과제 문장.
- 지표: recall@1/3/10, MRR, 지연 p50/p95. 결과는 `results/<시각>.json`.
- 엔진(`engines.py`): `current` = 서버의 `PgFactStore.search`(tsvector AND + trgm similarity + ILIKE), `lexical-or` = 낱말 OR + `word_similarity`.

## 한계(정직하게)

- 템플릿 생성이라 실제 저자 글보다 규칙적이다. 조합 상한이 720 이라 `--n 1000` 은 720 으로 잡힌다. 5k 이상은 생성기를 넓혀야 한다(다음 단계: LLM 보강 집합).
- 한국어 형태소 분석이 없다. "추출해줘"와 "추출한다"는 어떤 어휘 엔진도 잇지 못한다 — 숫자에 그대로 나타난다.
- 진짜 카탈로그에는 mock 을 넣지 않는다. 이 장치는 코드 저장소 안에서만 돈다.

## 기준선 (2026-10-19, N=720, 좋은 description)

| 엔진 | R@1 | R@3 | R@10 | MRR | p50 ms |
|---|---|---|---|---|---|
| current | 0.259 | 0.259 | 0.259 | 0.259 | 5.4 |
| lexical-or | 0.395 | 0.531 | 0.686 | 0.479 | 5.5 |

스타일별 R@3(lexical-or): exact 0.99 · synonym 0.38 · cross-lang 0.24 · task 0.52. N=100→720 에서 synonym 0.70→0.38, cross-lang 0.54→0.24 로 떨어진다 — 규모 저하가 보인다.
막연한 description 은 두 엔진 다 0 근처다 — 엔진보다 설명 품질(review 점검표 A1·A3)이 먼저다.
`current` 가 R@1=R@3=R@10 인 이유: `plainto_tsquery` 가 낱말을 AND 로 묶어 한 낱말만 달라도 후보가 0 이다. 찾으면 1등, 아니면 없음.
