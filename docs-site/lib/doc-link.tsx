import { existsSync } from 'node:fs';
import path from 'node:path';
import type { ComponentProps } from 'react';
import defaultMdxComponents from 'fumadocs-ui/mdx';
import type { InferPageType } from 'fumadocs-core/source';
import type { source as docsSource } from './source';
import { repoBlob } from './shared';

type DocsSource = typeof docsSource;
type DocsPage = InferPageType<DocsSource>;

/**
 * docs/*.md 의 상대 링크를 사이트의 자리로 돌린다 — tools/mkdocs_hooks.py 가 맡던 구실.
 *
 * 원본 마크다운은 GitHub 에서도 읽히는 글이라 `operations.md`·`../.github/runner.env.example` 처럼
 * **저장소에서 맞는** 상대 경로를 쓴다. 사이트에서는 그 둘이 서로 다른 자리로 가야 한다:
 *
 *   · 같은 docs/ 안의 쪽  → 사이트의 쪽 URL (`/docs/operations`)
 *   · docs/ 밖의 저장소 파일 → GitHub blob
 *
 * fumadocs 의 `createRelativeLink` 는 `./`·`../` 로 시작하는 것만 본다(실측) — 이 저장소의 글은
 * 맨 이름(`operations.md`)을 쓰므로 여기서 `./` 를 붙여 준다.
 *
 * 깨진 링크는 빌드를 멈춘다(mkdocs 의 `strict: true` 가 하던 일): 가리키는 쪽도 파일도 없으면 던진다.
 */
export function createDocLink(source: DocsSource, page: DocsPage) {
  const Link = defaultMdxComponents.a;
  const repoRoot = path.resolve(process.cwd(), '..');

  function resolve(href: string): string {
    if (/^(?:[a-z]+:|\/\/|#|\/)/i.test(href)) return href;

    const [target, hash] = href.split('#');
    const relative = target.startsWith('./') || target.startsWith('../') ? target : `./${target}`;
    const resolved = source.resolveHref(hash ? `${relative}#${hash}` : relative, page);
    if (resolved !== relative && resolved !== href) return resolved;

    // 쪽이 아니다 — 저장소의 파일로 보낸다. docs/ 기준의 상대 경로를 저장소 기준으로 편다.
    const repoPath = path.posix.normalize(path.posix.join('docs', path.posix.dirname(page.path), target));
    if (!existsSync(path.join(repoRoot, repoPath))) {
      throw new Error(
        `깨진 링크: docs/${page.path} 의 "${href}" — 사이트의 쪽도 저장소의 파일도 아니다`,
      );
    }
    return `${repoBlob}/${repoPath}${hash ? `#${hash}` : ''}`;
  }

  return function DocLink({ href, ...props }: ComponentProps<'a'>) {
    return <Link href={href ? resolve(href) : href} {...props} />;
  };
}
