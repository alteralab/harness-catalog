import { DocsLayout } from 'fumadocs-ui/layouts/docs';
import { source } from '@/lib/source';
import { baseOptions } from '@/lib/layout.shared';
import { basePath, repoBlob } from '@/lib/shared';

// 사이드바에 두는 바깥 자리들. 사이트의 쪽이 아니므로 목차와 섞지 않는다.
const elsewhere = [
  { href: `${basePath}/llms.txt`, label: 'llms.txt — 에이전트용 목차' },
  { href: `${repoBlob}/DESIGN.md`, label: 'DESIGN.md — 설계와 결정' },
  { href: `${repoBlob}/PLAN.md`, label: 'PLAN.md · plans/ — 실행 계획' },
];

export default function Layout({ children }: LayoutProps<'/docs'>) {
  return (
    <DocsLayout
      tree={source.getPageTree()}
      {...baseOptions()}
      // 헤더의 링크는 문서 쪽에서 사이드바로 들어가 목차와 겹친다(실측) — 여기서는 목차만 둔다.
      links={[]}
      sidebar={{
        banner: <p className="hc-sidebar-label px-2 pt-1 pb-2">문서</p>,
        footer: (
          <div className="border-t border-fd-border px-2 pt-3 text-[0.78rem] text-fd-muted-foreground">
            <p className="hc-label mb-1.5">사이트 밖</p>
            <ul className="space-y-1">
              {elsewhere.map((item) => (
                <li key={item.href}>
                  <a className="hover:text-fd-primary" href={item.href}>
                    {item.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ),
      }}
    >
      {children}
    </DocsLayout>
  );
}
