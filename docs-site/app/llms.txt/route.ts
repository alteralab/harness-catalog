import { absolutizeLinks, docsLlms } from '@/lib/source';
import { absoluteUrl, appName } from '@/lib/shared';

export const revalidate = false;

// 에이전트용 목차. 옛 사이트의 mkdocs-llmstxt 가 내던 것과 같은 구실이고, 머리글의 설명도 그것을 잇는다.
const HEAD = `# ${appName}

> 스킬·툴 카탈로그와 MCP 레지스트리. 스킬 하나는 git 저장소의 디렉토리 하나이고, \`main\` 에 병합된 것이 게시된 판이다.
> 레지스트리는 그 저장소를 받아 검사·색인하고 하네스가 MCP 로 물으면 답한다(도구 넷, 전부 읽기).
> 전체 본문은 ${absoluteUrl('/llms-full.txt').replace(/\/$/, '')} 에 있다.
`;

export async function GET() {
  const index = absolutizeLinks(await docsLlms.index());
  return new Response(`${HEAD}\n${index}`, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
