"""telemetry: ENDPOINT가 없으면 아무것도 꽂지 않고, 있으면 OTLP/HTTP exporter가 달린 provider를 만든다(네트워크 없음)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from harness_catalog_server.telemetry import DEFAULT_SERVICE_NAME, configure_tracing
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

if TYPE_CHECKING:
    from pathlib import Path


def test_no_endpoint_is_noop() -> None:
    assert configure_tracing({}) is None
    assert configure_tracing({"OTEL_EXPORTER_OTLP_ENDPOINT": "  "}) is None


def test_endpoint_builds_otlp_provider() -> None:
    provider = configure_tracing({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:9/v1/traces", "OTEL_SERVICE_NAME": "hc-test"})
    assert isinstance(provider, TracerProvider)
    assert provider.resource.attributes["service.name"] == "hc-test"
    processors = provider._active_span_processor._span_processors  # pyright: ignore[reportPrivateUsage]
    assert any(isinstance(p, BatchSpanProcessor) for p in processors)
    provider.shutdown()


def test_default_service_name() -> None:
    provider = configure_tracing({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:9/v1/traces"})
    assert provider is not None
    assert provider.resource.attributes["service.name"] == DEFAULT_SERVICE_NAME
    provider.shutdown()


def test_headers_from_file(tmp_path: Path) -> None:
    from harness_catalog_server.telemetry import headers_from_file

    assert headers_from_file("") == {}
    assert headers_from_file(str(tmp_path / "missing")) == {}
    f = tmp_path / "otlp_headers"
    f.write_text("Authorization=Basic abc==, X-Extra = v \n")
    assert headers_from_file(str(f)) == {"Authorization": "Basic abc==", "X-Extra": "v"}
    f.write_text("\n")
    assert headers_from_file(str(f)) == {}
