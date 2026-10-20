import { source } from '@/lib/source';
import { createFromSource } from 'fumadocs-core/search/server';

export const revalidate = false;

// 정적 내보내기라 서버가 없다 — 색인 전체가 out/api/search 한 파일로 떨어지고 브라우저에서 찾는다.
// 엔진(zbsearch)의 언어 목록에 한국어가 없다. 'english' 를 박아 두면 영어 어간 추출기와
// 영어 불용어가 한국어 토큰에 걸린다 — 'multilingual' 은 어간 추출을 끄고 토큰을 그대로 남긴다.
// 조사 변화형은 질의 쪽 tolerance 가 메운다(lib/shared.ts 의 staticSearchParams). 수치: scripts/search-probe.mjs.
export const { staticGET: GET } = createFromSource(source, {
  language: 'multilingual',
});
