# 설정값

레지스트리 프로세스가 읽는 환경 변수. 비밀은 `<이름>_FILE=<경로>`로 파일에서도 읽는다.

| 변수 | 필수 | 기본값 | 뜻 |
|---|---|---|---|
| `HC__CATALOG_REPO_URL` | 예 |  | 카탈로그 git 저장소 URL (deploy key로 fetch만 한다) |
| `HC__GIT_DEPLOY_KEY` | 예 |  | 읽기 전용 deploy key의 개인 키(PEM). 로컬 file:// 저장소면 빈 문자열 |
| `HC__OIDC_ISSUER` | 예 |  | OIDC issuer URL (토큰의 iss, JWKS 발견) |
| `HC__PUBLIC_URL` | 예 |  | 레지스트리 공개 URL = 토큰의 audience = RFC 9728 resource |
| `HC__DATABASE_URL` | 예 |  | PostgreSQL 접속 문자열 |
| `HC__FETCH_INTERVAL_SECONDS` | 아니오 | 60 | 주기 fetch 간격(초) |
