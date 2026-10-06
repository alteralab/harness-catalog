"""표지 파일 `.harness-catalog`의 파서. 내용은 TOML 한 줄(layout = 1)."""

from __future__ import annotations

import tomllib
from typing import NamedTuple

MARKER_PATH = ".harness-catalog"


class Marker(NamedTuple):
    layout: int


class MarkerError(ValueError):
    """표지가 TOML이 아니거나 layout이 없다."""


def parse_marker(text: str) -> Marker:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise MarkerError(f"not TOML: {e}") from e
    layout = data.get("layout")
    if not isinstance(layout, int) or isinstance(layout, bool):
        raise MarkerError("layout must be an integer")
    return Marker(layout)


def render_marker(layout: int) -> str:
    return f"layout = {layout}\n"
