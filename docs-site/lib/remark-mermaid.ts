import type { Root } from 'mdast';
import { visit } from 'unist-util-visit';

/**
 * ```mermaid 코드 울타리를 `<Mermaid chart="…" />` 로 바꾼다.
 *
 * shiki(rehype-code) 보다 먼저 돌아야 하므로 remark 단계다 — 울타리가 하이라이트된 <pre> 로 바뀌면
 * 원문을 되찾을 수 없다. 그려 주는 쪽은 클라이언트 컴포넌트(components/mermaid.tsx)다: `rehype-mermaid` 는
 * 빌드에 headless 브라우저를 끌어오므로 CI 가 무거워진다.
 */
export function remarkMermaid() {
  return (tree: Root) => {
    visit(tree, 'code', (node, index, parent) => {
      if (node.lang !== 'mermaid' || !parent || index === undefined) return;
      // mdxJsxFlowElement 는 mdast 기본 타입에 없다(mdast-util-mdx-jsx 의 확장) — 런타임은 MDX 가 처리한다.
      parent.children[index] = {
        type: 'mdxJsxFlowElement',
        name: 'Mermaid',
        attributes: [{ type: 'mdxJsxAttribute', name: 'chart', value: node.value }],
        children: [],
      } as unknown as Root['children'][number];
    });
  };
}
