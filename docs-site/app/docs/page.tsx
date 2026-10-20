import Link from 'next/link';
import type { Metadata } from 'next';
import { ArrowRight } from 'lucide-react';
import { source } from '@/lib/source';
import { appName } from '@/lib/shared';

export const metadata: Metadata = {
  title: '문서',
  description: `${appName} 문서의 목차 — 과제 하나에 쪽 하나.`,
};

/**
 * `/docs` 의 표제 쪽. 콘텐츠 쪽이 아니라 목차다 — 왼쪽 네비게이션과 같은 것을 펼쳐 보여 준다.
 * (옛 사이트는 여기에 README 를 통째로 끌어와 목차가 둘로 겹쳐 있었다.)
 *
 * 쪽 목록을 평평하게 늘어놓지 않고 **page tree 를 그대로 걷는다** — docs/ 가 과제 단위로 갈리면서
 * 묶음이 넷 생겼고, 평평한 목록은 그 묶음을 지워 스물여섯 줄이 된다(2026-10-20).
 */
type Row = { url: string; title: string; description?: string };

function rowsOf(nodes: readonly { type: string; url?: string; name?: unknown; description?: unknown }[]): Row[] {
  // 트리의 이름·설명은 ReactNode 타입이지만 이 저장소의 meta.json·프런트매터는 전부 문자열이다.
  return nodes.flatMap((node) =>
    node.type === 'page' && node.url
      ? [{ url: node.url, title: String(node.name ?? ''), description: node.description ? String(node.description) : undefined }]
      : [],
  );
}

function RowList({ rows }: { rows: Row[] }) {
  return (
    <ul className="divide-y divide-fd-border border-y border-fd-border">
      {rows.map((row) => (
        <li key={row.url}>
          <Link
            href={row.url}
            className="group flex flex-wrap items-baseline gap-x-4 gap-y-1 py-3.5 transition-colors hover:text-fd-primary"
          >
            <span className="text-[0.95rem] font-medium">{row.title}</span>
            <span className="text-[0.86rem] leading-[1.7] text-fd-muted-foreground">
              {row.description}
            </span>
            <ArrowRight className="ms-auto size-4 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" />
          </Link>
        </li>
      ))}
    </ul>
  );
}

export default function DocsIndex() {
  // 묶음에 속하지 않은 쪽(빠른 시작·설정값)과 묶음 넷을 네비게이션 순서 그대로 가른다.
  const children = source.pageTree.children as readonly {
    type: string;
    url?: string;
    name?: unknown;
    description?: unknown;
    index?: { url: string };
    children?: readonly { type: string; url?: string; name?: unknown; description?: unknown }[];
  }[];

  // 묶음에 속한 쪽은 어느 독자의 것인지 묶음이 말해 준다 — 쪽마다 audience 를 되풀이하지 않는다.
  const audienceOf = new Map(source.getPages().map((p) => [p.url, p.data.audience]));

  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-12 md:px-10">
      <p className="hc-label">목차</p>
      <h1 className="mt-3 text-[1.7rem] font-semibold tracking-[-0.02em]">문서</h1>
      <p className="mt-3 text-[0.95rem] leading-[1.8] text-fd-muted-foreground">
        쪽 하나가 과제 하나다. 묶음 넷은 독자별이고, 빠른 시작과 설정값은 어느 독자든 보는 쪽이라
        바깥에 있다.
      </p>

      <div className="mt-10 flex flex-col gap-10">
        {children.map((node) => {
          if (node.type === 'page' && node.url) {
            return (
              <section key={node.url}>
                <p className="hc-label mb-3">{audienceOf.get(node.url) ?? '문서'}</p>
                <RowList rows={rowsOf([node])} />
              </section>
            );
          }
          if (node.type !== 'folder') return null;

          const title = String(node.name ?? '');
          const indexUrl = node.index?.url;
          return (
            <section key={title}>
              <p className="hc-label mb-3">
                {(indexUrl && audienceOf.get(indexUrl)) || '문서'}
              </p>
              <h2 className="text-[1.15rem] font-semibold tracking-[-0.015em]">
                {indexUrl ? (
                  <Link href={indexUrl} className="transition-colors hover:text-fd-primary">
                    {title}
                  </Link>
                ) : (
                  title
                )}
              </h2>
              {node.description ? (
                <p className="mt-1.5 mb-4 text-[0.88rem] leading-[1.75] text-fd-muted-foreground">
                  {String(node.description)}
                </p>
              ) : (
                <div className="mb-4" />
              )}
              <RowList rows={rowsOf(node.children ?? [])} />
            </section>
          );
        })}
      </div>
    </div>
  );
}
