"""임베딩 어댑터(Embedder 포트) — 모델이 있는 머신의 HTTP 서비스를 부른다(§11 2026-10-19 검색 0.8.0, plans/search.md §3).

두 요청 모양을 안다. URL 경로로 가른다:
  - `…/api/embed` → Ollama(mini 호스트 앱, Metal): {"model", "input": [...], "truncate": true} → {"embeddings": [[...]]}
  - 그 밖(`…/embed`)  → text-embeddings-inference: {"inputs": [...], "normalize": true} → [[...]]
닿지 않거나 모양이 다르면 None — 앱이 BM25 만으로 깎아 답한다. 벡터는 여기서 한 번 더 정규화한다(코사인 = 내적).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from typing import Any, Final, cast

import httpx

from harness_catalog_core.search import embedding_generation

log = logging.getLogger(__name__)
CONNECT_SECONDS: Final = 3.0  # 연결만 짧게 — 질의 임베딩 호출이 죽은 서비스에 매달리지 않게
TIMEOUT_SECONDS: Final = 120.0  # 색인 때 수백 문서를 한 번에 보낸다(mini Ollama: 720 문서 15 s)
BATCH: Final = 64


class HttpEmbedder:
    def __init__(self, url: str, model: str, *, timeout: float = TIMEOUT_SECONDS) -> None:
        self._url = url.rstrip("/")
        self._model = model
        self._ollama = self._url.endswith("/api/embed")
        self._client = httpx.Client(timeout=httpx.Timeout(timeout, connect=CONNECT_SECONDS))  # 서비스가 죽어 있으면 연결에서 바로 실패해 검색 한 번이 색인 timeout 만큼 매달리지 않는다

    @property
    def generation(self) -> str:
        return embedding_generation(self._model)

    def embed(self, texts: Sequence[str], /) -> list[list[float]] | None:
        out: list[list[float]] = []
        for i in range(0, len(texts), BATCH):
            chunk = list(texts[i : i + BATCH])
            got = self._one(chunk)
            if got is None or len(got) != len(chunk) or (out and len(got[0]) != len(out[0])):
                return None  # 한 배치라도 틀리면 전부 없음 — 세대가 섞이지 않게
            out.extend(got)
        return out

    def _one(self, texts: list[str]) -> list[list[float]] | None:
        body: dict[str, Any] = {"model": self._model, "input": texts, "truncate": True} if self._ollama else {"inputs": texts, "normalize": True}
        try:
            r = self._client.post(self._url, json=body)
            r.raise_for_status()
            raw = r.json()
            rows = cast(list[list[float]], raw["embeddings"] if self._ollama else raw)
            vecs = [[float(x) for x in row] for row in rows]
            # HTTP 200 의 깨진 본문도 실패다: 빈 벡터, 행마다 다른 차원, NaN/Inf, 0 벡터(Codex 2026-10-19 #2)
            if vecs and any(not v or len(v) != len(vecs[0]) or not all(math.isfinite(x) for x in v) or not any(v) for v in vecs):
                raise ValueError("malformed embedding payload")
            return [_normalize(v) for v in vecs]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
            log.warning("embed failed (%s): %s", self._url, e)
            return None


def _normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v
