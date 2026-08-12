"""Create office analysis point tasks during камеральный анализ."""

from __future__ import annotations

import json
from typing import Any

from psycopg2.extensions import connection as PgConnection

from app.crm.store import (
    CRM_GROUP_DISRUPTIONS,
    TASK_ID_COLUMNS,
    TaskRecord,
    _normalize_id_value,
    _task_select_columns_sql,
)
from app.crm.tasks_area import analise_lock_holder, pre_analise_lock_holder
from app.crm.user_audit import make_user_audit

_LINK_PREFILL_COLUMNS = frozenset({"oati_id", "earthwork_id", "localwork_id", "avr_mos_id"})
_STAGE_OPERATOR_ROLES = frozenset({"office"})
_FREE_PLACE_ROLES = frozenset({"manager", "admin"})


def _validate_point_geometry(geometry: dict[str, Any]) -> tuple[float, float]:
    if geometry.get("type") != "Point":
        raise ValueError("geometry must be a GeoJSON Point")
    coords = geometry.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 2:
        raise ValueError("geometry.coordinates must be [lng, lat]")
    lng, lat = float(coords[0]), float(coords[1])
    if not (-180 <= lng <= 180 and -90 <= lat <= 90):
        raise ValueError("geometry coordinates out of range")
    return lng, lat


def _require_active_stage_lock(conn: PgConnection, area_task_key: str, login: str) -> None:
    holder = analise_lock_holder(conn, area_task_key)
    if holder is None:
        holder = pre_analise_lock_holder(conn, area_task_key)
    if holder is None:
        raise ValueError("Площадный заказ не в режиме подготовки или анализа")
    if holder.strip() != login.strip():
        raise ValueError("Заказ выполняет другой пользователь")


def _point_inside_area(conn: PgConnection, area_task_key: str, lng: float, lat: float) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ST_Contains(
                geom,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)
            )
            FROM crm.tasks_area
            WHERE key = %s::uuid
              AND geom IS NOT NULL
            """,
            (lng, lat, area_task_key),
        )
        row = cur.fetchone()
    if not row or not row[0]:
        raise ValueError("Точка должна находиться внутри полигона площадного заказа")


def _resolve_area_task_key(conn: PgConnection, lng: float, lat: float) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT key::text
            FROM crm.tasks_area
            WHERE geom IS NOT NULL
              AND ST_Contains(
                  geom,
                  ST_SetSRID(ST_MakePoint(%s, %s), 4326)
              )
            ORDER BY area ASC NULLS LAST, key ASC
            LIMIT 1
            """,
            (lng, lat),
        )
        row = cur.fetchone()
    if not row:
        raise ValueError("Точка вне площадных заказов")
    return str(row[0])


def create_office_task(
    conn: PgConnection,
    login: str,
    geometry: dict[str, Any],
    area_task_key: str | None = None,
    link_prefill: dict[str, Any] | None = None,
    *,
    role: str,
) -> TaskRecord:
    lng, lat = _validate_point_geometry(geometry)
    role_normalized = (role or "").strip().lower()

    if role_normalized in _STAGE_OPERATOR_ROLES:
        if not area_task_key or not str(area_task_key).strip():
            raise ValueError("area_task_key обязателен для роли office")
        resolved_key = str(area_task_key).strip()
        _require_active_stage_lock(conn, resolved_key, login)
        _point_inside_area(conn, resolved_key, lng, lat)
    elif role_normalized in _FREE_PLACE_ROLES:
        if area_task_key and str(area_task_key).strip():
            resolved_key = str(area_task_key).strip()
            _point_inside_area(conn, resolved_key, lng, lat)
        else:
            _resolve_area_task_key(conn, lng, lat)
    else:
        raise ValueError("Создание office-точки недоступно для вашей роли")

    id_values: dict[str, str | None] = {col: None for col in TASK_ID_COLUMNS}
    if link_prefill:
        for col, value in link_prefill.items():
            if col not in _LINK_PREFILL_COLUMNS:
                continue
            normalized = _normalize_id_value(value)
            if normalized:
                id_values[col] = normalized

    audit = make_user_audit(login)
    geom_json = json.dumps(geometry)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO crm.tasks (
                type,
                photo_uuid, photo_lens, ogh_id, oati_id, earthwork_id, localwork_id, avr_mos_id,
                is_office_task,
                user_created, user_last_edit
            ) VALUES (
                %s,
                %s, %s, %s, %s, %s, %s, %s,
                TRUE,
                %s::text[], %s::text[]
            )
            RETURNING key
            """,
            (
                CRM_GROUP_DISRUPTIONS,
                id_values["photo_uuid"],
                id_values["photo_lens"],
                id_values["ogh_id"],
                id_values["oati_id"],
                id_values["earthwork_id"],
                id_values["localwork_id"],
                id_values["avr_mos_id"],
                audit,
                audit,
            ),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError("Failed to insert office task")
        task_key = str(row[0])

        cur.execute(
            """
            INSERT INTO crm.office_task_points (task_key, point)
            VALUES (%s::uuid, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
            """,
            (task_key, geom_json),
        )

    conn.commit()

    columns = _task_select_columns_sql()
    with conn.cursor() as cur:
        cur.execute(f'SELECT {columns} FROM crm.tasks WHERE key = %s LIMIT 1', (task_key,))
        fetched = cur.fetchone()
    if not fetched:
        raise RuntimeError("Office task not found after insert")
    return TaskRecord.from_row(fetched)
