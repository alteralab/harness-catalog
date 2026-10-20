// 색인(out/api/search)에 한국어 질의를 직접 돌려 건수를 센다 — 검색 설정을 바꿀 때 전후를 숫자로 본다.
//
//   node scripts/search-probe.mjs [색인경로]
//
// 엔진은 zbsearch 이고 지원 언어에 한국어가 없다. 그래서 둘을 같이 재 둔다:
//   · tolerance 0 — 토큰이 그대로 맞아야 한다(조사 변화형은 못 맞춘다)
//   · tolerance 1 — 편집 거리 1 까지 허용(`레지스트리가` ↔ `레지스트리를`/`레지스트리`)
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { create, load, search } from 'zbsearch';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const indexPath = process.argv[2] ?? path.join(root, 'out/api/search');

const QUERIES = [
  '레지스트리',
  '레지스트리를',
  '레지스트리가',
  '하이브리드',
  '임베딩',
  '배포 절차',
  'BM25',
  'registry',
];

const raw = JSON.parse(readFileSync(indexPath, 'utf8'));
const db = create({ schema: { _: 'string' } });
load(db, raw);

const rows = [];
for (const term of QUERIES) {
  const strict = await search(db, { term, limit: 50 });
  const fuzzy = await search(db, { term, limit: 50, tolerance: 1 });
  rows.push([term, strict.count, fuzzy.count]);
}

const width = Math.max(...QUERIES.map((q) => [...q].length * 2));
console.log(`색인: ${indexPath}`);
console.log(`${'질의'.padEnd(width)}  tolerance 0  tolerance 1`);
for (const [term, strict, fuzzy] of rows) {
  const pad = width - [...term].length * 2;
  console.log(`${term}${' '.repeat(Math.max(pad, 1))}  ${String(strict).padStart(11)}  ${String(fuzzy).padStart(11)}`);
}
