"""설정값 여섯 — 정의의 유일한 자리. 환경 변수 HC__<이름>, 비밀은 HC__<이름>_FILE로 파일 경로도 받는다."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

ENV_PREFIX = "HC__"


class _FileEnvSource(PydanticBaseSettingsSource):
    """HC__<NAME>_FILE=<경로>이면 그 파일의 내용을 값으로 쓴다(docker secrets 관례)."""

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:  # noqa: ARG002 — 기반 클래스의 시그니처
        var = f"{ENV_PREFIX}{field_name.upper()}_FILE"
        path = os.environ.get(var)
        if not path:
            return None, field_name, False
        return Path(path).read_text().rstrip("\n"), field_name, False

    # ast-grep-ignore: dict-payload-return — 기반 클래스(PydanticBaseSettingsSource)가 dict 반환을 요구한다
    def __call__(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for name, field in self.settings_cls.model_fields.items():
            value, _, _ = self.get_field_value(field, name)
            if value is not None:
                values[name] = value
        return values


class Settings(BaseSettings):
    """필수 다섯 + 기본값 있는 셋(fetch 간격, 임베딩 서비스 주소·모델). 비면 기동 실패(어느 것이 비었는지 pydantic이 말한다)."""

    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, env_nested_delimiter="__", extra="ignore")

    catalog_repo_url: str = Field(description="카탈로그 git 저장소 URL (deploy key로 fetch만 한다)")
    git_deploy_key: SecretStr = Field(description="읽기 전용 deploy key의 개인 키(PEM). 로컬 file:// 저장소면 빈 문자열")
    oidc_issuer: AnyHttpUrl = Field(description="OIDC issuer URL (토큰의 iss, JWKS 발견)")
    public_url: AnyHttpUrl = Field(description="레지스트리 공개 URL = 토큰의 audience = RFC 9728 resource")
    database_url: SecretStr = Field(description="PostgreSQL 접속 문자열")
    fetch_interval_seconds: int = Field(default=60, ge=1, description="주기 fetch 간격(초)")
    embed_url: str = Field(default="", description="임베딩 서비스 주소(외부 서비스 — Ollama `…/api/embed` 또는 TEI `…/embed`). 비면 BM25 만(§11 2026-10-19 검색 0.8.0)")
    embed_model: str = Field(default="hf.co/mykor/KURE-v1-gguf:BF16", description="임베딩 모델 이름(Ollama 요청에 실리고 벡터 세대 키가 된다)")

    @field_validator("oidc_issuer", "public_url", mode="before")
    @classmethod
    def _no_trailing_slash(cls, v: object) -> object:
        """issuer·공개 URL은 Dex(issuer·audience 클라이언트 id)와 레지스트리(iss·aud 검증, PRM resource)가 글자까지 같은 값을 봐야 한다.
        끝 슬래시는 그 둘을 조용히 갈라놓으므로 입력 단계에서 거부한다(Codex 리뷰 2026-10-10)."""
        if isinstance(v, str) and v.rstrip().endswith("/"):
            raise ValueError("must not end with '/' (Dex and the registry must see one identical string)")
        return v

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, _FileEnvSource(settings_cls), dotenv_settings, file_secret_settings)
