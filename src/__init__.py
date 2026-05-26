"""Typed application configuration loaded from ``config/config.yaml``.

Living at the package root makes :func:`get_config` accessible as
``from . import get_config`` from any sibling module. The shape mirrors
the YAML sections one-to-one (``app``, ``cors``, ``frontend``,
``artifacts``, ``catalog``) — those section models live in :mod:`.model`
alongside the rest of the Pydantic data shapes. Environment variables
override nested fields with a double-underscore delimiter, e.g.
``APP__PORT=9000`` or ``ARTIFACTS__DIR=/data/artifacts``.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from src.model import ROOT, App, Artifacts, Catalog, Cors, Frontend


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        env_nested_delimiter="__",
        env_nested_max_split=1,
    )

    config_path: ClassVar[Path] = ROOT / "config" / "config.yaml"

    app: App
    cors: Cors
    frontend: Frontend
    artifacts: Artifacts
    catalog: Catalog

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=cls.config_path),
        )


__config__: Config | None = None


def get_config() -> Config:
    global __config__
    if __config__ is None:
        __config__ = Config()
    return __config__
