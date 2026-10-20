import { llms, loader } from 'fumadocs-core/source';
import { docs } from '@/.source/server';
import { absoluteUrl, docsRoute } from './shared';

// 콘텐츠는 저장소의 docs/ (source.config.ts 의 `dir: '../docs'`).
export const source = loader({
  baseUrl: docsRoute,
  source: docs.toFumadocsSource(),
});

// 쪽마다 주소를 머리에 달고 본문은 손대지 않는다 — 본문의 h1 이 이미 제목이라 제목을 또 붙이지 않는다.
export const docsLlms = llms(source, {
  renderPage: async (page) => `---
url: ${absoluteUrl(page.url)}
---

${await page.data.getText('processed')}`,
});

/** llms.txt 의 목차는 사이트 안의 경로로 나온다 — 바깥에서 읽는 파일이므로 절대 URL 로 돌린다. */
export function absolutizeLinks(markdown: string): string {
  return markdown.replace(/\]\(\/(?=[^)])([^)]*)\)/g, (_, path: string) => `](${absoluteUrl(path)})`);
}
