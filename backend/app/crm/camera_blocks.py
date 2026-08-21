"""Pause GenPlan photo task creation for a camera after send-to-field."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Literal, Optional

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.crm.date_utils import parse_attribute_date
from app.crm.store import (
    CRM_GROUP_DISRUPTIONS,
    TaskRecord,
    _normalize_id_value,
    moscow_today,
)

logger = logging.getLogger(__name__)

CameraBlockMode = Literal[
    "until_field_observed",
    "until_quarter",
    "until_date",
    "until_order_end",
]

CAMERA_BLOCK_MODES: tuple[CameraBlockMode, ...] = (
    "until_field_observed",
    "until_quarter",
    "until_date",
    "until_order_end",
)

ORDER_LINK_COLUMNS = ("oati_id", "earthwork_id", "avr_mos_id")

_TABLE_READY = False

ENSURE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS crm.camera_blocks (
        cam_id TEXT PRIMARY KEY,
        mode TEXT NOT NULL CHECK (mode IN (
            'until_field_observed',
            'until_quarter',
            'until_date',
            'until_order_end'
        )),
        until_date DATE,
        task_key UUID,
        created_by TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_crm_camera_blocks_task_key
        ON crm.camera_blocks (task_key)
        WHERE task_key IS NOT NULL
    """,
    """
    CREATE OR REPLACE FUNCTION crm.camera_is_blocked(p_cam_id TEXT)
    RETURNS BOOLEAN
    LANGUAGE plpgsql
    STABLE
    AS $$
    DECLARE
      blk RECORD;
      observed BOOLEAN;
      today_msk DATE;
    BEGIN
      IF p_cam_id IS NULL OR btrim(p_cam_id) = '' THEN
        RETURN FALSE;
      END IF;

      SELECT mode, until_date, task_key
        INTO blk
      FROM crm.camera_blocks
      WHERE cam_id = btrim(p_cam_id);

      IF NOT FOUND THEN
        RETURN FALSE;
      END IF;

      today_msk := (NOW() AT TIME ZONE 'Europe/Moscow')::date;

      IF blk.mode = 'until_field_observed' THEN
        IF blk.task_key IS NULL THEN
          RETURN TRUE;
        END IF;
        SELECT field_observed INTO observed
        FROM crm.tasks
        WHERE key = blk.task_key;
        RETURN COALESCE(observed, FALSE) IS NOT TRUE;
      END IF;

      IF blk.mode = 'until_quarter' THEN
        RETURN blk.until_date IS NOT NULL AND today_msk < blk.until_date;
      END IF;

      IF blk.mode IN ('until_date', 'until_order_end') THEN
        RETURN blk.until_date IS NOT NULL AND today_msk <= blk.until_date;
      END IF;

      RETURN FALSE;
    END;
    $$
    """,
    """
    CREATE OR REPLACE FUNCTION crm.camera_block_skip_task_insert()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    DECLARE
      cam TEXT;
    BEGIN
      IF NEW.photo_uuid IS NULL OR btrim(NEW.photo_uuid) = '' THEN
        RETURN NEW;
      END IF;

      BEGIN
        SELECT NULLIF(btrim(cam_id::text), '')
          INTO cam
        FROM genplan.photo_meta
        WHERE uuid::text = btrim(NEW.photo_uuid)
        LIMIT 1;
      EXCEPTION
        WHEN undefined_table OR undefined_column THEN
          RETURN NEW;
      END;

      IF cam IS NULL THEN
        RETURN NEW;
      END IF;

      IF crm.camera_is_blocked(cam) THEN
        RAISE NOTICE
          'camera_blocks: skip INSERT crm.tasks photo_uuid=% cam_id=%',
          NEW.photo_uuid, cam;
        RETURN NULL;
      END IF;

      RETURN NEW;
    END;
    $$
    """,
    "DROP TRIGGER IF EXISTS trg_camera_block_skip_insert ON crm.tasks",
    """
    CREATE TRIGGER trg_camera_block_skip_insert
      BEFORE INSERT ON crm.tasks
      FOR EACH ROW
      EXECUTE FUNCTION crm.camera_block_skip_task_insert()
    """,
    """
    CREATE OR REPLACE FUNCTION crm.camera_block_release_on_observed()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
      IF NEW.field_observed IS TRUE AND OLD.field_observed IS DISTINCT FROM TRUE THEN
        DELETE FROM crm.camera_blocks
        WHERE mode = 'until_field_observed'
          AND task_key = NEW.key;
      END IF;
      RETURN NEW;
    END;
    $$
    """,
    "DROP TRIGGER IF EXISTS trg_camera_block_release_observed ON crm.tasks",
    """
    CREATE TRIGGER trg_camera_block_release_observed
      BEFORE UPDATE OF field_observed ON crm.tasks
      FOR EACH ROW
      EXECUTE FUNCTION crm.camera_block_release_on_observed()
    """,
)


def ensure_camera_blocks_table(conn: PgConnection) -> bool:
    global _TABLE_READY
    if _TABLE_READY:
        return True
    try:
        with conn.cursor() as cur:
            for stmt in ENSURE_STATEMENTS:
                cur.execute(stmt)
        conn.commit()
        _TABLE_READY = True
        return True
    except Exception as exc:
        conn.rollback()
        logger.warning("Failed to ensure crm.camera_blocks: %s", exc)
        return False


def next_quarter_start(today: date) -> date:
    """First day of the calendar quarter after ``today``."""
    quarter_index = (today.month - 1) // 3
    if quarter_index >= 3:
        return date(today.year + 1, 1, 1)
    return date(today.year, quarter_index * 3 + 4, 1)


def is_camera_block_active(
    *,
    mode: str,
    until_date: date | None,
    task_field_observed: bool | None,
    today: date,
    has_task_key: bool = True,
) -> bool:
    """Python mirror of crm.camera_is_blocked for a loaded row."""
    if mode == "until_field_observed":
        if not has_task_key:
            return True
        return task_field_observed is not True
    if mode == "until_quarter":
        return until_date is not None and today < until_date
    if mode in ("until_date", "until_order_end"):
        return until_date is not None and today <= until_date
    return False


def should_skip_photo_task_insert(
    photo_uuid: str | None,
    cam_id: str | None,
    block_active: bool,
) -> bool:
    """Mirror of BEFORE INSERT skip: only GenPlan rows with a blocked cam_id."""
    if not _normalize_id_value(photo_uuid):
        return False
    if not _normalize_id_value(cam_id):
        return False
    return block_active


def resolve_cam_id(conn: PgConnection, photo_uuid: str | None) -> str | None:
    uuid = _normalize_id_value(photo_uuid)
    if not uuid:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT NULLIF(btrim(cam_id::text), '')
                FROM genplan.photo_meta
                WHERE uuid::text = %s
                LIMIT 1
                """,
                (uuid,),
            )
            row = cur.fetchone()
    except Exception as exc:
        logger.warning("Failed to read genplan.photo_meta.cam_id for %s: %s", uuid, exc)
        return None
    if not row:
        return None
    return _normalize_id_value(row[0])


def resolve_order_end_date(
    conn: PgConnection,
    record: TaskRecord,
    store_cfg: dict[str, Any],
    registry: Any,
) -> date | None:
    if not any(_normalize_id_value(getattr(record, col)) for col in ORDER_LINK_COLUMNS):
        return None

    from app.crm.link_resolver import resolve_linked_features

    linked, _missing = resolve_linked_features(
        conn, record, CRM_GROUP_DISRUPTIONS, store_cfg, registry
    )
    dates: list[date] = []
    for feat in linked:
        if feat.get("link_column") not in ORDER_LINK_COLUMNS:
            continue
        parsed = parse_attribute_date((feat.get("attributes") or {}).get("work_end_date"))
        if parsed is not None:
            dates.append(parsed)
    return max(dates) if dates else None


def upsert_camera_block(
    conn: PgConnection,
    *,
    cam_id: str,
    mode: CameraBlockMode,
    until_date: date | None,
    task_key: str | None,
    created_by: str,
) -> dict[str, Any]:
    ensure_camera_blocks_table(conn)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO crm.camera_blocks (cam_id, mode, until_date, task_key, created_by)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (cam_id) DO UPDATE SET
                mode = EXCLUDED.mode,
                until_date = EXCLUDED.until_date,
                task_key = EXCLUDED.task_key,
                created_by = EXCLUDED.created_by,
                created_at = NOW()
            RETURNING cam_id, mode, until_date, task_key::text AS task_key
            """,
            (cam_id, mode, until_date, task_key, created_by),
        )
        row = dict(cur.fetchone() or {})
    conn.commit()
    return row


def apply_camera_block(
    conn: PgConnection,
    record: TaskRecord,
    *,
    mode: CameraBlockMode,
    until_date: date | None,
    login: str,
    store_cfg: dict[str, Any],
    registry: Any,
) -> dict[str, Any]:
    cam_id = resolve_cam_id(conn, record.photo_uuid)
    if not cam_id:
        raise ValueError("У фотографии нет номера камеры")

    today = moscow_today()
    task_key: Optional[str] = None
    resolved_until: date | None = None

    if mode == "until_field_observed":
        task_key = record.key
    elif mode == "until_quarter":
        resolved_until = next_quarter_start(today)
    elif mode == "until_date":
        if until_date is None:
            raise ValueError("Укажите дату блокировки")
        if until_date <= today:
            raise ValueError("Дата блокировки должна быть позже сегодняшнего дня")
        resolved_until = until_date
    elif mode == "until_order_end":
        resolved_until = resolve_order_end_date(conn, record, store_cfg, registry)
        if resolved_until is None:
            raise ValueError("Не удалось получить дату окончания ордера")
    else:
        raise ValueError("Неизвестный режим блокировки камеры")

    return upsert_camera_block(
        conn,
        cam_id=cam_id,
        mode=mode,
        until_date=resolved_until,
        task_key=task_key,
        created_by=login,
    )
