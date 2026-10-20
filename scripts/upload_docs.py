#!/usr/bin/env python3
"""문서 사이트 산출물(`docs-site/out`)을 S3 호환 저장소의 버킷으로 올린다 — 거울처럼. 멱등.

DESIGN §11 2026-10-20: 문서 사이트는 앱 배포와 분리된 정적 호스팅에 둔다. 우리 설치의 그 자리는
NAS 의 MinIO 버킷이고, 앞의 nginx 가 S3 "웹사이트 엔드포인트"를 대신한다(portainer repo 의 stacks/minio).

호출(CI 가 이렇게 부른다 — .github/workflows/docs.yml):
    MINIO_ENDPOINT=https://ds923plus.tail2f9fe3.ts.net:9800 \
    MINIO_BUCKET=harness-catalog-docs \
    MINIO_ACCESS_KEY=… MINIO_SECRET_KEY=… \
    uv run --no-project python scripts/upload_docs.py docs-site/out

하는 일: 올리고(바뀐 것만), 로컬에 없는 원격 키는 지운다. 그래서 문서를 지운 PR 이 사이트에도 반영된다.

**Content-Type 을 반드시 싣는다.** 비워 두면 MinIO 가 저장한 그대로 돌려주는데, 브라우저는
`x-content-type-options: nosniff` 때문에 HTML 을 렌더하지 않는다(2026-10-20 실측: 타입 없이 올렸더니
`application/x-www-form-urlencoded` 로 나갔다).

비밀은 환경변수로만 받는다. fail-loud: 실패한 키를 stderr 에 남기고 비0 종료.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
REGION = os.environ.get("MINIO_REGION", "us-east-1")

# mimetypes 가 놓치거나 틀리게 보는 것만 못박는다. 나머지는 확장자로 추측한다.
EXTRA_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json",
    ".map": "application/json",
    ".svg": "image/svg+xml",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".xml": "application/xml",
}


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"{name} 가 비어 있다 — CI 시크릿 또는 환경을 확인할 것")
    return value


# 확장자가 없는 데이터 파일. 검색 색인이 그렇다(`/api/search`) — 확장자가 없어 추측이 octet-stream 으로
# 떨어진다. 브라우저의 res.json() 은 타입을 안 보지만, 저장된 타입이 틀린 채로 남는 것은 그 자체로 결함이다.
EXTRA_BY_KEY = {"api/search": "application/json"}


def content_type(path: Path, key: str = "") -> str:
    if key in EXTRA_BY_KEY:
        return EXTRA_BY_KEY[key]
    suffix = path.suffix.lower()
    if suffix in EXTRA_TYPES:
        return EXTRA_TYPES[suffix]
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


class Client:
    """SigV4 로 서명하는 최소 S3 클라이언트. boto3·mc 를 끌어오지 않는다(러너에 도구를 늘리지 않는다)."""

    def __init__(self) -> None:
        self.endpoint = _env("MINIO_ENDPOINT").rstrip("/")
        self.bucket = _env("MINIO_BUCKET")
        self.access = _env("MINIO_ACCESS_KEY")
        self.secret = _env("MINIO_SECRET_KEY")
        self.host = self.endpoint.split("://", 1)[1]

    def request(self, method: str, key: str = "", query: str = "", body: bytes = b"",
                headers: dict[str, str] | None = None) -> tuple[int, bytes]:
        path = f"/{self.bucket}" + (f"/{urllib.parse.quote(key, safe='/~_-.')}" if key else "")
        extra = {k.lower(): v for k, v in (headers or {}).items()}
        payload = hashlib.sha256(body).hexdigest()
        now = datetime.datetime.now(datetime.timezone.utc)
        amz, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")

        signed = {"host": self.host, "x-amz-content-sha256": payload, "x-amz-date": amz, **extra}
        names = ";".join(sorted(signed))
        canonical_headers = "".join(f"{k}:{signed[k]}\n" for k in sorted(signed))
        canonical = f"{method}\n{path}\n{query}\n{canonical_headers}\n{names}\n{payload}"
        scope = f"{day}/{REGION}/s3/aws4_request"
        to_sign = f"AWS4-HMAC-SHA256\n{amz}\n{scope}\n{hashlib.sha256(canonical.encode()).hexdigest()}"
        key_bytes = f"AWS4{self.secret}".encode()
        for part in (day, REGION, "s3", "aws4_request"):
            key_bytes = hmac.new(key_bytes, part.encode(), hashlib.sha256).digest()
        signature = hmac.new(key_bytes, to_sign.encode(), hashlib.sha256).hexdigest()

        request = urllib.request.Request(
            self.endpoint + path + (f"?{query}" if query else ""),
            data=body or None, method=method,
            headers={**signed, "Authorization":
                     f"AWS4-HMAC-SHA256 Credential={self.access}/{scope}, "
                     f"SignedHeaders={names}, Signature={signature}"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def remote_keys(self) -> dict[str, str]:
        """{키: ETag} — ETag 로 바뀐 것만 올린다."""
        out: dict[str, str] = {}
        token = None
        while True:
            query = "list-type=2&max-keys=1000"
            if token:
                query += f"&continuation-token={urllib.parse.quote(token)}"
            status, body = self.request("GET", query=query)
            if status != 200:
                sys.exit(f"목록 실패 {status}: {body[:200]!r}")
            root = ET.fromstring(body)
            for item in root.iter(f"{NS}Contents"):
                # Key 가 없는 Contents 는 S3 응답으로 성립하지 않지만 findtext 의 타입은 None 을 허용한다 — 건너뛴다.
                remote_key = item.findtext(f"{NS}Key")
                if remote_key is None:
                    continue
                out[remote_key] = (item.findtext(f"{NS}ETag") or "").strip('"')
            if root.findtext(f"{NS}IsTruncated") != "true":
                return out
            token = root.findtext(f"{NS}NextContinuationToken")


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else "docs-site/out")
    if not root.is_dir():
        sys.exit(f"{root} 가 없다 — 먼저 `make docs-build` 로 만들 것")

    client = Client()
    local = {str(p.relative_to(root)): p for p in root.rglob("*") if p.is_file()}
    remote = client.remote_keys()
    print(f"로컬 {len(local)}개 · 원격 {len(remote)}개")

    def put(item: tuple[str, Path]) -> str | None:
        key, path = item
        data = path.read_bytes()
        if remote.get(key) == hashlib.md5(data).hexdigest():  # noqa: S324 — S3 ETag 는 MD5 다(보안 용도 아님)
            return None
        status, body = client.request("PUT", key, body=data,
                                      headers={"content-type": content_type(path, key)})
        return None if status in (200, 204) else f"PUT {key} -> {status} {body[:120]!r}"

    with ThreadPoolExecutor(max_workers=8) as pool:
        failed = [r for r in pool.map(put, local.items()) if r]

    stale = sorted(set(remote) - set(local))
    with ThreadPoolExecutor(max_workers=8) as pool:
        def drop(key: str) -> str | None:
            status, body = client.request("DELETE", key)
            return None if status in (200, 204) else f"DELETE {key} -> {status} {body[:120]!r}"
        failed += [r for r in pool.map(drop, stale) if r]

    uploaded = sum(1 for key, path in local.items()
                   if remote.get(key) != hashlib.md5(path.read_bytes()).hexdigest())  # noqa: S324
    print(f"올림 {uploaded}개 · 지움 {len(stale)}개 · 그대로 {len(local) - uploaded}개")

    if failed:
        print("\n실패:", file=sys.stderr)
        for line in failed:
            print(f"  - {line}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
