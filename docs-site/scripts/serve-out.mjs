// out/ 을 운영과 같은 하위 경로(`/harness-catalog/`)로 서빙한다 — 링크·자산·검색을 그 자리에서 보려고.
// 운영은 NAS MinIO + 앞의 nginx 다. 이 서버는 그 nginx 처럼 디렉토리 요청에 index.html 을 돌려준다.
//
//   node scripts/serve-out.mjs [포트]
import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = path.join(root, 'out');
const basePath = process.env.DOCS_BASE_PATH ?? '/harness-catalog';
const port = Number(process.argv[2] ?? 8810);

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
};

async function resolve(urlPath) {
  const candidates = [urlPath, path.join(urlPath, 'index.html'), `${urlPath}.html`];
  for (const candidate of candidates) {
    const full = path.join(out, candidate);
    if (!full.startsWith(out)) continue;
    try {
      if ((await stat(full)).isFile()) return full;
    } catch {
      /* 다음 후보 */
    }
  }
  return null;
}

http
  .createServer(async (req, res) => {
    const { pathname } = new URL(req.url ?? '/', 'http://localhost');
    if (basePath && !pathname.startsWith(basePath)) {
      res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
      res.end(`${basePath} 하위만 서빙한다 (요청: ${pathname})\n`);
      return;
    }
    const rel = decodeURIComponent(pathname.slice(basePath.length)) || '/';
    const file = await resolve(rel);
    if (!file) {
      res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
      res.end(`404 ${pathname}\n`);
      return;
    }
    // api/search 는 확장자가 없다 — MinIO 와 달리 여기서는 JSON 으로 못박아 둔다.
    const type = TYPES[path.extname(file)] ?? (file.endsWith('search') ? 'application/json' : 'application/octet-stream');
    res.writeHead(200, { 'content-type': type });
    createReadStream(file).pipe(res);
  })
  .listen(port, () => {
    console.log(`http://127.0.0.1:${port}${basePath}/`);
  });
