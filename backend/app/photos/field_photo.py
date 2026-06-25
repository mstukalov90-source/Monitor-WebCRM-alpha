"""Resolve field photos from mggt_field.reports + mggt_field.photos."""

from __future__ import annotations

import getpass
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.config import Settings
from app.photos.ai_photo import media_type_for_path, photo_file_path
from app.photos.sftp_fetch import (
    SftpPhotoError,
    _download_via_paramiko,
    _download_via_scp,
    _resolve_identity_file,
    resolved_cache_dir,
    sftp_configured,
)

logger = logging.getLogger(__name__)

BANNER_LABEL = "Фото баннера"
FIELD_PHOTO_CACHE_SUBDIR = "field"


@dataclass
class FieldPhotoItem:
    id: int
    file_path: str
    banner: bool
    created_at: str | None
    photo_key: str | None
    username: str | None

    def to_dict(self, image_url: str) -> dict[str, Any]:
        return {
            "id": self.id,
            "file_path": self.file_path,
            "banner": self.banner,
            "created_at": self.created_at,
            "photo_key": self.photo_key,
            "username": self.username,
            "label": BANNER_LABEL if self.banner else None,
            "image_url": image_url,
        }


@dataclass
class FieldPhotosResult:
    photos: list[FieldPhotoItem]
    banner_missing: bool

    def to_dict(self, image_url_fn) -> dict[str, Any]:
        return {
            "photos": [p.to_dict(image_url_fn(p.file_path)) for p in self.photos],
            "banner_missing": self.banner_missing,
        }


def _field_image_url(file_path: str) -> str:
    from urllib.parse import quote

    name = Path(file_path.strip()).name
    return f"/api/photos/field/{quote(name)}/image"


def _format_created_at(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def fetch_field_photos(conn: PgConnection, task_key: str) -> FieldPhotosResult:
    query = """
        SELECT p.id, p.file_path, p.banner, p.created_at, p.photo_key, p.username
        FROM mggt_field.reports r
        JOIN mggt_field.photos p ON p.task = r.task
        WHERE r.tasks_key = %s::uuid
          AND p.file_path IS NOT NULL
          AND TRIM(p.file_path) <> ''
        ORDER BY p.banner DESC, p.created_at ASC
    """
    photos: list[FieldPhotoItem] = []
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (task_key,))
        for row in cur.fetchall():
            file_path = str(row["file_path"]).strip()
            if not file_path:
                continue
            photos.append(
                FieldPhotoItem(
                    id=int(row["id"]),
                    file_path=Path(file_path).name,
                    banner=bool(row["banner"]),
                    created_at=_format_created_at(row.get("created_at")),
                    photo_key=row.get("photo_key"),
                    username=row.get("username"),
                )
            )
    has_banner = any(p.banner for p in photos)
    return FieldPhotosResult(photos=photos, banner_missing=not has_banner)


def field_photo_storage_dir(settings: Settings) -> Path:
    raw = settings.field_photo_storage_dir.strip() or "/opt/monitor/mggtfield_photo"
    path = Path(raw)
    if not path.is_absolute():
        backend_dir = Path(__file__).resolve().parent.parent.parent
        path = (backend_dir / path).resolve()
    return path


def field_photo_cache_dir(settings: Settings) -> Path:
    base = resolved_cache_dir(settings)
    cache = base / FIELD_PHOTO_CACHE_SUBDIR
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def resolve_field_photo_path(file_name: str, settings: Settings) -> Path | None:
    storage_dir = field_photo_storage_dir(settings)
    cache_dir = field_photo_cache_dir(settings)
    found = photo_file_path(file_name, storage_dir)
    if found is not None:
        return found
    return photo_file_path(file_name, cache_dir)


def ensure_field_photo_cached(file_name: str, settings: Settings) -> Path:
    storage_dir = field_photo_storage_dir(settings)
    cache_dir = field_photo_cache_dir(settings)

    existing = photo_file_path(file_name, storage_dir)
    if existing is not None:
        return existing

    cached = photo_file_path(file_name, cache_dir)
    if cached is not None:
        return cached

    if not sftp_configured(settings):
        raise SftpPhotoError("Файл полевого фото не найден на сервере")

    remote_path = f"{settings.field_photo_sftp_remote_dir.rstrip('/')}/{file_name}"
    host = settings.photo_sftp_host.strip() or settings.db_host
    user = settings.photo_sftp_user.strip()
    password = settings.photo_sftp_password.strip() or None
    identity_file = _resolve_identity_file(settings)
    target = cache_dir / file_name
    scp_user = user or getpass.getuser()

    errors: list[str] = []
    try:
        _download_via_scp(
            host,
            scp_user,
            remote_path,
            target,
            port=settings.photo_sftp_port,
            identity_file=identity_file,
        )
    except SftpPhotoError as exc:
        errors.append(f"scp: {exc}")
        try:
            _download_via_paramiko(
                host,
                scp_user,
                password,
                remote_path,
                target,
                port=settings.photo_sftp_port,
                identity_file=identity_file,
            )
        except Exception as paramiko_exc:
            errors.append(f"sftp: {paramiko_exc}")
            logger.warning("Field photo download failed for %s: %s", file_name, "; ".join(errors))
            raise SftpPhotoError(
                "Не удалось скачать полевое фото с VPS. "
                f"{' | '.join(errors)}"
            ) from paramiko_exc

    cached = photo_file_path(file_name, cache_dir)
    if cached is None:
        raise SftpPhotoError("Скачанный файл не прошёл проверку")
    return cached


def read_field_photo(file_name: str, settings: Settings) -> tuple[Path, str]:
    safe_name = Path(file_name.strip()).name
    local_path = resolve_field_photo_path(safe_name, settings)
    if local_path is None and sftp_configured(settings):
        local_path = ensure_field_photo_cached(safe_name, settings)
    if local_path is None:
        raise SftpPhotoError("Файл полевого фото не найден")
    return local_path, media_type_for_path(local_path)
