import { source } from '@/lib/source';
import {
  DocsBody,
  DocsPage,
  MarkdownCopyButton,
  ViewOptionsPopover,
} from 'fumadocs-ui/layouts/docs/page';
import { notFound } from 'next/navigation';
import { getMDXComponents } from '@/components/mdx';
import type { Metadata } from 'next';
import { createDocLink } from '@/lib/doc-link';
import { getPageMarkdownUrl, repoBlob } from '@/lib/shared';

export default async function Page(props: PageProps<'/docs/[...slug]'>) {
  const params = await props.params;
  const page = source.getPage(params.slug);
  if (!page) notFound();

  const MDX = page.data.body;
  const markdownUrl = getPageMarkdownUrl(page).url;

  return (
    // 제목은 본문의 h1 이다 — docs/*.md 는 GitHub 에서도 읽혀야 해서 h1 을 그대로 두고,
    // 프런트매터의 title 은 네비게이션·검색·메타데이터 쪽에서만 쓴다(제목이 두 번 나오지 않는다).
    <DocsPage toc={page.data.toc.filter((item) => item.depth > 1)} full={page.data.full}>
      <div className="flex items-center justify-between gap-3 border-b border-fd-border pb-3">
        <p className="hc-label">{page.data.audience ?? '문서'}</p>
        <div className="flex flex-row items-center gap-2">
          <MarkdownCopyButton markdownUrl={markdownUrl} />
          <ViewOptionsPopover markdownUrl={markdownUrl} githubUrl={`${repoBlob}/docs/${page.path}`} />
        </div>
      </div>
      <DocsBody>
        <MDX components={getMDXComponents({ a: createDocLink(source, page) })} />
      </DocsBody>
    </DocsPage>
  );
}

export function generateStaticParams() {
  return source.generateParams();
}

export async function generateMetadata(props: PageProps<'/docs/[...slug]'>): Promise<Metadata> {
  const params = await props.params;
  const page = source.getPage(params.slug);
  if (!page) notFound();

  return { title: page.data.title, description: page.data.description };
}
