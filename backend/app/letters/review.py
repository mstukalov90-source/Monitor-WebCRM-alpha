"""Manager review listing and flags for stored OATI letters."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.letters.oati import LetterError

LetterReviewStatus = Literal["approved", "rejected"]

LETTER_LIST_LIMITS = (20, 50, 100, 200)
DEFAULT_LETTER_LIST_LIMIT = 50

_REVIEW_COLUMNS_SQL = (
    "ALTER TABLE webcrm.oati_letters ADD COLUMN IF NOT EXISTS review_status TEXT",
    "ALTER TABLE webcrm.oati_letters ADD COLUMN IF NOT EXISTS reviewed_by TEXT",
    "ALTER TABLE webcrm.oati_letters ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ",
    "ALTER TABLE webcrm.oati_letters ADD COLUMN IF NOT EXISTS hidden_at TIMESTAMPTZ",
    "ALTER TABLE webcrm.oati_letters ADD COLUMN IF NOT EXISTS hidden_by TEXT",
)

_review_columns_ready = False


def ensure_letter_review_columns(conn: PgConnection) -> bool:
    global _review_columns_ready
    if _review_columns_ready:
        return True
    try:
        with conn.cursor() as cur:
            for stmt in _REVIEW_COLUMNS_SQL:
                cur.execute(stmt)
        conn.commit()
        _review_columns_ready = True
        return True
    except Exception:
        conn.rollback()
        return False


def parse_letter_lonlat(coordinates: str | None) -> tuple[float | None, float | None]:
    """Parse ``format_wgs84`` text ``lat, lon`` into ``(lon, lat)``."""
    text = (coordinates or "").strip()
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 2:
        return None, None
    try:
        lat = float(parts[0])
        lon = float(parts[1])
    except ValueError:
        return None, None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None, None
    return lon, lat


def normalize_letter_list_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LETTER_LIST_LIMIT
    if int(limit) not in LETTER_LIST_LIMITS:
        raise LetterError(
            f"limit must be one of {list(LETTER_LIST_LIMITS)}",
            status_code=422,
        )
    return int(limit)


def _payload_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _payload_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None:
        return ""
    return str(value).strip()


def letter_row_to_out(row: dict[str, Any]) -> dict[str, Any]:
    payload = _payload_dict(row.get("payload"))
    lon, lat = parse_letter_lonlat(_payload_text(payload, "coordinates") or None)
    status = row.get("review_status")
    review_status = str(status).strip() if status else None
    if review_status not in ("approved", "rejected"):
        review_status = None
    return {
        "fid": int(row["fid"]),
        "task_key": str(row.get("task_key") or ""),
        "report_id": int(row["report_id"]) if row.get("report_id") is not None else None,
        "created_by": str(row.get("created_by") or ""),
        "created_at": _iso(row.get("created_at")),
        "review_status": review_status,
        "reviewed_by": (str(row["reviewed_by"]).strip() if row.get("reviewed_by") else None),
        "reviewed_at": _iso(row.get("reviewed_at")),
        "street": _payload_text(payload, "street"),
        "address": _payload_text(payload, "address"),
        "rayon": _payload_text(payload, "rayon"),
        "customer": _payload_text(payload, "customer"),
        "executor": _payload_text(payload, "executor"),
        "description": _payload_text(payload, "description"),
        "today": _payload_text(payload, "today"),
        "coordinates": _payload_text(payload, "coordinates"),
        "lon": lon,
        "lat": lat,
    }


def list_letters_for_review(conn: PgConnection, *, limit: int | None = None) -> list[dict[str, Any]]:
    ensure_letter_review_columns(conn)
    limit = normalize_letter_list_limit(limit)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                fid,
                task_key::text,
                report_id,
                created_by,
                created_at,
                payload,
                review_status,
                reviewed_by,
                reviewed_at
            FROM webcrm.oati_letters
            WHERE hidden_at IS NULL
            ORDER BY created_at DESC, fid DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
    return [letter_row_to_out(row) for row in rows]


def set_letter_review(
    conn: PgConnection,
    fid: int,
    *,
    status: LetterReviewStatus | None,
    login: str,
) -> dict[str, Any]:
    ensure_letter_review_columns(conn)
    if status not in (None, "approved", "rejected"):
        raise LetterError("Недопустимый статус ревью", status_code=422)
    reviewer = (login or "").strip()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            UPDATE webcrm.oati_letters SET
                review_status = %s,
                reviewed_by = CASE WHEN %s IS NULL THEN NULL ELSE %s END,
                reviewed_at = CASE WHEN %s IS NULL THEN NULL ELSE NOW() END
            WHERE fid = %s
              AND hidden_at IS NULL
            RETURNING
                fid,
                task_key::text,
                report_id,
                created_by,
                created_at,
                payload,
                review_status,
                reviewed_by,
                reviewed_at
            """,
            (status, status, reviewer, status, fid),
        )
        row = cur.fetchone()
    conn.commit()
    if not row:
        raise LetterError("Письмо не найдено", status_code=404)
    return letter_row_to_out(row)


def hide_letter(conn: PgConnection, fid: int, *, login: str) -> None:
    ensure_letter_review_columns(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE webcrm.oati_letters SET
                hidden_at = NOW(),
                hidden_by = %s
            WHERE fid = %s
              AND hidden_at IS NULL
            RETURNING fid
            """,
            ((login or "").strip(), fid),
        )
        row = cur.fetchone()
    conn.commit()
    if not row:
        raise LetterError("Письмо не найдено", status_code=404)
