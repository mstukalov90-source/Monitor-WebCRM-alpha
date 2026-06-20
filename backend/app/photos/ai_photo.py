"""Resolve AI photo files from genplan.photo_meta."""

from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
PHOTO_FETCH_TIMEOUT_SEC = 60


@dataclass
class AiPhotoMeta:
    uuid: str
    image_name: str
    date: str | None
    azimuth_deg: float | None
    order_id: str | None

    def to_dict(self, image_url: str) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "image_name": self.image_name,
            "date": self.date,
            "azimuth_deg": self.azimuth_deg,
            "order_id": self.order_id,
            "url": image_url,
        }


def is_valid_uuid(value: str) -> bool:
    return bool(UUID_RE.match(value.strip()))


def resolve_ai_photo(conn: PgConnection, uuid: str) -> AiPhotoMeta | None:
    if not is_valid_uuid(uuid):
        return None
    query = """
        SELECT uuid, image_name, date, azimuth_deg, order_id
        FROM genplan.photo_meta
        WHERE uuid = %s
        LIMIT 1
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (uuid.strip(),))
        row = cur.fetchone()
    if not row or not row.get("image_name"):
        return None
    return AiPhotoMeta(
        uuid=str(row["uuid"]),
        image_name=str(row["image_name"]).strip(),
        date=row.get("date"),
        azimuth_deg=row.get("azimuth_deg"),
        order_id=row.get("order_id"),
    )


def photo_file_path(image_name: str, base_dir: Path) -> Path | None:
    name = image_name.strip()
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        return None

    base = base_dir.resolve()
    candidate = (base / name).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def media_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    return "image/jpeg"


def photo_remote_configured(proxy_base_url: str, static_base_url: str) -> bool:
    return bool(proxy_base_url.strip() or static_base_url.strip())


def read_local_photo(image_name: str, base_dir: Path) -> tuple[bytes, str] | None:
    file_path = photo_file_path(image_name, base_dir)
    if file_path is None:
        return None
    return file_path.read_bytes(), media_type_for_path(file_path)


def _http_get_bytes(url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=PHOTO_FETCH_TIMEOUT_SEC) as response:
            content = response.read()
            media_type = response.headers.get("Content-Type", "image/jpeg")
            if ";" in media_type:
                media_type = media_type.split(";", 1)[0].strip()
            return content, media_type or "image/jpeg"
    except urllib.error.HTTPError as exc:
        raise PhotoFetchError(exc.code, f"Remote photo HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise PhotoFetchError(502, f"Remote photo unreachable: {exc.reason}") from exc


class PhotoFetchError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def fetch_remote_photo(
    meta: AiPhotoMeta,
    *,
    proxy_base_url: str,
    static_base_url: str,
) -> tuple[bytes, str]:
    static_base = static_base_url.strip().rstrip("/")
    if static_base:
        url = f"{static_base}/{urllib.parse.quote(meta.image_name)}"
        return _http_get_bytes(url)

    proxy_base = proxy_base_url.strip().rstrip("/")
    if proxy_base:
        url = f"{proxy_base}/api/photos/ai/{urllib.parse.quote(meta.uuid)}/image"
        return _http_get_bytes(url)

    raise PhotoFetchError(404, "Photo file not found on server")


def fetch_photo_bytes(
    meta: AiPhotoMeta,
    *,
    storage_dir: Path,
    proxy_base_url: str = "",
    static_base_url: str = "",
) -> tuple[bytes, str]:
    local = read_local_photo(meta.image_name, storage_dir)
    if local is not None:
        return local
    return fetch_remote_photo(
        meta,
        proxy_base_url=proxy_base_url,
        static_base_url=static_base_url,
    )
