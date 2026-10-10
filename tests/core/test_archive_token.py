"""아카이브 토큰: 발급·검증·만료·변조·형식·키 교체."""

from __future__ import annotations

import pytest

from harness_catalog_core.archive_token import ArchiveSigner

KEY = b"k" * 32
NAME, TREE = "yt-subs", "a" * 40


def test_mint_then_verify_within_ttl() -> None:
    t = [1_000_000]
    s = ArchiveSigner(KEY, ttl_seconds=300, clock=lambda: t[0])
    token, exp = s.mint(NAME, TREE)
    assert exp == 1_000_300 and token.startswith("v1.1000300.") and "?" not in token
    assert s.verify(NAME, TREE, token)
    t[0] = 1_000_299
    assert s.verify(NAME, TREE, token)  # TTL 안 재생은 허용(멱등 읽기)
    t[0] = 1_000_300
    assert not s.verify(NAME, TREE, token)  # exp 자체는 만료


def test_rejects_tamper_other_target_far_future_and_malformed() -> None:
    t = [1_000_000]
    s = ArchiveSigner(KEY, ttl_seconds=300, clock=lambda: t[0])
    token, _ = s.mint(NAME, TREE)
    assert not s.verify("other", TREE, token) and not s.verify(NAME, "b" * 40, token)
    head, _, sig = token.rpartition(".")
    assert not s.verify(NAME, TREE, head + "." + ("A" if sig[0] != "A" else "B") + sig[1:])  # 서명 변조
    assert not s.verify(NAME, TREE, f"v1.{1_000_900}.{sig}")  # 만료 연장 시도(서명 범위에 exp)
    far = ArchiveSigner(KEY, ttl_seconds=300, clock=lambda: 1_000_000)
    forged, _ = ArchiveSigner(KEY, ttl_seconds=99_999, clock=lambda: 1_000_000).mint(NAME, TREE)
    assert not far.verify(NAME, TREE, forged)  # 같은 키라도 창(ttl+leeway)을 넘는 exp는 거부
    for bad in (None, "", "v2." + token[3:], token + "=", token.replace(".", ",", 1), "v1.abc." + sig, "v1.1000300." + sig[:-1]):
        assert not s.verify(NAME, TREE, bad)
    assert not s.verify("Bad_Name", TREE, token) and not s.verify(NAME, "zz", token)


def test_other_key_or_restart_invalidates() -> None:
    a = ArchiveSigner(b"a" * 32, clock=lambda: 10)
    b = ArchiveSigner(b"b" * 32, clock=lambda: 10)
    token, _ = a.mint(NAME, TREE)
    assert a.verify(NAME, TREE, token) and not b.verify(NAME, TREE, token)
    with pytest.raises(ValueError):
        ArchiveSigner(b"short")
    with pytest.raises(ValueError):
        a.mint("Bad Name", TREE)
