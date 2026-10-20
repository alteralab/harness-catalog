import { defineConfig, defineDocs } from 'fumadocs-mdx/config';
import { pageSchema } from 'fumadocs-core/source/schema';
import { z } from 'zod';
import { remarkMermaid } from './lib/remark-mermaid';

// 콘텐츠 루트는 저장소의 docs/ 그대로다 — 사이트용으로 복사하거나 옮기지 않는다.
// 그래서 같은 파일이 GitHub 에서도 읽히고, 생성 경로(`hc config docs` → docs/configuration.md)도 그대로다.
export const docs = defineDocs({
  dir: '../docs',
  docs: {
    // `audience` 는 이 저장소의 문서가 독자별로 갈리기 때문에 둔다(README 의 "누구에게" 칸과 같은 것).
    schema: pageSchema.extend({ audience: z.string().optional() }),
    postprocess: {
      // llms.txt·llms-full.txt 가 쓰는 본문. 켜지 않으면 getText('processed') 가 비어 나온다.
      includeProcessedMarkdown: true,
    },
  },
});

export default defineConfig({
  mdxOptions: {
    // ```mermaid 울타리를 <Mermaid> 로 바꾼다 — rehype-mermaid 는 빌드에 브라우저(playwright)를 끌어온다.
    remarkPlugins: (plugins) => [remarkMermaid, ...plugins],
    rehypeCodeOptions: {
      // 밝은·어두운 테마 둘을 한 번에 심고 CSS 가 고른다(fumadocs 의 shiki 이중 테마).
      themes: { light: 'github-light', dark: 'github-dark-dimmed' },
    },
  },
});
