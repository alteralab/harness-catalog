// Pretendard Variable 을 public/fonts/ 로 베낀다 — 빌드마다, 고정된 npm 판(`pretendard`)에서.
//
// 왜 베끼는가: 한글 본문이라 본문 서체가 CDN 에 매달리면 안 된다(자체 호스팅). 그리고 통짜 가변 폰트는
// 2.0MB 다 — dynamic subset 은 유니코드 구간별 92조각이라 브라우저가 쓰는 조각만 받는다. CSS 안의 url 이
// `./woff2-dynamic-subset/…` 상대 경로라서 디렉토리 모양을 그대로 유지하면 그대로 맞는다.
//
// 산출물은 커밋하지 않는다(.gitignore). 판은 package.json 의 `pretendard` 핀이 정본이다.
import { cp, mkdir, readdir, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const src = path.join(root, 'node_modules/pretendard/dist/web/variable');
const dest = path.join(root, 'public/fonts/pretendard');

const CSS = 'pretendardvariable-dynamic-subset.css';
const SUBSET_DIR = 'woff2-dynamic-subset';

try {
  await stat(path.join(src, CSS));
} catch {
  console.error(`[vendor-fonts] ${path.join(src, CSS)} 가 없다 — npm install 을 먼저 할 것`);
  process.exit(1);
}

await mkdir(dest, { recursive: true });
await cp(path.join(src, CSS), path.join(dest, CSS));
await cp(path.join(src, SUBSET_DIR), path.join(dest, SUBSET_DIR), { recursive: true });

const files = await readdir(path.join(dest, SUBSET_DIR));
console.log(`[vendor-fonts] Pretendard Variable → public/fonts/pretendard (조각 ${files.length}개)`);
