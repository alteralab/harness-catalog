# 검색 — 스킬·도구를 규모에서 잘 고르기 (2026-10-19)

`search_skills`·`search_tools`는 세션(사람)과 kata(루프 조립기)의 관문이다. kata는 상위 k(당분간 5, §3-6)만 보므로 거기서 틀리면 끝이다.
이 문서는 (1) 2026-10-19 리서치의 원장, (2) 벤치마크 결과, (3) 결정을 한곳에 둔다. 결정은 DESIGN §11에 행으로 간다.

## 1. 리서치 원장 — 무엇이 알려져 있는가

| 출처 | 핵심 발견 | 우리에게 뜻하는 것 |
|---|---|---|
| ToolRet (Shi et al., ACL Findings 2025) — 7,615 과제 · 43,215 도구 | 질의와 대상 도구 문서의 ROUGE-L 겹침 **0.06**(일반 IR 0.27~0.34). 최고 범용 임베딩(NV-Embed-v1 7B)도 nDCG@10 **33.83**, 모든 모델이 Completeness@10 35% 미만. BM25s는 질의만으로 22.32이나 **지시문을 붙이면 36.46**으로 올라 다수의 dense 모델을 앞선다. 리랭커(monoT5·mxbai·bge·jina)는 개선이 제한적(bge-reranker-v2-gemma만 +4.7%p C@10). ToolRet-train 200k로 학습하면 모든 모델이 크게 개선 | 어휘 엔진은 구조적으로 불리하다. 질의 쪽 **지시문/의도 추출**이 값싸고 크다. 리랭커는 만능이 아니다 |
| Tool-REX "Tools are under-documented" (Lu et al., ICLR 2026) | 문제의 뿌리는 **문서 품질**. 도구 문서를 `function_description`·`when_to_use`·`limitations`·`tags`로 확장하면 BM25와 dense 모델이 **모두** 오른다(ToolRet Avg nDCG@10: BM25s 36.41→39.35, Qwen3-Embedding-0.6B 43.52→45.65, -4B 45.54→45.65, -8B 46.21→46.21). `example_usage`는 오히려 해롭다. 확장 문서로 학습한 Tool-Embed-4B 52.23(+10.23 over SoTA), Tool-Rank-4B 리랭커 56.44 | 우리 description 규약(발동 낱말 + 쓰지 말 상황 = when_to_use + limitations + tags)이 정확히 이 방향이다. review 점검표 A1·A3이 엔진보다 먼저라는 벤치마크 결과와 일치 |
| Re-Invoke (Chen et al., EMNLP Findings 2024, Google) | 비지도. 색인 때 도구마다 **합성 질의**를 생성해 함께 색인하고, 검색 때 긴 사용자 질의에서 **의도만 추출**해 다중 관점으로 매칭. ToolE nDCG@5 단일 +20%, 다중 +39% | kata의 과제 문장(우리 `task` 스타일, R@3 0.52)에 바로 적용되는 기법: 조립기가 과제에서 의도를 뽑아 질의로 쓴다 |
| Toollery (2026) — 7.9만 capability | 스킬과 도구를 같은 "capability"로 두고, 문서 쪽 질의 확장 → 색인 → 상위 k 후보 압축 → LLM이 최종 선택. 고정 top-10 예산에서 end-to-end 선택 개선 | 우리 모양(스킬·도구 한 카탈로그, 조립기 top-3 → 모델 선택)과 같다 |
| MCP-Zero (2025) — 308 서버 · 2,797 도구 | 서버→도구 **2단계 조회**(score = (s_server×s_tool)×max), 모델이 `server`·`tool` 두 필드로 구조화 요청. APIBank 69.23%→95.19%, 토큰 98% 절감 | 도구에 server 필드가 있는 우리 `kind: mcp`에 그대로 맞는다. 구조화 요청은 조립기가 할 수 있다 |
| Anthropic Tool Search Tool (2025-11) | 연결된 도구 정의를 지연 적재하고 regex/BM25(또는 custom embeddings)로 찾는다. 토큰 85% 절감(72K→8.7K), Opus 4 49→74%, Opus 4.5 79.5→88.1%. "Clear, descriptive definitions improve discovery accuracy" | 세션에서 toolbox가 띄운 도구가 많아지면 쓸 것. 카탈로그에서 아직 안 받은 도구를 찾는 일은 대신 못 한다 — 레지스트리 검색은 남는다 |
| 하이브리드 관행 | BM25 + dense → RRF(k=60) → cross-encoder 리랭크(top-50~100). 학습 신호가 없으면 RRF가 가중 합보다 낫다 | 시작 모양은 이것. 단, ToolRet은 리랭커 효과가 작다고 하니 벤치마크로 확인 |

### 1b. 실제 시스템은 어떻게 하나 — 사례 (2026-10-19 딥 리서치, 사용자: "hybrid·rerank 를 괜히 쓰는 게 아닐 텐데")

| 시스템 | 무엇을 색인하나 | 어떻게 찾나 | 하이브리드·리랭크 | 숫자·한도 |
|---|---|---|---|---|
| **Anthropic Tool Search Tool** (API, 2025-11) | 도구 이름·설명·인자 이름·인자 설명 | 서버 쪽 regex 또는 BM25(모델이 질의를 씀), 기본 5개 반환. 클라이언트 쪽 custom search 로 임베딩 가능(쿡북: all-MiniLM-L6-v2, name+description+parameters 를 한 문장으로, 코사인 top-5, 하이브리드·리랭크 없음 — "BM25 와 섞는 것은 다음 개선") | 없음(서버 쪽은 어휘 하나) | 30~50개 넘으면 선택 정확도 저하, 10개 이상이면 권고, 최대 10,000 deferred. "Use keywords in descriptions that match how users describe tasks", 이름 접두 namespacing |
| **OpenAI Responses tool search** (gpt-5.4+) | namespace·MCP 서버의 이름·설명(개별 함수는 숨김) | 모델이 namespace/서버 단위로 적재(2단계 — MCP-Zero 와 같은 모양). hosted 또는 client-executed(`tool_search_call`/`tool_search_output`) | 없음 | namespace 당 함수 10개 미만 권고 |
| **Codex skills / Claude Code skills** | SKILL.md name+description 매니페스트 | 검색 없음 — 매니페스트를 프롬프트에 싣고 모델이 고름 | 없음 | Codex: 컨텍스트의 2%(미상이면 8,000자) 상한, 넘치면 설명을 줄이고 그래도 넘치면 일부 생략 + 경고 |
| **VS Code Copilot virtual tools** | 도구 묶음(서버·확장 단위) | 128개 초과 시 `activate_*` 가상 도구 뒤로 접고 모델이 묶음을 펼침, 최근 안 쓴 묶음부터 다시 접음 | 없음 | 요청당 하드 리밋 128 |
| **Cursor** | — | 없음. 활성 도구 약 40개 상한, 넘으면 조용히 안 보임 | 없음 | 40 |
| **langgraph-bigtool** | 도구 `description` 만 | LangGraph Store 의미 검색(text-embedding-3-small), `limit=2`, `retrieve_tools_function` 으로 교체 가능(예: 범주별) | 없음 | "수백~수천 도구" |
| **hermes-agent 제안**(이슈 #130044) | SKILL frontmatter 만(name·description·when_to_use·triggers·tags), 본문 제외 | 임베딩 top-K 를 사용자 메시지에 주입, 이미 로드된 스킬은 제외 | **BM25/FTS5 는 임베딩 API 가 죽었을 때의 대체 경로** — 우리 결정과 같은 모양 | 70+ 스킬에서 약 300ms |
| **RAG-MCP** (2025) | MCP 도구 설명 | 의미 검색 top-k 만 | 없음 | 선택 정확도 13.62% → 43.13%, 토큰 −50% |
| **ScaleMCP** (2025, 도구 5,000) | 이름·설명·파라미터·합성 질문(TDWA 가중 0.2/0.3/0/0.5) | 벡터·하이브리드·BM25·Cohere 리랭크·LLM 리랭크 다섯을 비교 | **벡터 R@5 0.91 vs BM25 0.66**; Cohere 리랭크 R@5 0.90(nDCG +0.02); LLM 리랭크 R@5 0.93~0.94(nDCG +0.05~0.06) | 단순 concat 이 TDWA 보다 벡터 검색에서 나음 |
| **Toolshed** (2024, "Advanced RAG-Tool Fusion") | 이름(공백 넣어 풀어씀)+설명+인자 스키마+합성 질문+핵심 의도 | 질의 재작성·분해·다중 질의 확장 → 벡터 검색(text-embedding-3-large) → LLM 리랭커로 top-k 압축 | 논문 본문은 "하이브리드(sparse+dense)"를 언급하나 표의 차별점은 **문서 확장과 질의 분해**; 리랭커는 LLM("임베더 리랭커로 바꿀 수 있다") | ToolE 단일 R@5: BM25 0.462 → Re-Invoke 0.871 → Toolshed 0.928; Seal-Tools R@5 BM25 0.410 → 0.876 |
| **Anthropic Contextual Retrieval** (2024, 문서 청크) | 청크 + LLM 이 붙인 문맥 | 임베딩 + BM25 → rank fusion → top-150 → 리랭크 → top-20 | **하이브리드가 핵심**: 실패율 5.7% → 임베딩만 3.7%(−35%) → +BM25 2.9%(−49%) → +리랭크 1.9%(−67%) | BM25 가 이기는 자리: "Error code TS-999" 같은 식별자·기술 용어 |
| Bruch 외 (2022, 결합 함수 분석) | — | — | **RRF 는 매개변수와 약한 쪽에 민감, 볼록 결합(정규화 점수 α 합)이 안팎 도메인 모두에서 낫고 예 몇 개로 α 를 맞출 수 있다** | — |
| 한국어 BM25 토크나이저 벤치(AutoRAG, Allganize 세트) | — | 공백 vs okt/kiwi/kkma | okt 가 공백을 크게 앞섬(R@3 0.956, R@5 0.965); **이 세트에서는 BM25(okt) 가 임베딩 모델을 순위 지표에서 앞섬** | 형태소 없는 어휘 엔진은 한국어에서 반쪽 |
| 운영 글(tianpan 2026) | — | — | 어휘가 이기는 다섯 자리: 오류 코드·식별자, 모델 번호·SKU, 함수·라이브러리 이름, 희귀 고유명사, 통제 어휘. Elasticsearch 실측: 단순 RRF +1.3% nDCG, 계층(식별자 질의는 어휘 우선) +7.5% | — |

**읽는 법.** 하이브리드와 리랭커가 "괜히" 있는 것은 아니다 — 있는 이유가 정확히 둘이다. (1) **임베딩이 뭉개는 토큰**: 식별자·오류 코드·함수 이름·희귀 고유명사·통제 어휘. 문서 청크 검색(Contextual Retrieval)과 운영 로그·코드 검색에서 어휘가 크게 이기는 자리이고, 도구 검색에서도 이름·명령·API 이름이 그 자리다. (2) **첫 단계 recall 이 모자랄 때의 보정**: 리랭커는 top-k 안에 정답이 있는데 순위가 틀릴 때 돕는다. 반대로 **도구·스킬처럼 짧고 잘 쓰인 문서**에서는 ScaleMCP(5,000 도구)·Toolshed(ToolE)·RAG-MCP 모두 임베딩이 BM25 를 크게 앞서고, cross-encoder 리랭크는 recall 을 거의 안 올린다(ScaleMCP 0.91 → 0.90). 이 두 결론은 우리 첫 판과 맞는다. 첫 판이 공정하지 않았던 자리도 둘이다. 어휘 쪽이 Postgres `simple` OR(형태소도 BM25 도 없음)이었고, 질의에 식별자·희귀 토큰이 없었다. 그래서 v2 벤치마크는 BM25(한글 2-gram) + 볼록 결합 + 식별자(`name`)·희귀 토큰(`jargon`) 질의로 다시 잰다(§2).

### 모델 후보 (한국어·영어 혼용 카탈로그, 사내 인프라에서 로컬 실행)

| 모델 | 크기 | 라이선스 | 근거 |
|---|---|---|---|
| **Qwen3-Embedding-0.6B / 4B** | 0.6B / 4B | Apache-2.0 | 100+ 언어, 지시문 인식(질의 지시문 없으면 1~5% 하락), MTEB 다국어 1위(8B 70.58). Tool-REX의 Tool-Embed 기반 모델. 짝 리랭커 Qwen3-Reranker-0.6B(Apache) |
| **KURE-v1** (bge-m3 한국어 미세조정) | 568M | MIT | MTEB-ko-retrieval nDCG@10 0.7616(bge-m3 0.7509, KoE5 0.7337). 한국어 질의에 가장 안전. 짝 리랭커 KURE-Reranker-nano 149M |
| KURE-v2 (late interaction) | 154M | MIT | 0.8160으로 1위지만 다중 벡터라 pgvector 한 열로 못 담는다 — 보류 |
| bge-m3 | 568M | MIT | 다국어 기본선. sparse·colbert도 내지만 dense만 쓰면 KURE-v1이 상위 호환 |
| multilingual-e5-small | 118M | MIT | 가장 가볍다. 질이 모자라면 대안 아님 |
| jina-embeddings-v3 / v4 | 570M / 3.8B | **CC BY-NC 4.0** / Qwen Research | 과제별 LoRA(retrieval.query/passage) 설계는 좋으나 비상업 라이선스. 한국어 리더보드에서도 bge-m3 아래(평균 recall 0.483 vs 0.518). 사내 제품이라도 상업 사용에 해당할 수 있어 후보에서 뺀다 |

### Jev (TypeSafe AI) — 임베딩이 아니라 "결정 모델", 자리는 리랭커·최종 선택

처음 조사에서 "Jev"를 jina-embeddings-v3 로 잘못 짚었다(2026-10-19, 사용자가 hotchpotch 의 jev-reranker 글로 바로잡음). 정정한 사실:

| 항목 | 사실 | 출처 |
|---|---|---|
| 무엇인가 | TypeSafe AI 의 호스팅 "System One" 모델. 글을 생성하지 않고 **Choice(선택지별 확률)·Score(루브릭 점수)·Noul(예/아니오 확률)** 로 답한다. 보정(calibration)된 확률을 내도록 학습 | docs.typesafe.ai/concepts/system-one |
| 접근 | `POST https://api.typesafe.ai/v1/systemone`, Python SDK `typesafe-sdk`(`TypeSafeClient().system_one(state, questions, model)`), 가중치 비공개. 판: jev-1.13.0(`jev-latest`), jev-1.14.0(`jev-preview`, 2026-10-14) | docs.typesafe.ai/models |
| 비용·지연·한도 | 입력 토큰 $0.042/M, 출력 무료. 70~500ms. 요청당 64k, 질문당 32k 토큰. Choice 선택지 최대 255 | 위 + firecrawl "What is Jev" |
| 언어 | "English is the primary training language … Other languages, including CJK scripts, are handled but not equally well; test on your own content" | docs.typesafe.ai/models |
| 리랭킹 성적 | Elastic(ESCI 250 질의): 하이브리드 0.9351 → Jev 포인트와이즈 0.9565 nDCG@10(+0.021). TypeSafe 쿡북(판례 인용 검색, 후보 30): Top-1 5→18%, Top-10 38→62%, 1,200 호출 $0.0645. Parallel.ai: 검색 리랭킹 nDCG@10 0.7 로 자체 모델과 비슷, 레이블이 많은 분류는 뒤짐 | elastic.co search-labs, docs.typesafe.ai/cookbooks/rerank_typesafe, parallel.ai/blog/testing-jev |
| 못 하는 것 | 산술·날짜 비교, 다중 홉 추론, 생성. "literal reading", 적대적 입력에 약함 | firecrawl |
| 열린 대안 | hotchpotch/bekko-system-one-v0-68m(ModernBERT 계열 68M, 영어 전용, S1MB 40.46 vs Jev 59.59 — 멀다), openjev/openjev(27B, CC BY-NC, H100 필요). 둘 다 우리 자리에 안 맞는다 | 모델 카드 |

**우리에게 뜻하는 것.** Jev 는 벡터를 내지 않으므로 검색 1단계(수백·수천에서 후보 모으기)는 대신 못 한다. 자리는 둘이다.
(1) **리랭커**: 하이브리드 상위 10~20 을 후보마다 Noul 한 번으로 다시 매긴다 — 로컬 cross-encoder(bge-reranker-v2-m3) 대신 호스팅 호출. 장점은 운영할 모델이 없다는 것, 단점은 외부 의존·호출당 과금·한국어 미검증.
(2) **최종 선택**: kata 조립기가 상위 3 중 하나를 고르는 자리에 Choice 를 쓸 수 있다 — 지금은 모델(LLM)이 고른다. 토큰·지연이 훨씬 싸다.
둘 다 **숫자로 정한다**. `bench/search --jev`(TYPESAFE_API_KEY) 가 하이브리드 상위 10 을 Jev 로 다시 매겨 같은 표에 적는다(엔진 `hybrid+jev:<모델>`). **2026-10-19 실측(§2 표·"숫자가 말한 것" 4)**: 리랭커 자리에서는 dense 단독보다 나빴고 한국어 동의어에서 잃는다 → (1)은 닫는다. (2) 최종 선택·"맞는 스킬 없음" 판정·과제 종류 분류·되돌릴 수 없는 호출 판정·주입 걸러내기 같은 **빠른 판단 자리는 kata 쪽**이고, 거기서 한국어 과제 문장으로 따로 잰다. 호출당 입력 토큰은 질의+설명 한 쌍에 약 450 이었다. 사내 내용(과제 문장·스킬 설명·호출 인자)이 밖으로 나가는 범위도 그때 정한다.

## 2. 벤치마크 (`bench/search/`, `make bench-search`)

`bench/` 는 저장소에 넣지 않는다(`.gitignore`, 2026-10-19 사용자 결정) — 로컬 측정 장치이고, 숫자와 결론은 이 문서가 정본이다. 기준선과 결과는 아래 표에 누적한다. 말뭉치·질의·지표·플래그는 로컬 `bench/search/README.md`.

| 날짜 | 조건 | R@1 | R@3 | R@10 | MRR | p50 ms |
|---|---|---|---|---|---|---|
| 2026-10-19 | current(tsvector AND + trgm), N=720, 좋은 설명 | 0.259 | 0.259 | 0.259 | 0.259 | 5.4 |
| 2026-10-19 | lexical-or(OR + word_similarity) | 0.395 | 0.531 | 0.686 | 0.479 | 5.5 |
| 2026-10-19 | dense:e5-small(118M) | 0.687 | 0.848 | 0.934 | 0.774 | 6.3 |
| 2026-10-19 | dense:bge-m3 | 0.859 | 0.953 | 0.989 | 0.909 | 15.7 |
| 2026-10-19 | **dense:KURE-v1** | 0.855 | 0.962 | 0.989 | 0.908 | 15.3 |
| 2026-10-19 | dense:Qwen3-Embedding-0.6B | 0.533 | 0.816 | 0.948 | 0.685 | 23.6 |
| 2026-10-19 | hybrid RRF(어휘 50 + dense 50) — bge-m3 / KURE / Qwen3 | 0.691 / 0.691 / 0.585 | 0.882 / 0.886 / 0.814 | 0.955 / 0.954 / 0.945 | 0.79 / 0.79 / 0.71 | 47~65 |
| 2026-10-19 | hybrid RRF(어휘 3 + dense 50), KURE | 0.637 | 0.770 | 0.988 | 0.748 | 48 |
| 2026-10-19 | hybrid + bge-reranker-v2-m3(상위 20), KURE | 0.864 | 0.951 | 0.967 | 0.908 | 151 |
| 2026-10-19 | **dense:KURE-v1 + 확장 문서**(이름·설명·발동 낱말) | **0.923** | **0.977** | 0.993 | 0.951 | 15.1 |
| 2026-10-19 | dense:Qwen3-0.6B + 확장 문서 | 0.662 | 0.892 | 0.975 | 0.782 | 23.6 |
| 2026-10-19 | 막연한 설명 — current / lexical-or / dense:KURE | 0.000 / 0.006 / 0.014 | 0.000 / 0.016 / 0.045 | 0.000 / 0.055 / 0.151 | — | — |
| 2026-10-19 | hybrid + Jev(jev-1.13.0, Noul, 상위 10), KURE | 0.774 | 0.924 | 0.954 | 0.849 | 264(12 병렬) |

스타일별 R@3(좋은 설명, N=720): lexical-or exact 0.99 · synonym 0.38 · cross-lang 0.24 · task 0.52 → dense:KURE exact 1.00 · synonym 0.88 · cross-lang 0.98 · task 0.99. 지연은 Apple MPS 기준 질의 임베딩 포함.

### v2 (2026-10-19 밤) — 제대로 된 어휘 엔진, 볼록 결합, 식별자·희귀 토큰 질의

말뭉치 v2: 설명에 동작별 고유 명사 32개(`yt-dlp`, `git range-diff`, `pdfplumber`, `conversations.history` …)를 넣고, 질의 스타일을 넷에서 여섯으로(`name` = 이름 그대로, `jargon` = 고유 명사 + 동의어). 질의 4,320개. 전부 확장 문서(이름·설명·발동 낱말), KURE-v1.

| 엔진 | R@1 | R@3 | R@10 | MRR | p50 ms | synonym R@3 | name R@3 |
|---|---|---|---|---|---|---|---|
| current(tsvector AND) | 0.505 | 0.505 | 0.505 | 0.505 | 6.1 | 0.02 | 1.00 |
| lexical-or(Postgres simple OR) | 0.564 | 0.680 | 0.785 | 0.632 | 6.2 | 0.38 | 1.00 |
| **bm25**(낱말 + 한글 2-gram, rank_bm25) | 0.902 | 0.940 | 0.953 | 0.921 | **0.3** | 0.64 | 1.00 |
| dense:KURE-v1 | 0.923 | 0.979 | 0.995 | 0.952 | 15.4 | 0.90 | 0.98 |
| hybrid RRF(lexical-or + dense) | 0.785 | 0.928 | 0.972 | 0.860 | 53 | 0.70 | 1.00 |
| hybrid RRF(bm25 + dense) | 0.924 | 0.956 | 0.979 | 0.942 | 15.7 | 0.73 | 1.00 |
| hybrid CC α=0.5 | 0.944 | 0.968 | 0.988 | 0.958 | 15.7 | 0.81 | 1.00 |
| hybrid CC α=0.7 | 0.945 | 0.977 | 0.992 | 0.962 | 15.8 | 0.86 | 1.00 |
| **hybrid CC α=0.85** | **0.947** | **0.982** | **0.995** | **0.965** | 15.6 | 0.89 | 1.00 |
| hybrid(lexical-or) + bge-reranker | 0.940 | 0.974 | 0.979 | 0.957 | 211 | 0.85 | 1.00 |

(exact·jargon·task·cross-lang 은 bm25·dense·CC 모두 1.00 — cross-lang 이 1.00 인 것은 확장 문서에 영어 발동 낱말이 들어가서다.)

**v2 가 뒤집은 것과 지킨 것.**
- **하이브리드는 이득이다 — 어휘가 BM25 이고 결합이 볼록 결합일 때.** CC α=0.85 가 dense 단독보다 R@1 +0.024, R@3 +0.003, 식별자(`name`) 0.98→1.00. 비용은 BM25 0.3ms 라 사실상 0. 사용자 지적("관행이 괜히 있는 게 아니다")이 맞았고, 첫 판의 "하이브리드 손해"는 **약한 어휘 엔진 + RRF** 의 결과였다.
- **RRF 는 BM25 와 섞어도 dense 단독보다 나쁘다**(0.956 < 0.979). Bruch 외(2022)대로 — 두 순위를 동등하게 세면 BM25 가 못 잡는 한국어 동의어(0.64)가 dense 의 0.90 을 끌어내린다. 결합은 α 가 큰 볼록 결합이어야 한다.
- **BM25 혼자서도 R@3 0.940** — 대체 경로(임베딩 서비스가 죽었을 때)로 충분히 강하다. 지금 tsvector(0.505~0.680)와는 급이 다르다. 한글 2-gram 하나가 그 차이다.
- **리랭커는 여전히 본전 이하**(0.974, 지연 14배).
- 남는 구멍 하나는 **한국어 동의어·활용**(CC 0.89)이고, 이것은 어휘로 못 메우고 더 나은 임베딩이나 저자가 description 에 동의어를 적는 것(review A1)으로 메운다.

### k 곡선 (2026-10-19 밤, v2 말뭉치, 확장 문서, KURE-v1) — "상위 3" 은 적절한가

| 엔진 | R@1 | R@2 | R@3 | R@5 | R@10 |
|---|---|---|---|---|---|
| bm25 | 0.902 | 0.927 | 0.940 | 0.947 | 0.953 |
| dense:KURE-v1 | 0.923 | 0.966 | 0.979 | 0.989 | 0.995 |
| hybrid RRF(bm25) | 0.924 | 0.947 | 0.956 | 0.965 | 0.979 |
| hybrid CC α=0.7 | 0.945 | 0.968 | 0.977 | 0.986 | 0.992 |
| hybrid CC α=0.85 (v2 실행) | 0.947 | — | 0.982 | — | 0.995 |

스타일별(CC α=0.7): exact·jargon·name·task·cross-lang 은 **k=2 에서 1.00** 에 닿는다. 손실은 전부 **synonym**(한국어 동의어·활용)이다: k=1 0.69 → 2 0.81 → 3 0.86 → 5 0.92 → 10 0.95.

**읽는 법.** k 를 3 에서 5 로 올리면 전체 R@k 가 0.98 → 0.99(+0.01), 5 에서 10 은 +0.006. 늘어나는 비용은 후보 설명 두 줄(약 100~200 토큰)과 워크트리에 실체화하는 스킬 둘이고, 모델의 선택 정확도는 Toolshed 실측대로 128개까지 흔들리지 않는다. 사례의 k 는 1(MCP-Zero·RAG-MCP)·2(bigtool)·5(Anthropic 기본·ScaleMCP)·10(Toollery) 에 퍼져 있고 "전부 보여 주는 매니페스트"도 있다. **제안: k=5** — "R@k 가 0.99 를 처음 넘는 k" 규칙으로 정한 값이고, Anthropic Tool Search 의 기본값과 같다. 여기에 둘을 붙인다. (a) 점수 꼬리 자르기: 1등과의 결합 점수 차가 문턱(벤치로 정함)을 넘는 후보는 버려 보통은 2~3개만 넘어간다. (b) MCP-Zero 식 **재요청**: 모델이 "맞는 것이 없다"고 하면 조립기가 질의를 바꿔 다시 찾는다 — 이 길이 있으면 k 를 더 올릴 이유가 없다. "k 중 모델이 실제로 맞게 고르는 비율"은 검색 벤치로 못 재고 kata 의 Harbor 과제(후보 k 를 프롬프트에 싣고 모델이 고르게)로 잰다.

### 숫자가 말한 것 (v1, 2026-10-19 낮)

1. **dense 하나면 된다.** KURE-v1·bge-m3 가 동의어·다른 언어·과제 문장을 거의 다 잡는다(R@3 0.95~0.96). 가장 가벼운 e5-small 도 어휘보다 훨씬 낫다(0.848).
2. **어휘를 RRF 로 섞으면 어느 깊이든 나빠진다**(0.96 → 0.89 / 0.77). 어휘 OR 이 틀린 후보를 높은 순위로 밀어 넣기 때문이다. 하이브리드가 "관행"이라고 그대로 들여오면 손해다 — 벤치마크가 있어서 잡혔다. 어휘는 섞지 않고 **대체 경로**(임베딩을 못 쓸 때)로만 둔다.
3. **문서 확장이 가장 싸고 가장 크다.** 색인 문서를 `name + description + 발동 낱말` 로 하면 R@1 0.855→0.923, R@3 0.962→0.977. Tool-REX 와 같은 방향이고 비용은 0.
4. **리랭커는 로컬도 Jev 도 본전 이하.** bge-reranker: R@1 +0.009, R@3 −0.011, 지연 10배. **Jev**(하이브리드 상위 10 을 후보마다 Noul 한 번, 28,800 호출, 입력 13.0M 토큰 ≈ $0.55): 입력이던 하이브리드(0.691/0.886)보다는 올렸지만 dense 단독(0.855/0.962)과 bge-reranker(0.864/0.951)에 못 미쳤다 — R@1 0.774, R@3 0.924. 스타일별로 보면 동의어 0.77(dense 0.88), 발동 낱말 그대로 0.97(dense 1.00)에서 잃었다 — 한국어 동의어·활용에서 "CJK handled but not equally well" 이 그대로 보인다. 상위 3 recall 이 이미 0.96 이라 어느 리랭커도 다시 매길 여지가 없고, 한국어에서는 Jev 가 오히려 맞는 것을 끌어내린다. **리랭커 칸은 비운다.**
5. **막연한 설명은 어떤 엔진도 못 살린다**(R@3 ≤ 0.05). 엔진이 아니라 review 점검표 A1·A3 이 지렛대다.
6. Qwen3-Embedding-0.6B 가 뒤지는 것(0.816)은 질의 지시문·왼쪽 패딩 등 모델 카드 설정을 다 맞추지 않은 탓일 수 있다 — 한국어 미세조정 모델이 이미 충분해 더 쫓지 않는다.

## 2b. Codex 적대적 검토 (2026-10-19 밤) — "가장 좋은 설계인가, 싸 보여서 고른 것인가"

사용자 질문에 답하려고 제안 전체를 Codex 에 적대적으로 검토시켰다(원문 `~/workspace/loop-engineering/codex-review-search-0.8.0.md`). 결론은 **"그대로 확정하면 안 된다"** 이고, 지적은 맞는 것이 대부분이다. 받아들인 것과 그에 따른 조치:

| 지적 | 받아들임 | 조치 |
|---|---|---|
| 말뭉치·질의가 같은 템플릿에서 나와 생성 규칙 복원에 가깝다; 스타일 1/6 균등 가중은 실제 분포와 무관 | 맞다. 합성 벤치는 **엔진 간 상대 비교**와 **실패 모드 발견**(AND 질의, RRF 끌어내림, 식별자)에 쓸 수 있을 뿐 절대값·α·k 확정 근거가 못 된다 | 절대값 주장 삭제. 실제 질의 집합(Langfuse 검색 스팬 + 수동 작성)을 시간순 holdout 으로 만들어 α·k 를 거기서 다시 고른다(§3-7) |
| α=0.85 를 같은 질의로 고르고 보고(과적합); 0.7→0.85 차이는 23건 | 맞다 | `--holdout`: 영역 반(youtube·git·docs·data)에서 α 를 고르고 나머지 반에서 한 번만 평가(실행 I). α 는 **설정값**이고 0.85 는 임시 기본값 |
| cross-lang 1.00 은 반대 언어 발동 낱말이 문서에 들어간 누출 | 맞다 | cross-lang 은 "번역 능력"이 아니라 "발동 낱말을 두 언어로 적으면 잡힌다"로만 읽는다. review A1 이 요구하는 바이기도 하다 |
| 지연이 MPS 인프로세스; 운영 TEI arm64 CPU HTTP 경로 미측정 | 맞다 | 같은 arm64 Mac 에서 TEI `cpu-arm64-1.9` 컨테이너를 띄워 HTTP p50/p95/p99·색인 시간·RSS 실측(아래 표). 인프로세스 CPU 도 쟀다: KURE-v1 질의 p50 55ms, 720 문서 색인 13s |
| Kiwi 형태소 BM25 가 핵심 대안인데 빠짐 | 맞다 | `tokenize_kiwi`(kiwipiepy 0.24, Apache-2.0: 문장부호·조사·어미 제거, 어간·기본형) 추가, 2-gram 과 같은 표에서 비교(실행 I) |
| KURE-v2 를 "pgvector 한 열" 때문에 뺀 논리가 메모리 설계와 충돌 | 맞다 — 메모리 계산이면 late interaction 도 된다 | `LateInteraction`(sentence-transformers `MultiVectorEncoder`, 토큰당 128차원, MaxSim) 추가, KURE-v1 과 같은 표에서 비교(실행 H). 문서당 벡터 수·메모리도 적는다 |
| 재임베딩 캐시: `real[]` 열만으로는 전량 DELETE/INSERT 때 재사용이 없다; 모델 판·문서 판이 벡터에 없다 | 맞다 | 캐시 키 = `sha256(색인 문서) + 모델 revision + 색인 문서 schema 판`. 열은 `embedding real[]`, `embedding_key text`. `replace_index` 가 새 행의 키를 옛 행에서 찾아 재사용하고 없는 것만 임베딩 요청. 키가 다른 벡터는 섞지 않는다(한 세대만) |
| TEI 자원 예산·기동 순서·`/readyz` 의미 불명확 | 맞다 | readyz 에 `embedding` 블록(모델 판, 벡터 세대, 사유 `embedding_unavailable`). 상태 셋: (a) 벡터 있음+TEI 불가 → 질의 임베딩 불가라 BM25 단독, (b) 첫 기동+TEI 늦음 → BM25 로 ready, 벡터는 뒤에 채움, (c) 부분 임베딩 → 그 세대는 쓰지 않고 이전 세대 유지. compose 는 TEI 를 `depends_on` 으로 묶지 않는다(레지스트리는 TEI 없이도 뜬다) |
| 다중 워커 메모리 중복 | 맞다 | 단일 워커 전제를 operations 에 명시, 워커당 메모리 = N × (4 KiB + BM25 posting). KURE-v2 면 N × 토큰수 × 512 B |
| "수만이면 pgvector" 는 근거 없는 문턱 | 맞다 | 전환 기준을 계측 가능하게: 상주 색인이 워커 메모리 예산의 25% 초과, 목표 동시성에서 p95 가 SLO 초과, 재구축이 fetch 간격 초과. 그때 pgvector·ParadeDB(pg_search+pgvector 한 이미지, AGPL 검토)·late interaction 색인을 함께 재평가 |
| k=5: α=0.85 의 R@5 가 결과 파일에 없고, "R@k≥0.99 첫 k" 규칙을 문자 그대로 적용하면 k=10 | 맞다 | 실행 H 가 α=0.85 의 R@1/2/3/5/10 을 저장. 규칙을 바꾼다: k 는 "0.99 규칙"이 아니라 **비용-recall 무릎**(3→5 +0.01, 5→10 +0.006; Anthropic 기본 5 와 같은 값)으로 고른 **임시 기본값**이고 설정값이다. 확정은 kata Harbor 과제(k 별 모델 선택 정확도·토큰·재질의율)가 한다 |
| Langfuse 재튜닝 경로 없음 | 맞다 | 검색 스팬에 후보 목록·점수·선택된 항목(get_skill 호출로 연결)·결과 0·재질의를 남긴다 → 약한 relevance label → 시간순 분할로 α·k·꼬리 문턱을 주기적으로 offline replay. DESIGN §2 사용 기록 표 개정 대상 |
| SPLADE·Anthropic Tool Search 2단계 중복 미평가 | 보완 | SPLADE 는 검증된 한국어 모델·TEI 호환·CPU 비용이 불리해 **검토 후 제외**로 적는다. 2단계(레지스트리 k → 세션 Tool Search)는 kata end-to-end 평가 항목 |
| BM25 폴백 0.940 은 균등 혼합 결과 | 맞다 | 폴백 품질은 "동의어 질의에서 0.64" 로 적고, 폴백은 가용성 보장이지 품질 보장이 아니라고 쓴다 |

받아들이지 않은 것: 없다. 다만 "범위를 줄여야 하면 BM25 + 관측부터 배포하고 dense 는 feature flag" 는 그대로 채택할 가치가 있다 — 0.8.0 을 두 단계로 나눈다(§3-5).

### 추가 실측 (실행 H·I, TEI)

**실행 H — KURE-v2 late interaction (v2 말뭉치, 확장 문서, 질의 4,320)**

| 엔진 | R@1 | R@2 | R@3 | R@5 | R@10 | synonym R@3 | name R@3 | p50 ms(MPS) |
|---|---|---|---|---|---|---|---|---|
| dense:KURE-v1 (568M, 1×1024) | 0.923 | 0.966 | 0.979 | 0.989 | 0.995 | 0.899 | 0.979 | 15.3 |
| hybrid CC α=0.85 (KURE-v1 + BM25) | 0.947 | 0.972 | 0.982 | 0.990 | 0.995 | 0.894 | 0.997 | 15.6 |
| **late:KURE-v2 (154M, 토큰당 128, MaxSim)** | 0.943 | 0.972 | 0.981 | 0.988 | 0.995 | 0.887 | **1.000** | 17.0 |
| CC α=0.85 (KURE-v2 + BM25) | 0.944 | 0.970 | 0.979 | 0.986 | 0.995 | — | — | 17.9 |

KURE-v2 **단독**이 KURE-v1 + BM25 하이브리드와 같은 자리(R@3 0.981 vs 0.982, R@1 0.943 vs 0.947)다. 토큰 단위 MaxSim 이 식별자 일치(name 1.00)를 스스로 잡아서 BM25 를 더해도 이득이 없다(0.979). 720 문서가 55,379 벡터 × 128 = 28 MB(문서당 약 39 KB). 모델은 KURE-v1 의 1/3.7 크기.

**실행 I — Kiwi 형태소 BM25 vs 2-gram, holdout α (v2 말뭉치, 확장 문서)**

| 엔진 | R@1 | R@3 | R@5 | R@10 | synonym R@3 |
|---|---|---|---|---|---|
| bm25 (2-gram) | 0.902 | 0.940 | 0.947 | 0.953 | 0.64 |
| bm25-kiwi (형태소·어간, 조사·어미 제거) | 0.849 | 0.928 | 0.947 | 0.956 | 0.64 |
| CC α=0.85, 2-gram | 0.947 | 0.982 | 0.990 | 0.995 | 0.89 |
| CC α=0.85, kiwi | 0.943 | 0.982 | 0.990 | 0.995 | 0.90 |
| CC α ∈ {0.5, 0.7, 0.85, 0.95}, 2-gram — R@3 | 0.968 / 0.977 / 0.982 / 0.981 | | | | |

Kiwi 는 단독으로는 2-gram 보다 못하고(짧은 설명에서 어간 하나로 줄어 변별이 떨어짐) 하이브리드에서는 같다. 동의어 구멍(0.64)은 둘 다 못 메운다 — 형태소가 아니라 어휘 자체가 다르기 때문. **2-gram 을 유지**하고 Kiwi 의존성은 넣지 않는다. α 는 0.7~0.95 사이가 평평하다(0.977~0.982).

**Holdout(영역 반반 — train: youtube·git·docs·data 에서 α 선택, test: infra·slack·pdf·calendar 1,920 질의에서 한 번 평가)**: 선택된 α=0.85(두 토크나이저 모두). test 에서 dense 0.925/0.988(R@1/R@3) → CC 0.959/0.990. **하이브리드 이득은 안 본 영역에서도 유지**(R@1 +0.034)되고 과적합의 증거는 없다. 다만 Codex 지적대로 이것은 "같은 템플릿의 다른 영역"이지 실제 질의가 아니다.

**실행 J — Ollama(mini 호스트, Metal) 의 KURE-v1 GGUF BF16 vs fp32 sentence-transformers (v2 말뭉치, 확장 문서, 질의 4,320)**

| 엔진 | R@1 | R@2 | R@3 | R@5 | R@10 | MRR | name R@3 | synonym R@3 |
|---|---|---|---|---|---|---|---|---|
| dense fp32 (sentence-transformers, MPS) | 0.923 | 0.966 | 0.979 | 0.989 | 0.995 | 0.952 | 0.98 | 0.90 |
| **dense Ollama BF16 GGUF** (`hf.co/mykor/KURE-v1-gguf:BF16`) | 0.923 | 0.966 | 0.979 | 0.989 | 0.995 | 0.952 | 0.98 | 0.90 |
| CC α=0.85 fp32 + BM25 | 0.947 | 0.972 | 0.982 | 0.990 | 0.995 | 0.965 | 1.00 | 0.89 |
| **CC α=0.85 Ollama + BM25** | 0.947 | 0.973 | 0.982 | 0.990 | 0.995 | 0.965 | 1.00 | 0.89 |

GGUF BF16 변환은 순위를 바꾸지 않는다(모든 지표·스타일 동일). 지연은 ssh 터널 경유 p50 99 ms(mini 로컬 68 ms). **Ollama 경로 확정.**

**실행 K — 회귀 게이트: 서버 모듈 `harness_catalog_core.search` 를 벤치에 그대로 꽂음 (`--app`, v2 말뭉치, 확장 문서, 질의 4,320, 2026-10-19 밤)**

| 엔진 | R@1 | R@2 | R@3 | R@5 | R@10 | MRR | synonym R@3 | name R@3 |
|---|---|---|---|---|---|---|---|---|
| current(0.7.x SQL: tsvector AND + trgm + ILIKE — 벤치 전용 기준선으로만 남김) | 0.505 | 0.505 | 0.505 | 0.505 | 0.505 | 0.505 | — | — |
| bm25 (벤치 엔진, rank_bm25) | 0.902 | 0.927 | 0.940 | 0.947 | 0.953 | 0.921 | 0.64 | 1.00 |
| **app-bm25(core.search)** — `SearchIndex.search(q, None)` | 0.902 | 0.928 | 0.940 | 0.948 | 0.954 | 0.922 | 0.64 | 1.00 |
| **app-hybrid(core.search)** — `SearchIndex.search(q, qvec)`, KURE-v1 fp32 | 0.947 | 0.972 | 0.981 | 0.990 | 0.995 | 0.966 | 0.89 | 1.00 |

앱 모듈(자체 BM25: Lucene idf·k1 1.5·b 0.75, min-max 볼록 결합 α=0.85)이 벤치 엔진과 같은 자리다(하이브리드 0.981 vs 0.982, BM25 0.940 = 0.940). 이 표가 검색 PR 의 게이트다 — `make bench-search` 가 아니라 `uv run --group bench python -m bench.search --n 720 --app --expanded --good-only --alphas 0.85`.

**TEI 운영 경로 실측 (같은 arm64 Mac, Docker VM 8 GB, `text-embeddings-inference:cpu-arm64-1.9`, KURE-v1)**

| 경로 | 질의 p50 / p95 / p99 | 720 문서 색인 | RSS |
|---|---|---|---|
| TEI cpu-arm64 (candle 백엔드 — ORT 는 model.onnx 없어 못 뜸) HTTP | 194 / 221 / 236 ms | **375 s** | 2.38 GiB |
| 인프로세스 torch CPU, KURE-v1 (sentence-transformers) | 55 / 57 ms | 13 s | — |
| 인프로세스 torch CPU, **KURE-v2** (MultiVectorEncoder) | 82 / 92 ms | 62 s | 프로세스 maxrss 903 MB |
| 인프로세스 MPS (벤치 조건) | 15 ms | 수 초 | — |

KURE-v2 는 모델이 작은데도 CPU 에서 질의 1.5배·색인 4.8배 느리다(질의가 64 토큰으로 패딩되고 문서는 토큰마다 출력). 품질은 KURE-v1+BM25 와 같고 식별자는 더 잘 잡지만, 단일 벡터 쪽이 CPU 비용·저장(문서당 4 KB vs 39 KB)·점수 계산 단순함에서 앞선다.

TEI 는 기본 워밍업(`--max-batch-tokens` 16384·4096)에서 **8 GB VM 안에서 OOM(137)** 으로 두 번 죽었고 `--max-batch-tokens 512 --max-batch-requests 2` 로 줄여야 떴다. 뜬 뒤에도 candle CPU 가 torch CPU 보다 질의 3.5배, 색인 **29배** 느리다. HF 직접 다운로드도 한 번 실패해 로컬 스냅샷을 마운트했다. **결론: Apple Silicon Docker 에서 TEI arm64 CPU 이미지는 이 모델에 맞는 런타임이 아니다.** 옆 컨테이너를 고집하지 않는다 — 레지스트리 프로세스 안에서 torch CPU 로 돌리거나(이미지 +1.5 GB, 질의 55ms), ONNX 로 내보내 onnxruntime 으로 돌린다(가벼움, 미측정). Codex 의 "TEI 자원 예산" 지적이 실측으로 확인된 셈이다.

### 2c. Codex 구현 검토 (2026-10-19 밤, 작업 트리 diff) — 7건, 전부 반영

원문 `~/workspace/loop-engineering/codex-review-search-impl-0.8.0.md`. 정상 경로(BM25 공식·α 결합·limit·응답·스팬·Postgres 교체 트랜잭션)는 적합 판정. 지적과 조치:

| # | 심각도 | 지적 | 조치 |
|---|---|---|---|
| 1 | 높음 | 같은 커밋에서 임베더가 한 번 실패하면 `_resync` 로만 빠져 영영 BM25 | `rebuild` 가 같은 커밋이라도 `_embedding_ok` 가 아니면 전체 빌드로 다시 시도. 시험 `test_embedder_recovers_on_same_commit` |
| 2 | 높음 | 임베딩 응답의 차원·유한성·0 벡터를 검증하지 않아 degraded 대신 예외 | `HttpEmbedder._one` 이 깨진 본문(빈 벡터·행마다 다른 차원·NaN/Inf·0 벡터)을 실패로; 배치 간 차원 불일치도 실패. `SearchIndex` 는 깨진 저장 벡터면 dense 를 끄고, 질의 벡터는 차원·유한·0 검사 뒤 아니면 BM25 만. 카탈로그는 깨진 저장분을 만나면 캐시를 비워 다음 빌드가 전부 다시 임베딩 |
| 3 | 높음 | 스냅샷과 색인을 따로 대입해 동시 검색이 두 세대를 섞음 | `_live = (snapshot, indexes)` 하나의 참조로 교체; 검색은 그 참조 하나를 읽는다 |
| 4 | 중간 | 빈 질의·전 점수 0 에서 하이브리드가 이름순 전체를 냄 | 빈 질의는 빈 결과. 0·NaN 질의 벡터는 2 로 BM25 만. "dense 는 언제나 상위 limit 을 낸다"는 설계대로(동의어 구조가 그것) — 문턱은 넣지 않는다 |
| 5 | 중간 | `HC__EMBED_URL` 비면 degraded 가 아니었음(설계와 반대) | 임베더 없음도 `embedding_unavailable` — 운영자가 /readyz 로 설정 누락을 본다. 시험 뒤집음 |
| 6 | 중간 | 캐시 키가 `tree_sha` 뿐 — 같은 내용 다른 이름이면 SHA 가 같아 벡터를 잘못 재사용 | 키를 `(name, tree_sha)` 로; `load_embeddings` 도 그 키, 스냅샷의 `embeddings` 는 `name` 키(한 스냅샷 안 이름 유일) |
| 7 | 중간 | 질의 때 임베더 장애가 /readyz 에 안 보임 | `_ranked` 가 질의 임베딩 성패로 `_embedding_ok` 를 갱신, `status()` 가 그 값으로 `embedding_unavailable` 을 합성. 시험 `test_query_time_embedder_outage_is_visible_in_status` |

내 쪽에서 먼저 잡은 둘(Codex 와 겹침): 임베더 장애 때 저장 벡터를 지우지 않기(`test_embedder_outage_keeps_stored_vectors_and_recovers`), 질의 임베딩 호출의 connect timeout 3 s(죽은 서비스에 검색이 120 s 매달리지 않게).

## 3. 결정 (벤치마크 뒤 제안 — 사용자 확정 뒤 DESIGN §11 행)

1. **문서 쪽**: description 규약(발동 낱말·쓰지 말 상황)을 유지하고, 색인 문서를 `name + description + 발동 낱말(description 안의 따옴표 구절)` 로 넓힌다 — 실측 +0.068 R@1. 합성 질의(Re-Invoke)는 넣지 않는다(레지스트리에 LLM 의존 없음; 넣는다면 write 스킬이 저자 앞에서).
2. **질의 쪽**: kata 조립기는 과제 문장에서 의도를 뽑아 짧은 질의로(Re-Invoke), 도구는 `server`·`tool` 두 필드로(MCP-Zero). 세션의 모델은 이미 그렇게 쓴다. 레지스트리는 바뀌지 않는다.
3. **엔진 — 실측으로 정한 모양(0.8.0 에 통째로, 5-0·5 항)**: **dense + BM25 의 볼록 결합**(α 설정값, 기본 0.85 — holdout 에서 유지됨, 0.7~0.95 평평). dense 는 KURE-v1(MIT, 568M, 문서당 1,024 차원 하나). 어휘는 BM25(낱말 + 한글 2-gram; Kiwi 형태소는 이득 없어 넣지 않음). **임베딩 런타임은 모델이 있는 머신의 GPU 쪽 작은 서비스**(5 항 참조; mini 호스트 MPS 질의 24 ms·색인 6.6 s. 2026-10-19 밤 정정 — 그 전 판의 '프로세스 안 torch CPU' 는 mini Docker VM 이 2 GB 라 성립하지 않았다). TEI arm64 CPU 이미지는 OOM 과 29배 느린 색인으로 탈락. **RRF 는 쓰지 않는다**. 임베딩 모델을 못 올리면 **BM25 단독으로 깎아서** 답한다(가용성 보장이지 품질 보장은 아님 — 동의어 질의 0.64). 리랭커는 넣지 않는다(본전 이하).
   **대안으로 기록해 두는 것 — KURE-v2 late interaction**(154M, Apache-2.0): 단독으로 KURE-v1+BM25 와 같은 품질(R@3 0.981), 식별자 1.00, BM25 가 필요 없어 결합 코드가 사라진다. 대신 CPU 질의 1.5배·색인 4.8배, 저장 10배(문서당 39 KB), MaxSim 계산. 한국어 동의어가 실제 질의에서 더 큰 문제로 드러나거나 BM25 쪽 유지가 부담이 되면 그때 이쪽으로 바꾼다 — 메모리 계산이라 바꾸는 비용은 모듈 하나다.
   **어디서 계산하나 — 메모리에서.** 카탈로그는 수백~수천 항목이고 레지스트리는 이미 색인 행 전체를 메모리에 들고 있다(DESIGN §2.1, DB 단절 때 깎아 답하기 위해). BM25(0.3ms)와 1,024차원 코사인(수천 × 1,024 내적)은 그 메모리 사본 위에서 numpy 로 끝난다 — **pgvector 도 pg_search 도 필요 없다.** Postgres 에는 벡터를 `real[]` 열로 저장해 재기동 때 다시 임베딩하지 않게만 한다. pgvector 는 항목이 수만을 넘을 때의 다음 단계다(그때 가서 HNSW). 이것이 단순함 기준([[feedback-simplicity-over-branching]])에 맞는 모양이다 — 이미지 교체도 확장도 없이 열 하나, 컨테이너 하나(TEI), 설정값 하나.
4. **게이트**: 검색 변경 PR은 벤치마크 숫자를 함께 적는다(DESIGN §11 2026-10-19). 벤치에 서버 모듈 그대로의 엔진(`--app` → `app-hybrid(core.search)`·`app-bm25(core.search)`)을 꽂아 같은 표로 잰다.
5-0. **설계 결정의 기준(2026-10-19 밤, 사용자 정정: "최소 구현 비용은 중요하지 않다, 처음부터 올바른 설계로").** 이 절은 세 번 흔들렸다 — dense 단독(v1 벤치) → dense+BM25 볼록 결합(v2 벤치) → BM25 단독(Codex 단순함 검토). 흔들린 이유는 검토마다 기준을 바꿔 들었기 때문이다(최고 숫자 → 최소 부품). 기준은 하나여야 한다: **측정된 품질이 가장 좋은 모양을 고르고, 그 안에서 제 몫을 못 하는 부품만 뺀다.** 그 기준으로 답은 **dense + BM25 볼록 결합 하나**이고, 단계도 플래그도 없이 0.8.0 에 통째로 들어간다. Codex 2차의 "BM25 만 먼저"는 미룬 결정이지 설계가 아니다 — 받아들이지 않는다. Codex 2차가 맞게 잡아 준 것은 그대로 받는다: 설정값 없음, a/b 두 단계 없음, 관측 최소 셋, 꼬리 문턱은 kata, 전환·롤백 규칙 명시, 제안서 안의 모순 제거.
   채택하지 않은 대안과 이유 — (a) **BM25 단독**(R@3 0.940, 동의어 0.64): 어휘가 못 잡는 바꿔 말하기를 사용자가 겪게 하고 "나중에 dense"는 설계를 미루는 것. (b) **dense 단독**(0.979, R@1 0.923, 식별자 0.979): 결합 대비 R@1 −0.024 — 사람이 첫 번째를 집는 세션에서 100번에 2~3번 더 틀리고, 식별자(이름·명령·API)를 100번에 2번 놓친다. 문헌(DPR 부록 C, Contextual Retrieval)이 말하는 임베딩의 약점 그대로라 제거할 수 없는 부품이다. (c) **KURE-v2 late interaction 단독**(0.981, R@1 0.943, 식별자 1.00, RSS 0.9 GB): 부품은 가장 적지만 CPU 질의 1.5배·색인 4.8배·저장 10배이고 2026년에 나온 단일 공급 모델이다. 품질 차이는 잡음 안이라 **RSS 가 제약이 되면 바꿀 수 있는 대안**으로 둔다.
5-1. **정본 KB(syntopicon `it`)가 같은 결론을 떠받치는 자리** (2026-10-19, kb-query).
   - `[it]` 하이브리드 검색과 리랭킹 — DPR 원전(Karpukhin 2020, Table 2)에서 BM25+DPR 선형 결합은 어휘가 강한 SQuAD·TREC 에서 크게 이기지만 **조밀 쪽이 이미 크게 앞서는 NQ·WQ 에서는 단독 DPR 보다 낮다**. 우리 v1(약한 어휘 + RRF 가 dense 를 끌어내림)과 v2(BM25 + 볼록 결합이 식별자 질의에서 이득)가 그 두 경우다. 원전의 λ=1.1 도 "개발 집합의 검색 정확도에 근거해" 고른 값 — 우리 α 를 holdout 에서 고른 것과 같은 절차. RRF 의 k=60 은 파일럿에서 한 번 고정된 상수다.
   - `[it]` 검색 품질 평가 — "임베딩 변환은 오류 코드·제품명 같은 키워드를 흐릿하게 만든다… 어휘 기반과 결합함으로써 다뤄진다"(huyen2025 6장), DPR 부록 C 의 "드물게 나타나는 두드러진 구절" 실패. 우리 `name`·`jargon` 스타일이 이 자리다.
   - `[it]` 외부 설정 — 설정으로 뺄 것의 목록에 "검색 가중치"는 없고, 저자들의 정정 "게을러서 결정을 설정으로 밀지 마라 — 한쪽으로 시도해 보고 피드백을 받아라"가 α·k·엔진 선택을 설정으로 열지 않는 근거.
   - `[it]` yagni 와 진화적 아키텍처 — 판정 질문 "나중에 리팩터링하기가 지금 넣는 것보다 상당히 더 어려운가". 임베딩 열·캐시 키·dense 자체 모두 다음 판에 더하는 비용이 작다.
   - `[it]` 배포 산출물로서의 모델 — "시작할 때마다 내려받지 말고 캐시하라". dense 를 넣는 판에서는 가중치를 이미지에 넣는 것이 가장 단순한 형태.
   - `[it]` 기록 시스템과 파생 데이터 — 인덱스는 파생, 정본은 git `main`. 재기동 때 다시 만드는 쪽이 구분을 지킨다.
5. **0.8.0 범위 — 하이브리드 검색 하나, 통째로.**
   - **엔진**: dense(KURE-v1, MIT, 1,024차원 하나) + BM25(소문자 낱말 + 한글 글자 2-gram, 라틴·한글 붙은 토큰 분리). 질의마다 두 점수를 min-max 정규화해 0.85·dense + 0.15·BM25 (상수 — holdout 에서 고른 값, 0.7~0.95 평평). 계산은 전부 레지스트리 프로세스 메모리의 색인 사본 위에서 numpy. RRF 없음, 리랭커 없음.
   - **임베딩 런타임 — 2026-10-19 밤 정정: 레지스트리 프로세스 밖, 모델이 있는 머신의 GPU 쪽으로 분리한다.** 사용자 질문 "하나의 큰 이미지가 맞나, 분리가 맞나"에 실측으로 답했다.
     - mini 의 Docker 는 **colima VM(vz, CPU 2, 메모리 2 GB)** 이고 open-webui(617 MB) 등 다른 일도 그 안에 산다. 레지스트리 이미지는 119 MB. 인프로세스 모델(RSS 2.1 GB, 이미지 +~3.4 GB: torch aarch64 휠 454 MB + 가중치 2.3 GB)은 **이 VM 에 들어가지 않는다.** VM 을 키워도(colima 재시작) 2~4 vCPU 리눅스에서 CPU 임베딩이다.
     - 같은 mini 의 **호스트(macOS, Apple M4 GPU)** 에서 KURE-v1 을 직접 돌린 실측: **MPS 질의 p50 23.7 ms · p95 25.8 ms, 720 문서 색인 6.6 s, RSS 2.2 GB**(호스트 16 GB 중). CPU 로도 43 ms / 14.5 s. 즉 GPU 는 호스트에만 있고 메모리도 호스트에 있다.
     - 따라서 **분리가 맞다.** "모델을 컨테이너로 올리지 않지 않나"(사용자)에 대한 답: 리눅스 서버에서는 컨테이너(TEI·vLLM·Ollama 이미지)가 표준이되 가중치는 이미지에 굽지 않고 마운트한다; **Mac 에서는 컨테이너가 Metal 에 닿지 못해 호스트 앱이 표준**(Ollama·LM Studio·MLX). 우리 실측이 그대로다.
     - **mini 에서는 이미 설치되어 돌고 있는 Ollama.app(0.18.0, 호스트, Metal) 을 쓴다** — 우리가 만들 서비스가 없다(사용자 승인 2026-10-19 밤 "그렇게 하라"). 모델은 KURE-v1 의 GGUF 변환본 `hf.co/mykor/KURE-v1-gguf:BF16`(MIT, 1.2 GB; F32 2.3 GB·Q8_0 635 MB 도 있음). 실측: 1024 차원·정규화 벡터, **질의 p50 68 ms, 720 문서 색인 15 s**(네이티브 torch MPS 24 ms·6.6 s 보다 느리나 TEI 194 ms·375 s 와는 급이 다름). GGUF BF16 의 순위 품질은 실행 J(아래)로 fp32 와 대조한다 — 떨어지면 F32 GGUF.
     - 레지스트리 설정값 하나가 생긴다: `HC__EMBED_URL`(외부 서비스 주소 — [it] 외부 설정 목록의 "앱이 쓰는 포트·IP·기계 이름"에 해당하므로 DESIGN §2 규칙 안이다; α 같은 가중치가 아니다)과 그 모델 이름 `HC__EMBED_MODEL`(Ollama 는 요청에 모델 이름이 필요; 이 값이 `embedding_generation` 열의 세대 키가 된다). 비면 BM25 만, 닿지 않으면 degraded `embedding_unavailable` + BM25. mini 에서는 `http://host.docker.internal:11434`(Ollama `/api/embed`; colima 에서 192.168.5.2 로 풀림). mini 의 Ollama 는 `~/Library/LaunchAgents/com.ollama.server.plist`(`/usr/local/bin/ollama serve`)로 떠 있고 colima 컨테이너에서 `http://host.docker.internal:11434/api/version` 이 이미 닿는다(2026-10-19 확인 — 별도 설정 불필요). 인증 없는 서비스이므로 tailnet·LAN 신뢰 경계 안(Nexus·Harbor 와 같음). 리눅스 서버라면 같은 자리에 TEI 컨테이너(`/embed`) — 어댑터는 "문장 목록 → 벡터 목록" 클라이언트 하나에 Ollama/TEI 두 요청 모양을 둔다.
     - 레지스트리 이미지는 그대로 119 MB, compose 서비스 셋 그대로. **새 컨테이너 없음, 새 서비스도 없음(이미 있는 Ollama).** 질의 임베딩 HTTP 왕복은 호스트 로컬이라 1~2 ms.
     - bf16 은 품질 동일(R@3 0.9204 = fp32, top-1 일치 98.6%)이나 CPU 색인이 6.6배 느려(148 s vs 22.6 s) 쓰지 않는다. MPS fp32 가 기준.
     - 대안으로 남기는 것: colima 를 8 GB/4 CPU 로 키우고 인프로세스 — 토폴로지는 단순하지만 CPU 임베딩(미측정)·3.4 GB 이미지·VM 안 메모리 경쟁. GPU 가 호스트에 있는 한 택하지 않는다.
   - **저장**: 마이그레이션 0004 — `skill_index`·`tool_index` 에 `embedding real[]`, `embedding_generation text` 두 열. `replace_index` 는 새 행의 (tree sha, embedding_generation) 이 옛 행에 있으면 벡터를 재사용하고 없는 것만 임베딩한 뒤 한 트랜잭션으로 교체 — 재기동 때 재임베딩 없음, main 이 바뀌면 바뀐 항목만. `embedding_generation` 값에 색인 문서 형식 판을 함께 적는다(`hf.co/mykor/KURE-v1-gguf:BF16/doc1`) — 모델이나 문서 형식이 바뀌면 값이 바뀌어 자연히 전부 다시 임베딩되고, 한 세대만 존재한다.
   - **ready·degraded**: 지금 규칙 그대로 — 인덱스(벡터 포함)가 있으면 ready. 임베딩 서비스에 닿지 못하면(`HC__EMBED_URL` 비었거나 오류) `degraded` 사유 `embedding_unavailable` 하나를 더하고 BM25 만으로 답한다(DB 단절 때 메모리로 깎는 것과 같은 모양). "BM25 먼저 떠서 나중에 dense" 같은 시간 분기는 없다.
   - **전환 규칙**: 배포 순간부터 모든 검색은 메모리 하이브리드가 정본. `PgFactStore.search`(tsvector·trgm·ILIKE)와 DB 단절 때의 부분 일치 폴백은 읽기 경로에서 뺀다. 생성 열·GIN 인덱스는 이번 판에 그대로 두고 다음 스키마 정리 판에서 지운다. 롤백은 이전 이미지(0004 는 열 추가뿐이라 이전 이미지와 공존).
   - **설정값 하나** `HC__EMBED_URL`(외부 서비스 주소 — 임베딩 런타임 항 참조; 가중치 α 같은 튜닝 값은 설정으로 열지 않는다). **응답 계약 불변**(`search_skills`/`search_tools` 모양, `limit` 기본 10·최대 20).
   - **관측 최소 셋**: 검색 스팬에 `query`(있음)·`result_count`(있음)·**후보 이름 목록**(추가). 선택은 후속 `get_skill`/`get_tool` 스팬과 같은 trace 로 사후 결합, 재질의는 같은 trace 의 후속 검색으로 유도. 점수·selected·result_0 은 넣지 않는다.
   - **검색 모듈 `search.py`** 는 앱 안의 순수 함수(토크나이저·BM25·코사인·결합)라 Postgres·모델 없이 시험되고, 벤치에 그대로 꽂아(`--app`, `app-hybrid(core.search)`) 같은 표로 회귀를 잡는다 — 실행 K: R@3 0.981(기대 0.982 와 같은 자리).
6. **k — 레지스트리는 모르고, kata 는 당분간 고정 5.** 꼬리 문턱·재요청은 넣지 않는다(k 3→5 synonym 0.89→0.94 — 잘릴 것이 바로 동의어 후보). 확정은 kata Harbor 과제(k 별 모델 선택 정확도·토큰)와 Langfuse 실제 질의.
7. **재튜닝 경로**: Langfuse 검색 스팬(후보 이름)과 후속 get 스팬의 trace 결합 → 시간순 train/valid/test → α·k 의 주기적 offline replay. 합성 벤치는 회귀 방지와 상대 비교용.

## 출처

- ToolRet: https://aclanthology.org/2025.findings-acl.1258/
- Tool-REX: https://proceedings.iclr.cc/paper_files/paper/2026/file/e54a9889f1048526365ed8fb56c8c8cd-Paper-Conference.pdf
- Re-Invoke: https://arxiv.org/abs/2408.01875 · https://research.google/blog/re-invoke-tool-invocation-rewriting-for-zero-shot-tool-retrieval/
- Toollery: https://arxiv.org/abs/2609.22218
- MCP-Zero: https://arxiv.org/abs/2506.01056
- Anthropic Tool Search Tool: https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool · https://anthropic.com/engineering/advanced-tool-use
- KURE: https://github.com/nlpai-lab/KURE
- Qwen3-Embedding: https://qwenlm.github.io/blog/qwen3-embedding/ · https://arxiv.org/abs/2506.05176
- jina-embeddings-v3/v4: https://huggingface.co/jinaai/jina-embeddings-v3 · https://huggingface.co/jinaai/jina-embeddings-v4
- 하이브리드 관행: https://indexical.dev/knowledge/reciprocal_rank_fusion_vs_reranker_which_should_you_use_for_hybrid_search_retrieval.php
- 사례(1b): Anthropic Tool Search https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool · 쿡북 https://platform.claude.com/cookbook/tool-use-tool-search-with-embeddings · OpenAI tool search https://developers.openai.com/api/docs/guides/tools-tool-search · Codex skills https://developers.openai.com/codex/skills.md · VS Code virtual tools https://code.visualstudio.com/updates/v1_103 · Cursor 40 https://forum.cursor.com/t/mcp-server-40-tool-limit-in-cursor-is-this-frustrating-your-workflow/81627 · langgraph-bigtool https://github.com/langchain-ai/langgraph-bigtool · hermes-agent #130044 https://github.com/NousResearch/hermes-agent/issues/130044 · RAG-MCP https://arxiv.org/abs/2505.03275 · ScaleMCP https://arxiv.org/abs/2505.06416 · Toolshed https://arxiv.org/abs/2410.14594 · Contextual Retrieval https://www.anthropic.com/news/contextual-retrieval · Bruch 외 https://arxiv.org/abs/2210.11934 · 한국어 BM25 토크나이저 https://velog.io/@autorag (AutoRAG 벤치) · tianpan https://tianpan.co/blog/2026/04/12/hybrid-search-production-bm25-dense-embeddings
- Jev: https://docs.typesafe.ai/models · https://docs.typesafe.ai/concepts/system-one · https://docs.typesafe.ai/cookbooks/rerank_typesafe · https://huggingface.co/blog/hotchpotch/introducing-jev-reranker · https://github.com/hotchpotch/jev-reranker · https://www.elastic.co/search-labs/blog/ecommerce-search-reranking-llm-alternative-jev · https://parallel.ai/blog/testing-jev · https://www.firecrawl.dev/blog/what-is-jev · https://arxiv.org/abs/2609.30216 · https://huggingface.co/hotchpotch/bekko-system-one-v0-68m · https://huggingface.co/openjev/openjev
