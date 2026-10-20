'use client';

import { useEffect, useId, useRef, useState } from 'react';

/**
 * ```mermaid 울타리를 그려 준다. lib/remark-mermaid.ts 가 울타리를 이 컴포넌트로 바꿔 놓는다.
 *
 * mermaid 는 1MB 가 넘으므로 `import()` 로 늦게 받는다 — 그림이 있는 쪽에서만 내려온다.
 * 테마는 CSS 변수에서 읽고, 라이트↔다크 전환(`<html class="dark">`)을 지켜보다 다시 그린다.
 */
export function Mermaid({ chart }: { chart: string }) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, '');
  const host = useRef<HTMLDivElement>(null);
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const read = () => setDark(document.documentElement.classList.contains('dark'));
    read();
    const observer = new MutationObserver(read);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      const style = getComputedStyle(document.documentElement);
      const token = (name: string, fallback: string) =>
        style.getPropertyValue(name).trim() || fallback;

      const paper = token('--hc-card', dark ? '#151e22' : '#ffffff');
      const sunken = token('--hc-sunken', dark ? '#1a2429' : '#e9edee');
      const line = token('--hc-line-strong', dark ? '#38474e' : '#bfcacd');
      const ink = token('--hc-ink', dark ? '#dde6e8' : '#0f1c1f');
      const teal = token('--hc-teal', dark ? '#3fb8ae' : '#0a6a6c');

      const { default: mermaid } = await import('mermaid');
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        fontFamily: 'var(--font-sans)',
        theme: 'base',
        themeVariables: {
          background: paper,
          primaryColor: sunken,
          primaryBorderColor: line,
          primaryTextColor: ink,
          secondaryColor: paper,
          secondaryBorderColor: line,
          tertiaryColor: paper,
          tertiaryBorderColor: line,
          lineColor: teal,
          textColor: ink,
          nodeBorder: line,
          clusterBkg: 'transparent',
          clusterBorder: line,
          edgeLabelBackground: paper,
          fontSize: '14px',
        },
      });

      const { svg } = await mermaid.render(`hc-mermaid-${id}`, chart);
      if (!cancelled && host.current) host.current.innerHTML = svg;
    })();

    return () => {
      cancelled = true;
    };
  }, [chart, dark, id]);

  return <div data-hc-mermaid="" ref={host} role="img" aria-label="구성도" />;
}

export default Mermaid;
