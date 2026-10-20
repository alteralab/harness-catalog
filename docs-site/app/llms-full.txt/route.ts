import { docsLlms } from '@/lib/source';
import { appName, siteUrl } from '@/lib/shared';

export const revalidate = false;

// 쪽 전부의 본문 한 파일. 쪽마다 머리에 제목과 절대 URL 이 붙는다(lib/source.ts 의 renderPage).
export async function GET() {
  const head = `# ${appName} — 문서 전체\n\n> ${siteUrl} 의 모든 쪽을 한 파일로. 목차는 llms.txt 에 있다.\n\n`;
  return new Response(head + (await docsLlms.full()), {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
