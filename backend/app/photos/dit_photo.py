"""Resolve DIT AI photos from dit_detect.ai_results."""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.photos.ai_photo import PHOTO_FETCH_TIMEOUT_SEC, PhotoFetchError, normalize_bboxes

ALLOWED_IMAGE_SCHEMES = {"http", "https"}


@dataclass
class DitPhotoMeta:
    result_id: str
    image_url: str
    image_name: str
    bboxes: list[Any] = field(default_factory=list)

    def to_dict(self, proxy_url: str) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "image": self.image_url,
            "image_name": self.image_name,
            "bboxes": self.bboxes,
            "url": proxy_url,
        }


def normalize_result_id(value: str) -> str | None:
    result_id = value.strip()
    if not result_id or "/" in result_id or "\\" in result_id or ".." in result_id:
        return None
    return result_id


def image_name_from_url(url: str) -> str:
    path = urlparse(url).path
    name = Path(path).name.strip()
    return name or "photo.jpg"


def issues_to_bboxes(raw: Any) -> list[Any]:
    bboxes = normalize_bboxes(raw)
    if bboxes:
        return bboxes
    if isinstance(raw, dict):
        nested = raw.get("issues")
        if isinstance(nested, list):
            return list(nested)
    return []


def is_http_image_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    return parsed.scheme.lower() in ALLOWED_IMAGE_SCHEMES and bool(parsed.netloc)


def resolve_dit_photo(conn: PgConnection, result_id: str) -> DitPhotoMeta | None:
    normalized = normalize_result_id(result_id)
    if normalized is None:
        return None
    query = """
        SELECT result_id, image, issues
        FROM dit_detect.ai_results
        WHERE result_id::text = %s
        LIMIT 1
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (normalized,))
        row = cur.fetchone()
    if not row:
        return None
    image = str(row.get("image") or "").strip()
    if not image:
        return None
    return DitPhotoMeta(
        result_id=str(row["result_id"]),
        image_url=image,
        image_name=image_name_from_url(image),
        bboxes=issues_to_bboxes(row.get("issues")),
    )


def fetch_dit_photo_bytes(meta: DitPhotoMeta) -> tuple[bytes, str]:
    if not is_http_image_url(meta.image_url):
        raise PhotoFetchError(400, "DIT photo URL must be http or https")
    request = urllib.request.Request(meta.image_url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=PHOTO_FETCH_TIMEOUT_SEC) as response:
            content = response.read()
            media_type = response.headers.get("Content-Type", "image/jpeg")
            if ";" in media_type:
                media_type = media_type.split(";", 1)[0].strip()
            return content, media_type or "image/jpeg"
    except urllib.error.HTTPError as exc:
        raise PhotoFetchError(exc.code, f"Remote DIT photo HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise PhotoFetchError(502, f"Remote DIT photo unreachable: {exc.reason}") from exc
