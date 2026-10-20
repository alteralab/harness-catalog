import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { Mermaid } from '@/components/mermaid';
import { architectureDiagram, repoVersion } from '@/lib/repo-facts';
import { appTagline, basePath, docsRoute, repoBlob, repoUrl, siteUrl } from '@/lib/shared';

/** 네 갈래 진입 — 독자가 자기 자리를 먼저 고른다. 순서·글은 docs/ 의 쪽들과 짝이다. */
const entries = [
  {
    index: '01',
    audience: '처음',
    title: '먼저 돌려 보기',
    body: 'Docker 하나로 레지스트리·Dex·PostgreSQL·심은 카탈로그가 내 머신에 뜬다. 편집할 파일도 환경 변수도 없다.',
    hint: 'docker compose … up -d --build --wait',
    href: `${docsRoute}/quickstart`,
  },
  {
    index: '02',
    audience: '팀원',
    title: '하네스에서 쓰기',
    body: '하네스에 레지스트리를 등록하고 LDAP 계정으로 한 번 로그인한다. 그 뒤로는 "캡션 가져와"로 스킬을 찾는다.',
    hint: 'claude mcp add --transport http …',
    href: `${docsRoute}/using`,
  },
  {
    index: '03',
    audience: '저자',
    title: '스킬 올리기',
    body: '스킬 하나는 디렉토리 하나다. 브랜치를 따고 검사를 돌리고 PR 을 연다. 병합한 사람이 그 판을 인증한 사람이다.',
    hint: 'hc check . --rev HEAD',
    href: `${docsRoute}/authoring`,
  },
  {
    index: '04',
    audience: '운영자',
    title: '레지스트리 띄우기',
    body: '프록시·Dex·LDAP·배포 키를 세우고 compose 로 올린다. 설정 표면 전부는 설정값 쪽에 층별로 있다.',
    hint: 'curl -fsS http://127.0.0.1:8000/readyz',
    href: `${docsRoute}/operations`,
  },
];

/** 사이트에 쪽으로 두지 않는 것들 — 참조와 원장. */
const ledger = [
  { key: 'configuration', label: '설정값 참조', note: '설정 표면 전부, 층별로', href: `${docsRoute}/configuration` },
  { key: 'development', label: '개발 환경', note: '배치·시험·게이트·릴리스', href: `${docsRoute}/development` },
  { key: 'DESIGN.md', label: '설계와 결정의 근거', note: '저장소의 정본', href: `${repoBlob}/DESIGN.md`, external: true },
  { key: 'llms.txt', label: '에이전트용 목차', note: '전체 본문은 llms-full.txt', href: `${basePath}/llms.txt`, external: true },
];

export default function HomePage() {
  const version = repoVersion();
  const diagram = architectureDiagram();

  return (
    <main className="flex flex-1 flex-col">
      {/* ── 히어로 한 줄 ─────────────────────────────────────────────── */}
      <section className="relative overflow-hidden border-b border-fd-border">
        <div aria-hidden className="hc-grid-field absolute inset-0" />
        <div className="relative mx-auto w-full max-w-5xl px-6 pt-16 pb-14 md:pt-24 md:pb-20">
          <p className="hc-label">스킬·툴 카탈로그 · MCP 레지스트리</p>
          <h1 className="mt-4 max-w-3xl text-[1.75rem] leading-[1.35] font-semibold tracking-[-0.02em] text-balance md:text-[2.5rem] md:leading-[1.3]">
            스킬은 <span className="text-fd-primary">git 저장소</span>에 있고, 하네스는 그것을{' '}
            MCP 로 찾는다.
          </h1>
          <p className="mt-5 max-w-xl text-[0.97rem] leading-[1.8] text-fd-muted-foreground">
            {appTagline}
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href={`${docsRoute}/quickstart`}
              className="inline-flex items-center gap-2 rounded-[5px] bg-fd-primary px-4 py-2.5 text-[0.9rem] font-medium text-fd-primary-foreground transition-opacity hover:opacity-90"
            >
              빠른 시작
              <ArrowRight className="size-4" />
            </Link>
            <Link
              href={docsRoute}
              className="inline-flex items-center gap-2 rounded-[5px] border border-fd-border bg-fd-card px-4 py-2.5 text-[0.9rem] font-medium transition-colors hover:border-fd-primary hover:text-fd-primary"
            >
              문서 전체
            </Link>
          </div>

          {/* 대장의 표제행 — 변하지 않는 사실만 적는다. */}
          <dl className="mt-12 grid max-w-3xl grid-cols-2 gap-x-8 gap-y-5 border-t border-fd-border pt-6 md:grid-cols-4">
            {[
              ['정본', 'git 저장소'],
              ['판', 'tree SHA'],
              ['도구', '넷, 전부 읽기'],
              ['배포물', version ? `v${version} lockstep` : 'lockstep 넷'],
            ].map(([term, value]) => (
              <div key={term}>
                <dt className="hc-label">{term}</dt>
                <dd className="mt-1 font-mono text-[0.82rem] text-fd-foreground">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* ── 네 갈래 진입: 색인 카드 ──────────────────────────────────── */}
      <section className="mx-auto w-full max-w-5xl px-6 py-14 md:py-18">
        <div className="flex items-baseline justify-between">
          <h2 className="hc-label">어디서부터</h2>
          <span className="hc-label">04</span>
        </div>
        <div className="mt-5 grid gap-px overflow-hidden rounded-[6px] border border-fd-border bg-fd-border sm:grid-cols-2">
          {entries.map((entry) => (
            <Link
              key={entry.index}
              href={entry.href}
              className="group relative flex flex-col gap-3 bg-fd-card p-6 transition-colors hover:bg-fd-accent"
            >
              {/* 색인 카드의 머리: 번호와 독자 */}
              <div className="flex items-center gap-2.5">
                <span className="font-mono text-[0.7rem] text-fd-muted-foreground">
                  {entry.index}
                </span>
                <span className="h-px flex-1 bg-fd-border" />
                <span className="hc-label">{entry.audience}</span>
              </div>
              <h3 className="text-[1.05rem] font-semibold tracking-[-0.01em] group-hover:text-fd-primary">
                {entry.title}
              </h3>
              <p className="text-[0.88rem] leading-[1.75] text-fd-muted-foreground">{entry.body}</p>
              <code className="hc-chip mt-auto self-start text-[0.72rem]">{entry.hint}</code>
            </Link>
          ))}
        </div>
      </section>

      {/* ── 구조: README 의 구성도를 그대로 ─────────────────────────── */}
      {diagram ? (
        <section className="border-t border-fd-border bg-fd-background">
          <div className="mx-auto w-full max-w-5xl px-6 py-14 md:py-18">
            <div className="flex items-baseline justify-between">
              <h2 className="hc-label">구조</h2>
              <span className="hc-label">README.md</span>
            </div>
            <p className="mt-4 max-w-xl text-[0.92rem] leading-[1.8] text-fd-muted-foreground">
              레지스트리는 카탈로그 저장소의 <code className="hc-chip">main</code> 을 주기적으로 받아
              검사·색인하고, 하네스가 MCP 로 물으면 답한다. 저장소에는 읽기 전용 배포 키로만 닿는다.
            </p>
            <Mermaid chart={diagram} />
          </div>
        </section>
      ) : null}

      {/* ── 그 밖: 대장 줄 ──────────────────────────────────────────── */}
      <section className="border-t border-fd-border">
        <div className="mx-auto w-full max-w-5xl px-6 py-14 md:py-18">
          <h2 className="hc-label">참조와 원장</h2>
          <ul className="mt-5 divide-y divide-fd-border border-y border-fd-border">
            {ledger.map((row) => {
              // 사이트 안의 쪽은 Link(basePath 가 붙는다), 바깥은 그냥 <a>.
              const Tag = row.external ? 'a' : Link;
              return (
                <li key={row.key}>
                  <Tag
                    href={row.href}
                    className="group flex flex-wrap items-baseline gap-x-4 gap-y-1 py-3.5 transition-colors hover:text-fd-primary"
                  >
                    <code className="hc-chip min-w-[9.5rem] text-[0.76rem]">{row.key}</code>
                    <span className="text-[0.92rem] font-medium">{row.label}</span>
                    <span className="text-[0.84rem] text-fd-muted-foreground">{row.note}</span>
                    <ArrowRight className="ms-auto size-4 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" />
                  </Tag>
                </li>
              );
            })}
          </ul>
        </div>
      </section>

      <footer className="mt-auto border-t border-fd-border bg-fd-card">
        <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-3 px-6 py-7 text-[0.8rem] text-fd-muted-foreground">
          <span className="font-mono">{siteUrl}</span>
          <a className="hover:text-fd-primary" href={repoUrl} rel="noreferrer">
            alteralab/harness-catalog
          </a>
        </div>
      </footer>
    </main>
  );
}
