"""검색 — 메모리 사본 위의 BM25 + dense 볼록 결합 (§11 2026-10-19 검색 0.8.0, 정본은 plans/search.md §3).

순수 함수·순수 자료구조만 있다. Postgres 도 임베딩 서비스도 모른다. 벡터는 호출자가 준다(없으면 BM25 만).
  - 토크나이저: 소문자 낱말 + 한글 구간의 글자 2-gram(형태소 분석기 없이 활용·조사를 어느 정도 잇는다; Kiwi 는 실측에서 이득 없었다).
  - BM25(k1 1.5, b 0.75, Lucene 식 idf log(1 + (n−df+0.5)/(df+0.5)) — 작은 카탈로그에서도 0 이 되지 않는다).
  - dense 는 정규화된 벡터의 코사인. 결합은 질의마다 min-max 정규화한 두 점수의 볼록 결합 α·dense + (1−α)·bm25, α 는 상수 0.85
    (영역 holdout 에서 고른 값, 0.7~0.95 평평 — 설정으로 열지 않는다).
벤치(로컬 bench/search)의 같은 질의로 R@3 0.982 가 기대값이다.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import TYPE_CHECKING, Final

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from numpy.typing import NDArray

ALPHA: Final = 0.85
K1: Final = 1.5
B: Final = 0.75
# ast-grep-ignore: regex-on-structure — 어휘: 문자 집합(한글·라틴·숫자·구분 문장부호)으로 낱말 경계를 자르는 토크나이저이지 중첩 구조가 아니다
_HANGUL = re.compile(r"[가-힣]+")
# ast-grep-ignore: regex-on-structure — 어휘: 문자 집합(한글·라틴·숫자·구분 문장부호)으로 낱말 경계를 자르는 토크나이저이지 중첩 구조가 아니다
_WORD = re.compile(r"[0-9a-zA-Z가-힣_+#]+(?:[.-][0-9a-zA-Z가-힣_+#]+)*")  # 안쪽의 . - 는 붙이고(conversations.history, yt-dlp) 끝의 문장부호는 뗀다


def _pieces(w: str) -> list[str]:
    """구분 문장부호(- _ .)로 쪼갠 조각들. 빈 조각은 버린다."""
    # ast-grep-ignore: regex-on-structure — 어휘: 문자 집합(한글·라틴·숫자·구분 문장부호)으로 낱말 경계를 자르는 토크나이저이지 중첩 구조가 아니다
    return [p for p in re.split(r"[-_.]", w) if p]


def _mixed_script(w: str) -> list[str]:
    """한글과 라틴·숫자가 한 낱말에 섞였을 때의 추가 토큰: 한글 아닌 구간과 그 조각들, 그리고 한글 구간들.

    "yt-dlp을" → yt-dlp, yt, dlp, 을 ; "renovate을" → renovate, 을
    """
    out: list[str] = []
    # ast-grep-ignore: regex-on-structure — 어휘: 문자 집합(한글·라틴·숫자·구분 문장부호)으로 낱말 경계를 자르는 토크나이저이지 중첩 구조가 아니다
    for raw in re.findall(r"[^가-힣]+", w):
        run = raw.strip(".-_")
        if run:
            out.append(run)
            out.extend(p for p in _pieces(run) if p != run)
    out.extend(_HANGUL.findall(w))
    return out


def _bigrams(w: str) -> list[str]:
    """한글 구간마다 글자 2-gram(형태소 분석기 없이 활용·조사를 어느 정도 잇는다)."""
    out: list[str] = []
    for run in _HANGUL.findall(w):
        if len(run) >= 2:
            out.extend(run[i : i + 2] for i in range(len(run) - 1))
    return out


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for w in _WORD.findall(text.lower()):
        out.append(w)
        if "-" in w or "_" in w or "." in w:
            out.extend(_pieces(w))
        # ast-grep-ignore: regex-on-structure — 어휘: 문자 집합(한글·라틴·숫자·구분 문장부호)으로 낱말 경계를 자르는 토크나이저이지 중첩 구조가 아니다
        if _HANGUL.search(w) and re.search(r"[0-9a-z]", w):
            out.extend(_mixed_script(w))
        out.extend(_bigrams(w))
    return out


def index_document(name: str, description: str, metadata: Iterable[str] = ()) -> str:
    """색인 문서 = 이름 + description + metadata 값. 발동 낱말은 description 안에 있다(저자 규약). 이 형식이 바뀌면 임베딩 세대 이름도 바꾼다(DOC_FORMAT)."""
    values = " ".join(sorted(metadata))
    return f"{name}: {description} {values}".strip()


DOC_FORMAT: Final = "doc1"  # 색인 문서 형식의 판. `embedding_model` 열에 "<모델>/<판>" 으로 함께 적혀 세대를 가른다


def embedding_generation(model: str) -> str:
    return f"{model}/{DOC_FORMAT}"


class Bm25:
    """문서 집합 하나의 BM25Okapi. scores() 는 모든 문서의 점수(결합용)."""

    def __init__(self, docs: Sequence[Sequence[str]]) -> None:
        self.n = len(docs)
        self.doc_len = [len(d) for d in docs]
        self.avgdl = (sum(self.doc_len) / self.n) if self.n else 0.0
        self.tf: list[Counter[str]] = [Counter(d) for d in docs]
        df: Counter[str] = Counter()
        for d in self.tf:
            df.update(d.keys())
        # Lucene 식 idf: log(1 + (n − df + 0.5)/(df + 0.5)) — 항상 양수. 원식(log((n−df+0.5)/(df+0.5)))은 문서가 둘뿐인 카탈로그에서
        # 한 문서에만 나온 낱말의 idf 가 0 이 되어 검색이 비는다(실측: 지금 카탈로그는 스킬 셋·도구 다섯).
        self.idf = {t: math.log(1.0 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: Sequence[str]) -> NDArray[np.float32]:
        out = np.zeros(self.n, dtype=np.float32)
        if not self.n:
            return out
        for t in query:
            w = self.idf.get(t)
            if w is None:
                continue
            for i, tf in enumerate(self.tf):
                f = tf.get(t)
                if f:
                    out[i] += w * f * (K1 + 1) / (f + K1 * (1 - B + B * self.doc_len[i] / self.avgdl))
        return out


def _minmax(x: NDArray[np.float32]) -> NDArray[np.float32]:
    lo, hi = float(x.min()), float(x.max())
    return np.zeros_like(x) if hi - lo < 1e-9 else (x - lo) / (hi - lo)


def _complete(rows: list[list[float]], count: int, given: int) -> bool:
    """벡터가 문서마다 하나씩 다 있고, 차원이 서로 같고, 0 차원이 아닌가."""
    return len(rows) == count == given and len({len(r) for r in rows}) == 1 and bool(rows[0])


def _document_matrix(count: int, vectors: Sequence[Sequence[float] | None] | None) -> NDArray[np.float32] | None:
    """문서 벡터 행렬(행마다 정규화). 벡터는 전부 있고, 차원이 같고 0 이 아니며, 유한해야 dense —
    아니면(저장분이 깨졌거나 세대가 섞임) None 이고 색인은 BM25 만으로 돈다. Codex 2026-10-19 #2"""
    if not count or vectors is None:
        return None
    rows = [list(v) for v in vectors if v is not None]
    if not _complete(rows, count, len(vectors)):
        return None
    m = np.asarray(rows, dtype=np.float32)
    if not bool(np.isfinite(m).all()):
        return None
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return (m / np.where(norms == 0, 1.0, norms)).astype(np.float32)


class SearchIndex:
    """한 종류(스킬 또는 도구)의 검색 색인. 이름 순서가 고정되고 벡터는 그 순서의 행렬(없으면 None)."""

    def __init__(self, names: Sequence[str], docs: Sequence[str], vectors: Sequence[Sequence[float] | None] | None = None) -> None:
        self.names = tuple(names)
        self.bm25 = Bm25([tokenize(d) for d in docs])
        self.vectors: NDArray[np.float32] | None = _document_matrix(len(self.names), vectors)

    @property
    def dense(self) -> bool:
        return self.vectors is not None

    def _query_vector(self, v: Sequence[float] | None) -> NDArray[np.float32] | None:
        """문서 벡터와 차원이 같고 유한하며 0 이 아닌 질의 벡터만 쓴다(아니면 BM25 만). 정규화해 돌려준다."""
        if v is None or self.vectors is None:
            return None
        q = np.asarray(list(v), dtype=np.float32)
        if q.ndim != 1 or q.shape[0] != self.vectors.shape[1] or not bool(np.isfinite(q).all()):
            return None
        qn = float(np.linalg.norm(q))
        return (q / qn).astype(np.float32) if qn else None

    def search(self, query: str, query_vector: Sequence[float] | None, limit: int) -> tuple[str, ...]:
        """점수 순 이름. 벡터가 양쪽에 있으면 볼록 결합(dense 는 언제나 상위 limit 을 낸다 — 동의어 구조가 그것), 아니면 BM25 만(점수 0 은 뺀다). 빈 질의는 빈 결과."""
        if not self.names or not query.strip():
            return ()
        bm = self.bm25.scores(tokenize(query))
        q = self._query_vector(query_vector)
        if self.vectors is not None and q is not None:
            cos = self.vectors @ q
            fused = ALPHA * _minmax(cos.astype(np.float32)) + (1 - ALPHA) * _minmax(bm)
            order = [int(i) for i in np.lexsort((np.asarray(self.names), -fused))]  # 점수 내림차, 같으면 이름 오름차
            return tuple(self.names[i] for i in order[:limit])
        order = [int(i) for i in np.lexsort((np.asarray(self.names), -bm))]
        return tuple(self.names[i] for i in order[:limit] if bm[i] > 0)
