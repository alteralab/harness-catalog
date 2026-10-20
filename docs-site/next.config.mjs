import { createMDX } from 'fumadocs-mdx/next';

const withMDX = createMDX();

// 운영의 서빙 자리는 NAS MinIO 버킷 + 앞의 nginx 이고, 경로가 `/harness-catalog/` 하위다.
// basePath 를 비우면 링크·자산·검색 색인이 전부 루트(`/_next/...`)를 가리켜 404 가 된다(실측).
// 로컬에서 루트로 서빙해 보려면 DOCS_BASE_PATH= 로 비워 둔다.
const basePath = process.env.DOCS_BASE_PATH ?? '/harness-catalog';

/** @type {import('next').NextConfig} */
const config = {
  output: 'export',
  // 산출물을 `<route>/index.html` 로 낸다 — MinIO/nginx 가 디렉토리 요청에 index.html 을 돌려주는
  // 지금 배선(mkdocs 가 내던 모양)을 그대로 쓴다. 끄면 `<route>.html` 이 되어 nginx 규칙이 필요하다.
  trailingSlash: true,
  basePath,
  reactStrictMode: true,
  // 정적 내보내기에는 이미지 최적화 서버가 없다.
  images: { unoptimized: true },
  // 클라이언트 코드가 basePath 를 알아야 하는 자리가 둘 있다: 검색 색인 fetch, 자체 호스팅 폰트 CSS.
  env: { NEXT_PUBLIC_BASE_PATH: basePath },
};

export default withMDX(config);
