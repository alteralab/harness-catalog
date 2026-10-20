import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { repoVersion } from '@/lib/repo-facts';
import { appTagline, basePath, docsRoute, repoBlob, repoUrl, siteUrl } from '@/lib/shared';

/** 네 갈래 진입 — 독자가 자기 자리를 먼저 고른다. 순서·글은 docs/ 의 쪽들과 짝이다.
 *  `hint` 는 **그대로 복사해 돌아가는 명령**이다. 줄임표(…)를 넣지 않는다 — 랜딩에서 베껴 간
 *  명령이 붙여넣자마자 깨지는 것은 그 자체로 결함이다(2026-10-20 사용자 지적). */
const entries = [
  {
    index: '01',
    audience: '처음',
    title: '먼저 돌려 보기',
    body: 'Docker 하나로 레지스트리·Dex·PostgreSQL·심은 카탈로그가 내 머신에 뜬다. 편집할 파일도 환경 변수도 없다.',
    hint: 'docker compose -f docker/compose.quickstart.yml up -d --build --wait',
    href: `${docsRoute}/quickstart`,
  },
  {
    index: '02',
    audience: '팀원',
    title: '하네스에서 쓰기',
    body: '하네스에 레지스트리를 등록하고 LDAP 계정으로 한 번 로그인한다. 그 뒤로는 "캡션 가져와"로 스킬을 찾는다.',
    hint: 'claude mcp add --transport http --scope user harness-catalog https://<레지스트리 호스트>/mcp',
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

/** 히어로 오른쪽 판 — 이 제품이 실제로 하는 한 가지를 보인다: 하네스가 MCP 로 묻고,
 *  레지스트리가 BM25 와 임베딩을 볼록 결합해 점수 순으로 답한다.
 *  이름은 카탈로그의 실제 스킬 셋(pin·review·write)이고, 계수 0.85 는 search.py 의 ALPHA 다.
 *  질의와 점수는 보기다 — 머리에 `예시`를 달아 실측으로 읽히지 않게 한다. */
/** 히어로 오른쪽 판 — 이 제품이 실제로 하는 한 가지를 보인다: 하네스가 MCP 로 묻고,
 *  레지스트리가 BM25 와 임베딩을 볼록 결합해 **순위**를 매겨 답한다.
 *
 *  점수 막대를 그리지 않는 이유: `Index.search` 의 반환형은 `tuple[str, ...]`(이름뿐)이고
 *  `SkillListing` 에도 점수 필드가 없다. 숫자를 그려 두면 있지도 않은 응답 필드를 약속하게 된다
 *  (2026-10-20 Codex 리뷰). 계수 0.85 는 search.py 의 ALPHA 이고, 이름 셋은 실제 카탈로그의
 *  스킬이다. 설명은 각 SKILL.md 의 description 을 한 줄로 줄인 것이고, 질의는 보기다. */
const hits = [
  { rank: '1', name: 'review', gloss: '스킬 하나를 규약에 견주어 심사한다' },
  { rank: '2', name: 'write', gloss: '새 스킬·도구의 뼈대를 만든다' },
  { rank: '3', name: 'pin', gloss: '스킬을 하네스 옆에 내려받는다' },
];

function SearchPanel() {
  return (
    <figure className="hc-panel w-full">
      <div className="flex items-center gap-2.5 border-b border-fd-border px-4 py-2.5">
        <span aria-hidden className="size-1.5 rounded-full bg-fd-primary" />
        <span className="font-mono text-[0.72rem] text-fd-foreground">search_skills</span>
        <span className="hc-label ms-auto">예시</span>
      </div>

      <div className="px-4 py-4">
        <p className="font-mono text-[0.76rem] text-fd-muted-foreground">
          <span className="text-fd-primary">질의</span> “코드 리뷰 어떻게 하지”
        </p>

        <ol className="mt-4 flex flex-col gap-3">
          {hits.map((hit) => (
            <li key={hit.name} className="flex min-w-0 items-baseline gap-3">
              <span className="font-mono text-[0.7rem] text-fd-muted-foreground tabular-nums">
                {hit.rank}
              </span>
              <code className="hc-chip shrink-0 text-[0.72rem]">{hit.name}</code>
              <span className="min-w-0 flex-1 text-[0.78rem] leading-[1.6] text-fd-muted-foreground">
                {hit.gloss}
              </span>
            </li>
          ))}
        </ol>
      </div>

      <figcaption className="border-t border-fd-border px-4 py-2.5 font-mono text-[0.7rem] leading-[1.7] text-fd-muted-foreground">
        0.85 × 임베딩 + 0.15 × BM25 로 매긴 순위. 점수 자체는 돌려주지 않는다.
      </figcaption>
    </figure>
  );
}

/** 구조 그림 — 세 칸과 이름 붙은 화살표 둘. README 의 전체 구성도(열다섯 칸)를 여기 끌어오면
 *  글자가 6px 로 줄어 읽히지 않는다(2026-10-20 실측). 랜딩은 기구(機構) 하나만 보인다.
 *  전체 구성도는 README 에 그대로 있다. */
const stages = [
  { title: '카탈로그 저장소', lines: ['skills/<이름>/', 'tools/<이름>/'] },
  { title: '레지스트리', lines: ['검사 · 색인', 'BM25 + 임베딩'] },
  { title: '하네스', lines: ['Claude Code · Codex', 'Cursor'] },
];
const links = [
  { label: '주기적으로 받기', note: '읽기 전용 배포 키' },
  { label: 'MCP over HTTP', note: 'OIDC 토큰' },
];

function FlowFigure() {
  return (
    <figure className="mt-6">
      <div className="flex flex-col items-stretch gap-3 md:flex-row md:items-center">
        {stages.map((stage, i) => (
          <div key={stage.title} className="contents">
            <div className="hc-panel flex-1 px-5 py-4">
              <p className="text-[0.95rem] font-semibold tracking-[-0.01em]">{stage.title}</p>
              {stage.lines.map((line) => (
                <p key={line} className="mt-1 font-mono text-[0.74rem] text-fd-muted-foreground">
                  {line}
                </p>
              ))}
            </div>
            {i < links.length ? (
              <div className="flex shrink-0 flex-col items-center gap-1 px-1 py-1 md:w-36">
                <span className="hc-label whitespace-nowrap">{links[i].label}</span>
                <span aria-hidden className="hc-connector" />
                <span className="font-mono text-[0.68rem] whitespace-nowrap text-fd-muted-foreground">
                  {links[i].note}
                </span>
              </div>
            ) : null}
          </div>
        ))}
      </div>
      <figcaption className="mt-4 text-[0.82rem] leading-[1.7] text-fd-muted-foreground">
        정본은 저장소 한 곳이다. 레지스트리가 들고 있는 것은 언제든 다시 지을 수 있는 사본이다.
      </figcaption>
    </figure>
  );
}

/** 절마다 눈썹(작은 모노 라벨)과 제목(본문 서체)을 함께 세운다 — 눈썹만 있으면 쪽에 마디가 없다. */
function SectionHead({ eyebrow, title, aside }: { eyebrow: string; title: string; aside?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <div>
        <p className="hc-label">{eyebrow}</p>
        <h2 className="mt-2 text-[1.35rem] font-semibold tracking-[-0.015em] md:text-[1.5rem]">
          {title}
        </h2>
      </div>
      {aside ? <span className="hc-label shrink-0">{aside}</span> : null}
    </div>
  );
}

export default function HomePage() {
  const version = repoVersion();

  return (
    <main className="flex flex-1 flex-col">
      {/* ── 히어로: 왼쪽은 주장, 오른쪽은 그 주장이 실제로 도는 모습 ──────── */}
      <section className="relative overflow-hidden border-b border-fd-border">
        <div aria-hidden className="hc-grid-field absolute inset-0" />
        <div className="relative mx-auto grid w-full max-w-6xl items-center gap-10 px-6 pt-16 pb-14 md:pt-20 md:pb-18 lg:grid-cols-12 lg:gap-12">
          <div className="lg:col-span-7">
            <p className="hc-label">스킬·툴 카탈로그 · MCP 레지스트리</p>
            <h1 className="mt-4 text-[1.9rem] leading-[1.32] font-semibold tracking-[-0.025em] text-balance md:text-[2.6rem] md:leading-[1.28]">
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
          </div>

          <div className="lg:col-span-5">
            <SearchPanel />
          </div>
        </div>
      </section>

      {/* ── 네 갈래 진입: 색인 카드 ──────────────────────────────────── */}
      <section className="mx-auto w-full max-w-6xl px-6 py-14 md:py-18">
        <SectionHead eyebrow="어디서부터" title="자기 자리를 먼저 고른다" aside="04" />
        <div className="mt-6 grid gap-px overflow-hidden rounded-[6px] border border-fd-border bg-fd-border sm:grid-cols-2">
          {entries.map((entry) => (
            <Link
              key={entry.index}
              href={entry.href}
              className="group relative flex min-w-0 flex-col gap-3 bg-fd-card p-6 transition-colors hover:bg-fd-accent"
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
              <code className="hc-chip hc-cmd mt-auto w-full text-[0.72rem]">{entry.hint}</code>
            </Link>
          ))}
        </div>
      </section>

      {/* ── 구조: 기구 하나 ─────────────────────────────────────────── */}
      <section className="border-t border-fd-border bg-fd-background">
        <div className="mx-auto w-full max-w-6xl px-6 py-14 md:py-18">
          <SectionHead eyebrow="구조" title="저장소가 정본, 레지스트리는 사본" aside="README.md" />
          <p className="mt-4 max-w-2xl text-[0.92rem] leading-[1.8] text-fd-muted-foreground">
            레지스트리는 카탈로그 저장소의 <code className="hc-chip">main</code> 을 주기적으로 받아
            검사·색인하고, 하네스가 MCP 로 물으면 답한다. 저장소에는 읽기 전용 배포 키로만 닿는다.
          </p>
          <FlowFigure />

          {/* 대장의 표제행 — 변하지 않는 사실만 적는다. 그림 아래가 이 값들이 읽히는 자리다. */}
          <dl className="mt-10 grid grid-cols-2 gap-x-8 gap-y-5 border-t border-fd-border pt-6 md:grid-cols-4">
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

      {/* ── 그 밖: 대장 줄 ──────────────────────────────────────────── */}
      <section className="border-t border-fd-border">
        <div className="mx-auto w-full max-w-6xl px-6 py-14 md:py-18">
          <SectionHead eyebrow="참조" title="원장과 참조" />
          <ul className="mt-6 divide-y divide-fd-border border-y border-fd-border">
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
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-7 text-[0.8rem] text-fd-muted-foreground">
          <span className="font-mono break-all">{siteUrl}</span>
          <a className="hover:text-fd-primary" href={repoUrl} rel="noreferrer">
            alteralab/harness-catalog
          </a>
        </div>
      </footer>
    </main>
  );
}
