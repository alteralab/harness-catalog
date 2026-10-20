---
title: 문서 사이트 짓기
description: 미리보기·빌드·빌드 뒤 점검, 하위 경로와 검색, 서빙.
audience: 개발자
---

# 문서 사이트 짓기

`docs/`의 마크다운을 사이트로 미리보고 짓는 쪽입니다.

```sh
make docs          # 미리보기 — http://127.0.0.1:3000/harness-catalog/
make docs-build    # docs-site/out 에 짓는다. llms.txt·llms-full.txt 가 여기서 나온다
make docs-serve    # 지은 것을 운영과 같은 하위 경로로 — http://127.0.0.1:8810/harness-catalog/
```

소스는 `docs/`의 마크다운 그대로입니다. 사이트용 사본을 따로 두지 않고 사이트 앱(`docs-site/`)이 `docs/`를 콘텐츠 루트로 읽습니다(`docs-site/source.config.ts`의 `dir: '../docs'`). 쪽마다 프런트매터 셋(`title`·`description`·`audience`)이 붙고, 왼쪽 네비게이션의 순서는 `docs/meta.json`입니다. 쪽 제목은 본문의 `#` 그대로라서 같은 파일이 GitHub에서도 읽힙니다.

**README·DESIGN·docs/\*.md를 사이트 때문에 고치지 않습니다** — 저장소에서 읽는 사람에게 맞는 링크를 그대로 두고, 사이트에서 다른 자리로 가야 하는 링크는 `docs-site/lib/doc-link.tsx` 한 곳에서 돌립니다: 같은 `docs/` 안의 쪽(이 쪽에서라면 `../operations/index.md`)은 사이트 URL로, `docs/` 밖의 저장소 파일(`../../.github/runner.env.example`)은 GitHub blob으로. 경로는 **그 글이 놓인 자리 기준**입니다 — 쪽을 다른 깊이로 옮기면 함께 고칩니다. 어느 쪽도 아니면 **빌드가 멈춥니다**(옛 mkdocs `strict: true`가 하던 일).

사이트 앱은 Fumadocs + Next의 정적 내보내기(`output: 'export'`)이고 판은 `docs-site/package-lock.json`에 고정됩니다. 파이썬 의존성은 없습니다.

**하위 경로.** 운영의 서빙 자리가 `/harness-catalog/` 아래라서 `next.config.mjs`의 `basePath`가 그 값이고, `trailingSlash: true`로 쪽마다 `<경로>/index.html`을 냅니다(정적 호스팅이 디렉토리 요청에 돌려주는 모양). 루트로 서빙해 보려면 `DOCS_BASE_PATH=`를 비워 둡니다. basePath를 모르는 자리가 둘 있어 직접 붙입니다 — 검색 색인 fetch(`docs-site/components/search.tsx`)와 자체 호스팅 폰트 CSS.

**빌드 뒤 점검.** `docs-site/scripts/after-build.mjs`가 매 빌드 끝에 돌아 쪽마다 `index.html`이 났는지, `basePath` 밖(`/_next/…`)을 가리키는 자산이 없는지, `llms.txt`·`llms-full.txt`가 비어 있지 않은지, 검색 색인이 JSON으로 파싱되는지를 봅니다. 하나라도 어긋나면 실패하므로 CI가 같은 명령으로 막습니다. 제목 id는 유니코드를 그대로 두어 한글이 앵커가 됩니다(`#빠른-시작`).

**`llms.txt`.** `docs-site/app/llms.txt`와 `app/llms-full.txt` 라우트가 목차와 전 쪽 본문을 냅니다. 링크의 절대 주소는 `docs-site/lib/shared.ts`의 `siteUrl`에서 옵니다 — 공개 도메인으로 옮기면 그 한 줄을 바꿉니다. 쪽마다의 마크다운 원문은 `/llms.mdx/docs/<쪽>/content.md`입니다.

**검색.** 서버가 없으므로 색인 전체(`out/api/search`)를 브라우저가 받아 찾습니다. 엔진(zbsearch)의 지원 언어에 한국어가 없어서 `language`를 `multilingual`로 둡니다 — 템플릿 기본값 `english`는 영어 어간 추출기·불용어를 한국어 토큰에 걸어 적중을 떨어뜨립니다(실측: `레지스트리` 39건 → 53건). 조사 변화형은 질의 쪽 `tolerance: 1`이 메웁니다(실측: `레지스트리가` 6건 → 53건, `레지스트리를` 1건 → 53건).

**mermaid.** ` ```mermaid ` 울타리는 `docs-site/lib/remark-mermaid.ts`가 `<Mermaid>`로 바꾸고 `components/mermaid.tsx`가 브라우저에서 그립니다(`rehype-mermaid`는 빌드에 headless 브라우저를 끌어옵니다). 테마 전환을 지켜보다 다시 그립니다.

**테마.** 색·서체·폭은 `docs-site/app/global.css`의 토큰 한 벌입니다(`--hc-*` → `--color-fd-*`). 본문 서체 Pretendard Variable은 `scripts/vendor-fonts.mjs`가 고정된 npm 판에서 `public/fonts/`로 베껴 자체 호스팅하고(유니코드 구간별 92조각이라 브라우저가 쓰는 것만 받습니다), 코드 서체 JetBrains Mono는 `next/font`가 빌드 때 받아 자체 호스팅합니다.

**서빙 — 별도 파이프라인, 정적 호스팅.** 문서는 앱 배포(compose·`deploy.sh`·이미지)와 **묶지 않습니다**. 사례 전부가 그렇습니다(2026-10-20 저장소 확인: Polaris·MkDocs Material 은 GitHub Pages, Airflow 는 ASF 퍼블리시, DataHub·Langfuse 는 Vercel, Dex 는 Netlify). 이 저장소는 `.github/workflows/docs.yml` 하나가 맡습니다 — PR 에서는 `docs/`·`docs-site/`·README 가 바뀔 때 빌드와 점검만, `main` 에서는 **NAS 의 MinIO 버킷(`harness-catalog-docs`)으로 거울처럼 올립니다**(`scripts/upload_docs.py`: 바뀐 것만 올리고, 지워진 쪽수는 버킷에서도 지웁니다). 버킷 앞에는 nginx 가 서서 S3 의 "웹사이트 엔드포인트"(끝 슬래시 → `index.html`, 404 문서)를 대신합니다 — 그쪽 스택의 정본은 `portainer` 저장소의 `stacks/minio/` 입니다. 주소는 `docs-site/lib/shared.ts` 의 `siteUrl`(`https://ds923plus.tail2f9fe3.ts.net:9810/harness-catalog/`, tailnet 안에서만)이고 `llms.txt` 의 절대 링크도 거기서 옵니다. 업로드는 tailnet 안에서만 되므로 publish 잡은 self-hosted 러너에서 돌고, 주소·버킷은 저장소 변수(`DOCS_MINIO_ENDPOINT`·`DOCS_MINIO_BUCKET`), 자격은 시크릿(`MINIO_ACCESS_KEY`·`MINIO_SECRET_KEY`)인데 **root 가 아니라 전용 사용자**입니다 — `harness-catalog-ci` 에 정책 `harness-catalog-docs-rw`(그 버킷 하나의 목록·읽기·쓰기·삭제)만 붙어 있어 다른 버킷은 보이지도 않습니다(2026-10-20 실측). 만드는 절차는 portainer 저장소의 `stacks/minio/README.md`. **Content-Type 을 반드시 싣습니다** — 비워 두면 MinIO 가 그대로 돌려주고 브라우저가 `nosniff` 때문에 HTML 을 렌더하지 않습니다(2026-10-20 실측).
