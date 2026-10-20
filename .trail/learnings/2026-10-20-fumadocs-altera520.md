---
title: "문서 사이트: 과제 단위 배치와 fumadocs 의 함정들"
author: Altera520
date: 2026-10-20
branch: main
cost: { minutes: 274, tokens: 3950752 }
touches:
  - README.md
  - docs-site/app/docs/page.tsx
  - docs-site/scripts/after-build.mjs
  - docs/authoring.md
  - docs/authoring/checks.md
  - docs/authoring/evals.md
  - docs/authoring/index.md
  - docs/authoring/lifecycle.md
  - docs/authoring/meta.json
  - docs/authoring/skill.md
---

## Decided
- `docs/` 는 **과제 하나에 쪽 하나**다. 독자별 긴 쪽이 아니라 묶음(폴더) + 과제 쪽.
  묶음마다 `meta.json` 을 두고 `index.md` 는 **`pages` 에 적지 않는다** — fumadocs 가
  비루트 폴더의 `index` 를 자동으로 그 묶음의 첫 쪽으로 잡는다(`pagesIndex` 기본값).
- 끝에 몰린 `## 문제 해결` 표는 행마다 그 과제의 쪽으로 나눈다. 막히는 자리에 고치는 법이 있어야 한다.
- `docs/configuration.md` 는 **루트에서 옮기지 않는다.** `config_docs` 가
  `out_dir / "configuration.md"` 로 경로를 박고 있고 `tests/cli/test_init.py` 가 그 경로를 본다.
- 프런트매터 `description` 은 **명사형 나열**이 이 저장소의 관례다(quickstart·configuration 이 본보기).
  평문이라 마크다운이 그려지지 않으니 백틱을 넣지 않는다.

## Tried and ruled out
- `/docs` 목차를 `source.getPages()` 로 평평하게 늘어놓기 — 쪽이 스물여섯이 되면 묶음이 지워진다.
  `source.pageTree.children` 을 걷는다.
- `after-build.mjs` 가 점검할 쪽을 손으로 적은 배열로 두기 — 쪽이 늘면 조용히 뒤처진다.
  콘텐츠 루트(`../docs`)를 재귀 스캔한다.
- 랜딩에 README 의 전체 구성도(mermaid 열다섯 칸)를 끌어오기 — 글자가 6px 로 줄어 못 읽는다.

## Watch out
- **YAML 평문 스칼라는 백틱(그리고 `@ % & * | > #` 등)으로 시작할 수 없다.** 프런트매터의
  `description: \`hc check\`가 …` 가 빌드를 멈춘다. 따옴표로 감싸거나 백틱을 뗀다.
- **깨진 링크를 빌드가 멈추는 것은 "쪽도 파일도 아닐 때"뿐이다.** `../operations/index.md` 처럼
  파일이 실제로 있으면, 쪽으로 안 풀려도 GitHub blob 링크로 **조용히** 떨어진다. 산출물에서
  `href="/harness-catalog/docs/…"` 로 났는지 확인할 것.
- **`white-space: nowrap` 은 격자 칸의 min-content 를 밀어 올린다.** 카드 안의 명령 한 줄 때문에
  390px 에서 칸이 619px 로 부풀고 부모가 잘라냈다. 격자·플렉스 항목에 `min-w-0` 을 같이 준다.
- **데스크톱 헤드리스 크롬은 viewport 메타를 무시한다.** `--window-size=390` 로 찍은 그림이
  넘치는 것처럼 보이는 것은 착시다. CDP `Emulation.setDeviceMetricsOverride({mobile: true})` 로 잰다.
