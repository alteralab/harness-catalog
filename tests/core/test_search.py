"""search.py — 토크나이저·BM25·볼록 결합의 성질(§11 2026-10-19 검색 0.8.0). Postgres 도 모델도 없다; 벡터는 손으로 준다."""

from __future__ import annotations

from harness_catalog_core.search import (
    ALPHA,
    Bm25,
    SearchIndex,
    embedding_generation,
    index_document,
    tokenize,
)


def test_tokenize_korean_bigrams_identifiers_and_mixed_tokens() -> None:
    toks = tokenize("자막 추출해줘. yt-dlp을 쓴다. conversations.history renovate을")
    assert "자막" in toks and "추출" in toks and "출해" in toks  # 한글 2-gram 이 활용형을 잇는다
    assert "yt-dlp" in toks and "yt" in toks and "dlp" in toks  # 식별자는 통째로도, 조각으로도
    assert "conversations.history" in toks and "history" in toks
    assert "renovate" in toks and "을" in toks  # 라틴+한글 붙은 토큰 분리
    assert tokenize("") == []


def test_bm25_prefers_rarer_matching_term_and_zero_for_no_overlap() -> None:
    docs = [tokenize(d) for d in ("youtube 자막을 추출한다", "youtube 댓글을 요약한다", "git 커밋을 정리한다")]
    bm = Bm25(docs)
    s = bm.scores(tokenize("자막"))
    assert s[0] > 0 and s[1] == 0 and s[2] == 0
    s2 = bm.scores(tokenize("youtube"))  # 셋 중 둘에 나오는 낱말 — 둘 다 양수, 셋째는 0
    assert s2[0] > 0 and s2[1] > 0 and s2[2] == 0
    assert list(Bm25([]).scores(["x"])) == []


def test_index_document_and_generation_name() -> None:
    assert index_document("yt-subs", "유튜브 자막을 추출한다.", ["ko", "video"]) == "yt-subs: 유튜브 자막을 추출한다. ko video"
    assert embedding_generation("hf.co/x:BF16") == "hf.co/x:BF16/doc1"


def test_bm25_only_search_orders_by_score_and_drops_zero() -> None:
    ix = SearchIndex(["a", "b", "c"], ["youtube 자막을 추출한다", "youtube 댓글을 요약한다", "git 커밋을 정리한다"])
    assert not ix.dense
    assert ix.search("자막 추출해줘", None, 10) == ("a",)  # 점수 0 인 b·c 는 빠진다
    assert ix.search("youtube", None, 10) == ("a", "b")  # 같은 점수면 이름 순
    assert ix.search("없는낱말", None, 10) == ()
    assert ix.search("youtube", None, 1) == ("a",)


def test_dense_rescues_synonym_and_bm25_rescues_identifier() -> None:
    # 세 문서, 2차원 벡터로 뜻을 흉내낸다: a=자막(1,0), b=댓글(0,1), c=커밋(−1,0)
    ix = SearchIndex(["a", "b", "c"], ["youtube 자막을 추출한다 yt-dlp", "youtube 댓글을 요약한다", "git 커밋을 정리한다"], [(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0)])
    assert ix.dense
    # 동의어 질의("캡션")는 BM25 로 0 이지만 질의 벡터가 a 쪽이면 a 가 1등
    assert ix.search("캡션 가져와", (0.9, 0.1), 3)[0] == "a"
    # 식별자 질의: 벡터는 b 쪽을 가리켜도 BM25 의 yt-dlp 일치가 a 를 끌어올린다(결합 α=0.85 에서 dense 1위 b, bm25 1위 a → 둘 다 상위)
    got = ix.search("yt-dlp", (0.0, 1.0), 3)
    assert set(got[:2]) == {"a", "b"}
    assert 0 < ALPHA < 1


def test_vectors_ignored_when_incomplete() -> None:
    ix = SearchIndex(["a", "b"], ["x 하나", "y 둘"], [(1.0, 0.0), None])
    assert not ix.dense  # 한 세대가 통째로 있어야 dense — 아니면 BM25 만
    assert ix.search("하나", (1.0, 0.0), 2) == ("a",)


def test_empty_query_and_bad_query_vector_fall_back_safely() -> None:
    """Codex 2026-10-19 #2·#4: 빈 질의는 빈 결과, 차원이 다르거나 0·NaN 인 질의 벡터는 BM25 만."""
    ix = SearchIndex(["a", "b"], ["x 하나", "y 둘"], [(1.0, 0.0), (0.0, 1.0)])
    assert ix.dense
    assert ix.search("", (1.0, 0.0), 2) == () and ix.search("   ", (1.0, 0.0), 2) == ()
    assert ix.search("둘", (1.0, 0.0, 0.0), 2) == ("b",)  # 차원 불일치 → BM25
    assert ix.search("둘", (0.0, 0.0), 2) == ("b",)  # 0 벡터 → BM25
    assert ix.search("둘", (float("nan"), 1.0), 2) == ("b",)


def test_malformed_stored_vectors_disable_dense() -> None:
    assert not SearchIndex(["a", "b"], ["x", "y"], [(1.0, 0.0), (1.0,)]).dense  # 차원 제각각
    assert not SearchIndex(["a", "b"], ["x", "y"], [(1.0, float("inf")), (0.0, 1.0)]).dense
    assert not SearchIndex(["a"], ["x"], [()]).dense
