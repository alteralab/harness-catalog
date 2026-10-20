import Link from 'next/link';
import type { Metadata } from 'next';
import { ArrowRight } from 'lucide-react';
import { source } from '@/lib/source';
import { appName } from '@/lib/shared';

export const metadata: Metadata = {
  title: '문서',
  description: `${appName} 문서의 목차 — 독자별로 갈린 쪽 여섯.`,
};

/**
 * `/docs` 의 표제 쪽. 콘텐츠 쪽이 아니라 목차다 — 왼쪽 네비게이션과 같은 것을 펼쳐 보여 준다.
 * (옛 사이트는 여기에 README 를 통째로 끌어와 목차가 둘로 겹쳐 있었다.)
 */
export default function DocsIndex() {
  const pages = source.getPages();
  const order = source.pageTree.children
    .flatMap((node) => (node.type === 'page' ? [node.url] : []))
    .filter(Boolean);
  const sorted = [...pages].sort((a, b) => {
    const ai = order.indexOf(a.url);
    const bi = order.indexOf(b.url);
    return (ai < 0 ? pages.length : ai) - (bi < 0 ? pages.length : bi);
  });

  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-12 md:px-10">
      <p className="hc-label">목차</p>
      <h1 className="mt-3 text-[1.7rem] font-semibold tracking-[-0.02em]">문서</h1>
      <p className="mt-3 text-[0.95rem] leading-[1.8] text-fd-muted-foreground">
        쪽마다 독자가 하나다. 처음 보는 사람은 빠른 시작, 팀원은 찾아 쓰기, 저자는 스킬 작성, 운영자는
        설치와 설정값이다.
      </p>

      <ul className="mt-9 divide-y divide-fd-border border-y border-fd-border">
        {sorted.map((page) => (
          <li key={page.url}>
            <Link
              href={page.url}
              className="group flex flex-col gap-1.5 py-5 transition-colors hover:text-fd-primary"
            >
              <div className="flex items-center gap-3">
                <span className="hc-label">{page.data.audience ?? '문서'}</span>
                <span className="h-px flex-1 bg-fd-border" />
                <ArrowRight className="size-4 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" />
              </div>
              <span className="text-[1.02rem] font-semibold tracking-[-0.01em]">
                {page.data.title}
              </span>
              <span className="text-[0.88rem] leading-[1.75] text-fd-muted-foreground">
                {page.data.description}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
