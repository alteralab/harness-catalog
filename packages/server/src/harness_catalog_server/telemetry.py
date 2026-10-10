"""OTel 배선: 표준 환경 변수(OTEL_EXPORTER_OTLP_ENDPOINT 등)가 있을 때만 TracerProvider + OTLP/HTTP exporter를 전역에 꽂는다.

MCP SDK는 `get_tracer("mcp-python-sdk")`로 `tools/call <tool>` 스팬을 내고 도구 어댑터가 속성을 더하지만, 전역 provider가 없으면
스팬은 비기록(no-op)이라 아무 데도 가지 않는다(2026-10-10 실측: 서버 어디에서도 provider를 만들지 않았다). ENDPOINT가 비면 그대로 no-op.
exporter는 자기 환경 변수(ENDPOINT·HEADERS·PROTOCOL·TIMEOUT)를 스스로 읽는다 — 여기서는 provider·service.name·헤더 비밀 파일(_FILE, D10)만 꽂는다(DESIGN §2 Configurator: OTel은 설정값이 아니다).
"""

from __future__ import annotations

import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

log = logging.getLogger(__name__)
DEFAULT_SERVICE_NAME = "harness-catalog"


def headers_from_file(path: str) -> dict[str, str]:
    """OTEL_EXPORTER_OTLP_HEADERS_FILE(docker secret) — 내용은 표준 변수와 같은 `k=v,k2=v2`. 없거나 비면 {} (그때 exporter는 환경 변수를 쓴다)."""
    if not path.strip() or not os.path.exists(path):
        return {}
    text = open(path, encoding="utf-8").read().strip()  # noqa: SIM115, PTH123 — 한 번 읽고 닫는다
    out: dict[str, str] = {}
    for pair in filter(None, (p.strip() for p in text.split(","))):
        key, sep, value = pair.partition("=")
        if sep:
            out[key.strip()] = value.strip()
    return out


def configure_tracing(environ: dict[str, str] | None = None) -> TracerProvider | None:
    """ENDPOINT가 있으면 provider를 만들어 전역으로 설정하고 돌려준다. 없으면 None(스팬 no-op)."""
    env = os.environ if environ is None else environ
    endpoint = env.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return None
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # noqa: PLC0415 — ENDPOINT가 있을 때만 적재

    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: env.get("OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME)}))
    headers = headers_from_file(env.get("OTEL_EXPORTER_OTLP_HEADERS_FILE", ""))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(headers=headers) if headers else OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    log.info("tracing on: otlp/http -> %s", endpoint)
    return provider
