"""Resolve Объектив (lens) photo paths for client-side viewing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

DEFAULT_WINDOWS_ROOT = r"X:\Common\Объектив"
PHOTO_TABLE_CANDIDATES = ("report_photos", "reports_photos")
_UPLOADS_PREFIX_RE = re.compile(r"^(uploads[/\\])+", re.IGNORECASE)
_WINDOWS_DRIVE_RE = re.compile(r"^[a-zA-Z]:")
_photo_table_name: str | None = None


@dataclass
class LensPhotoItem:
    id: int
    file_path: str
    relative_path: str
    windows_path: str
    file_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file_path": self.file_path,
            "relative_path": self.relative_path,
            "windows_path": self.windows_path,
            "file_name": self.file_name,
        }


@dataclass
class LensPhotosResult:
    external_report_id: str
    photos: list[LensPhotoItem]

    def to_dict(self) -> dict[str, Any]:
        return {
            "external_report_id": self.external_report_id,
            "photos": [photo.to_dict() for photo in self.photos],
        }


def normalize_lens_relative_path(file_path: str) -> str | None:
    """Strip a leading uploads/ prefix and reject unsafe paths."""
    text = (file_path or "").strip().replace("\\", "/")
    text = text.lstrip("/")
    text = _UPLOADS_PREFIX_RE.sub("", text)
    text = text.lstrip("/")
    if not text:
        return None
    if _WINDOWS_DRIVE_RE.match(text) or text.startswith("//"):
        return None
    parts = [part for part in text.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        return None
    return "/".join(parts)


def join_windows_path(root: str, relative_path: str) -> str:
    root_win = (root or DEFAULT_WINDOWS_ROOT).replace("/", "\\").rstrip("\\")
    tail = relative_path.replace("/", "\\")
    return f"{root_win}\\{tail}"


def build_lens_photo_item(
    photo_id: int,
    file_path: str,
    *,
    windows_root: str = DEFAULT_WINDOWS_ROOT,
) -> LensPhotoItem | None:
    relative = normalize_lens_relative_path(file_path)
    if relative is None:
        return None
    return LensPhotoItem(
        id=photo_id,
        file_path=file_path,
        relative_path=relative,
        windows_path=join_windows_path(windows_root, relative),
        file_name=relative.rsplit("/", 1)[-1],
    )


def resolve_lens_photo_table(conn: PgConnection) -> str:
    global _photo_table_name
    if _photo_table_name:
        return _photo_table_name
    query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'lens'
          AND table_name = ANY(%s)
        ORDER BY CASE table_name
            WHEN 'report_photos' THEN 0
            ELSE 1
        END
        LIMIT 1
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (list(PHOTO_TABLE_CANDIDATES),))
        row = cur.fetchone()
    if not row or not row.get("table_name"):
        _photo_table_name = PHOTO_TABLE_CANDIDATES[0]
    else:
        _photo_table_name = str(row["table_name"])
    return _photo_table_name


def reset_lens_photo_table_cache() -> None:
    global _photo_table_name
    _photo_table_name = None


def resolve_lens_photos(
    conn: PgConnection,
    external_report_id: str,
    *,
    windows_root: str = DEFAULT_WINDOWS_ROOT,
    photo_table: str | None = None,
) -> LensPhotosResult:
    report_id = (external_report_id or "").strip()
    photos: list[LensPhotoItem] = []
    if not report_id:
        return LensPhotosResult(external_report_id=report_id, photos=photos)

    table = photo_table or resolve_lens_photo_table(conn)
    if table not in PHOTO_TABLE_CANDIDATES:
        table = PHOTO_TABLE_CANDIDATES[0]

    query = f"""
        SELECT p.id, p.file_path
        FROM lens.reports r
        JOIN lens.{table} p ON p.report_id = r.id
        WHERE r.external_report_id = %s
        ORDER BY p.id
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (report_id,))
        rows = cur.fetchall()

    for row in rows:
        raw_path = row.get("file_path")
        if raw_path is None:
            continue
        item = build_lens_photo_item(
            int(row["id"]),
            str(raw_path),
            windows_root=windows_root,
        )
        if item is not None:
            photos.append(item)

    return LensPhotosResult(external_report_id=report_id, photos=photos)
