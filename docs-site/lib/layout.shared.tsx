import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';
import { appName, basePath, docsRoute, repoUrl } from './shared';

/** 헤더는 두 층 다(랜딩·문서) 같은 것을 쓴다 — 제목은 글자 그대로의 저장소 이름이다. */
export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: (
        <span className="flex items-baseline gap-2">
          <span
            aria-hidden
            className="inline-block size-2 rounded-[1px] bg-fd-primary align-middle"
          />
          <span className="font-mono text-[0.95rem] font-medium tracking-tight">{appName}</span>
        </span>
      ),
      transparentMode: 'none',
    },
    links: [
      { text: '문서', url: docsRoute, active: 'nested-url' },
      { text: '빠른 시작', url: `${docsRoute}/quickstart`, active: 'url' },
      // 정적 파일이라 Next 라우터를 타지 않는다 — basePath 를 직접 붙인다.
      { text: 'llms.txt', url: `${basePath}/llms.txt`, external: true },
    ],
    githubUrl: repoUrl,
  };
}
