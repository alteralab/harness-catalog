import { createGetUrl } from 'fumadocs-core/source';

export const appName = 'harness-catalog';
export const appTagline =
  '팀의 에이전트 스킬을 git 저장소에 두고, 각자의 하네스에서 MCP 로 찾아 쓰게 하는 스킬·툴 카탈로그.';

/** 운영 서빙 자리. mkdocs 의 `site_url` 이 맡던 구실. */
export const siteUrl = 'https://ds923plus.tail2f9fe3.ts.net:9810/harness-catalog/';

/** next.config.mjs 의 basePath. 클라이언트가 색인·폰트를 절대 경로로 받을 때 쓴다. */
export const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? '';

/**
 * 사이트 안의 경로(`/docs/quickstart`)를 바깥에서 쓸 수 있는 절대 URL 로 만든다.
 * llms.txt·llms-full.txt 는 에이전트가 사이트 밖에서 읽는 파일이라 상대 경로면 못 따라온다 —
 * basePath 도 빠져 있다. 끝의 `/` 는 trailingSlash 설정과 맞춘다(정적 호스팅이 디렉토리로 받는다).
 */
export function absoluteUrl(routePath: string): string {
  const clean = routePath.replace(/^\/+/, '').replace(/\/+$/, '');
  return clean ? `${siteUrl}${clean}/` : siteUrl;
}

/**
 * 색인 질의 옵션. `tolerance` 는 편집 거리 허용치다 — 한국어 조사 변화형(`레지스트리가`↔`레지스트리를`)이
 * 색인에 없는 토큰이 되는 것을 이것이 메운다(엔진 zbsearch 에 한국어 형태소 분석기가 없다).
 * 수치 근거: scripts/search-probe.mjs 의 전후 비교.
 */
export const staticSearchParams = { tolerance: 1 } as const;

export const docsRoute = '/docs';
export const docsContentRoute = '/llms.mdx/docs';

export const gitConfig = {
  user: 'alteralab',
  repo: 'harness-catalog',
  branch: 'main',
};

export const repoUrl = `https://github.com/${gitConfig.user}/${gitConfig.repo}`;
export const repoBlob = `${repoUrl}/blob/${gitConfig.branch}`;

const getContentUrl = createGetUrl(docsContentRoute);

export function getPageMarkdownUrl(page: { slugs: string[]; locale?: string }) {
  const segments = [...page.slugs, 'content.md'];

  return { segments, url: getContentUrl(segments, page.locale) };
}
