"""Application settings."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "monitor"
    db_user: str = "monitor"
    db_password: str = ""
    layers_config_path: str = "../shared/layers_config.json"
    cors_origins: str = "http://localhost:5173"
    geojson_default_limit: int = 2000
    photo_storage_dir: str = "/opt/monitor/downloaded_photo"
    """Local directory with photo files (used on VPS)."""
    photo_proxy_base_url: str = ""
    """Remote API base, e.g. http://77.222.63.161:8080 — image fetched via its /api/photos/ai/{uuid}/image."""
    photo_static_base_url: str = ""
    """Optional direct URL prefix for files, e.g. http://host/photos — uses {base}/{image_name}."""
    photo_sftp_enabled: bool = True
    photo_sftp_host: str = ""
    photo_sftp_port: int = 22
    photo_sftp_user: str = ""
    photo_sftp_password: str = ""
    photo_sftp_key_path: str = ""
    photo_sftp_remote_dir: str = "/opt/monitor/downloaded_photo"
    photo_local_cache_dir: str = "./data/photo_cache"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def resolved_config_path(self) -> Path:
        path = Path(self.layers_config_path)
        if path.is_absolute():
            return path
        backend_dir = Path(__file__).resolve().parent.parent
        return (backend_dir / path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def load_layers_config() -> dict[str, Any]:
    path = get_settings().resolved_config_path()
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def crm_tasks_config() -> dict[str, Any]:
    return load_layers_config().get("crm_tasks", {})


def crm_task_store_config() -> dict[str, Any]:
    return crm_tasks_config().get("task_store", {})
