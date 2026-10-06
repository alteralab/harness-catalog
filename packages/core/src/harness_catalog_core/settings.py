"""설정값 여섯 — 정의의 유일한 자리. 환경 변수 HC__<이름>, 비밀은 HC__<이름>_FILE로 파일 경로도 받는다."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import AnyHttpUrl, Field, SecretStr
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
    """필수 다섯 + 기본값 있는 하나. 비면 기동 실패(어느 것이 비었는지 pydantic이 말한다)."""

    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, env_nested_delimiter="__", extra="ignore")

    catalog_repo_url: str = Field(description="카탈로그 git 저장소 URL (deploy key로 fetch만 한다)")
    git_deploy_key: SecretStr = Field(description="읽기 전용 deploy key의 개인 키(PEM). 로컬 file:// 저장소면 빈 문자열")
    oidc_issuer: AnyHttpUrl = Field(description="OIDC issuer URL (토큰의 iss, JWKS 발견)")
    public_url: AnyHttpUrl = Field(description="레지스트리 공개 URL = 토큰의 audience = RFC 9728 resource")
    database_url: SecretStr = Field(description="PostgreSQL 접속 문자열")
    fetch_interval_seconds: int = Field(default=60, ge=1, description="주기 fetch 간격(초)")

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
