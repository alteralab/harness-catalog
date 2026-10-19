"""`config list`(실효값·출처)와 `config docs`(설정값 참조 문서 생성). 설정 정의는 core.settings 한 곳."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, NamedTuple

from harness_catalog_core.settings import ENV_PREFIX, Settings
from pydantic import SecretStr

if TYPE_CHECKING:
    from pydantic_settings import BaseSettings


class EffectiveValue(NamedTuple):
    name: str  # 환경 변수 이름
    source: str  # env | file | default | missing
    value: str  # 비밀은 가린다
    description: str


def effective_values() -> tuple[EffectiveValue, ...]:
    """설정값마다 어디서 왔는지. 기동하지 않고도 본다(필수가 비면 missing)."""
    out: list[EffectiveValue] = []
    for field_name, field in Settings.model_fields.items():
        env = f"{ENV_PREFIX}{field_name.upper()}"
        secret = field.annotation is SecretStr
        if env in os.environ:
            source, raw = "env", os.environ[env]
        elif f"{env}_FILE" in os.environ:
            source, raw = "file", os.environ[f"{env}_FILE"]
        elif field.is_required():
            source, raw = "missing", ""
        else:
            source, raw = "default", str(field.default)
        shown = "********" if secret and source == "env" and raw else raw
        out.append(EffectiveValue(env, source, shown, field.description or ""))
    return tuple(out)


GENERATED_BEGIN = "<!-- generated: harness-catalog config docs — 이 표만 생성된다. 바깥은 손으로 쓴다 -->"
GENERATED_END = "<!-- /generated -->"


def render_docs(settings_cls: type[BaseSettings] = Settings) -> str:
    """docs/configuration.md의 생성 구역: 레지스트리 설정값 표 하나(표식 포함)."""
    lines = [GENERATED_BEGIN, "", "| 변수 | 필수 | 기본값 | 뜻 |", "|---|---|---|---|"]
    for field_name, field in settings_cls.model_fields.items():
        env = f"{ENV_PREFIX}{field_name.upper()}"
        required = "예" if field.is_required() else "아니오"
        default = "" if field.is_required() else str(field.default)
        lines.append(f"| `{env}` | {required} | {default} | {field.description or ''} |")
    lines += ["", GENERATED_END]
    return "\n".join(lines) + "\n"


def merge_docs(existing: str | None, generated: str) -> str:
    """손으로 쓴 본문은 두고 표식 사이만 바꾼다. 파일이 없거나 표식이 없으면 제목 + 생성 구역으로 새로 만든다."""
    if existing and GENERATED_BEGIN in existing and GENERATED_END in existing:
        head = existing[: existing.index(GENERATED_BEGIN)]
        tail = existing[existing.index(GENERATED_END) + len(GENERATED_END) :].lstrip("\n")
        return head + generated + ("\n" + tail if tail else "")
    return "# 설정값\n\n레지스트리 프로세스가 읽는 환경 변수. 비밀은 `<이름>_FILE=<경로>`로 파일에서도 읽는다.\n\n" + generated


def render_env_example(settings_cls: type[BaseSettings] = Settings) -> str:
    """.env.example의 레지스트리 절."""
    lines = ["# --- 레지스트리 설정값 (harness-catalog config docs가 만든 절) ---"]
    for field_name, field in settings_cls.model_fields.items():
        env = f"{ENV_PREFIX}{field_name.upper()}"
        default = "" if field.is_required() else str(field.default)
        lines.append(f"# {field.description or ''}")
        lines.append(f"{env}={default}")
    return "\n".join(lines) + "\n"
