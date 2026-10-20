import { readFileSync } from 'node:fs';
import path from 'node:path';

// 빌드 때 저장소에서 바로 읽는다 — 랜딩에 숫자를 손으로 적어 두면 릴리스마다 어긋난다.
// 정적 내보내기라 이 코드는 빌드에서만 돈다(클라이언트로 가지 않는다).
const repoRoot = path.resolve(process.cwd(), '..');

function read(relative: string): string | null {
  try {
    return readFileSync(path.join(repoRoot, relative), 'utf8');
  } catch {
    return null;
  }
}

/** 네 배포물은 lockstep 이라 판이 같다 — core 의 것을 읽는다. */
export function repoVersion(): string | null {
  const toml = read('packages/core/pyproject.toml');
  return toml?.match(/^version\s*=\s*"([^"]+)"/m)?.[1] ?? null;
}

/** README 의 첫 mermaid 울타리(레지스트리 구성도). 원본이 정본이고 여기서 베끼지 않는다. */
export function architectureDiagram(): string | null {
  const readme = read('README.md');
  return readme?.match(/```mermaid\n([\s\S]*?)\n```/)?.[1] ?? null;
}
