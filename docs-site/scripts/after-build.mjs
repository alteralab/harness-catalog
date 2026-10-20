// 빌드 뒤 산출물 점검 — 하위 경로 설치에서 조용히 깨지는 것들만 본다.
//
// 1) 쪽마다 index.html 이 났는가(trailingSlash 로 디렉토리 모양이어야 nginx/MinIO 가 돌려준다).
// 2) 자산·링크가 basePath 밖(`/_next/…`)을 가리키지 않는가 — 이게 틀리면 전부 404 인데 빌드는 성공한다.
// 3) llms.txt·llms-full.txt 가 비어 있지 않은가.
// 4) 검색 색인(api/search)이 JSON 으로 파싱되는가.
import { readFile, readdir, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = path.join(root, 'out');
const basePath = process.env.DOCS_BASE_PATH ?? '/harness-catalog';

const problems = [];
const ok = [];

async function exists(rel) {
  try {
    const s = await stat(path.join(out, rel));
    return s.isFile() ? s.size : 0;
  } catch {
    return null;
  }
}

async function htmlFiles(dir = out) {
  const entries = await readdir(dir, { withFileTypes: true });
  const found = [];
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) found.push(...(await htmlFiles(full)));
    else if (entry.name.endsWith('.html')) found.push(full);
  }
  return found;
}

for (const rel of ['index.html', 'docs/index.html', 'llms.txt', 'llms-full.txt', 'api/search']) {
  const size = await exists(rel);
  if (size === null) problems.push(`없다: out/${rel}`);
  else if (size === 0) problems.push(`비었다: out/${rel}`);
  else ok.push(`out/${rel} (${size}B)`);
}

// 콘텐츠 쪽이 전부 디렉토리 + index.html 로 났는가.
// 목록을 손으로 적지 않고 콘텐츠 루트(../docs)에서 샌다 — 쪽을 더하거나 과제 단위로 가를 때
// 이 배열을 같이 고치지 않으면 점검이 조용히 뒤처진다(2026-10-20: 쪽이 여섯에서 스물여섯으로).
async function markdownSlugs(dir, prefix = '') {
  const entries = await readdir(dir, { withFileTypes: true });
  const found = [];
  for (const entry of entries) {
    if (entry.isDirectory()) {
      found.push(...(await markdownSlugs(path.join(dir, entry.name), `${prefix}${entry.name}/`)));
      continue;
    }
    if (!entry.name.endsWith('.md')) continue;
    // 묶음의 index.md 는 그 묶음의 URL 자체다.
    const stem = entry.name.slice(0, -3);
    found.push(stem === 'index' ? prefix.replace(/\/$/, '') : `${prefix}${stem}`);
  }
  return found;
}

const slugs = (await markdownSlugs(path.join(root, '..', 'docs'))).filter(Boolean);
for (const slug of slugs) {
  const size = await exists(`docs/${slug}/index.html`);
  if (!size) problems.push(`없다: out/docs/${slug}/index.html`);
}
ok.push(`콘텐츠 쪽 ${slugs.length}개`);

// basePath 를 벗어난 절대 경로. href="/" 자체는 Next 가 내지 않으므로 /_next·/fonts 만 본다.
if (basePath) {
  const bad = [];
  for (const file of await htmlFiles()) {
    const html = await readFile(file, 'utf8');
    for (const m of html.matchAll(/(?:href|src)="(\/(?:_next|fonts|api)\/[^"]*)"/g)) {
      if (!m[1].startsWith(`${basePath}/`)) bad.push(`${path.relative(out, file)} → ${m[1]}`);
    }
  }
  if (bad.length) problems.push(`basePath 밖을 가리키는 자산 ${bad.length}개: ${bad.slice(0, 5).join(', ')}`);
  else ok.push(`basePath(${basePath}) 밖을 가리키는 자산 0개`);
}

const index = await readFile(path.join(out, 'api/search'), 'utf8').catch(() => null);
if (index) {
  try {
    JSON.parse(index);
    ok.push('검색 색인 JSON 파싱 성공');
  } catch {
    problems.push('검색 색인이 JSON 이 아니다');
  }
}

console.log('[after-build]');
for (const line of ok) console.log(`  ok   ${line}`);
for (const line of problems) console.error(`  FAIL ${line}`);
if (problems.length) process.exit(1);
