"""Spatial matching of Monitoring area orders against OZN polygons."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.layers.geojson import normalize_rayon_name, sql_normalize_rayon_expr

OGH_SCHEMA = "odh_export"
OGH_TABLE = "ogh_analiz"

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_GEOM_NAMES = ("geom", "geometry", "wkb_geometry", "the_geom")
_ID_NAMES = ("id", "gid", "fid", "ogc_fid", "objectid", "global_id")
_LABEL_NAMES = (
    "order_name",
    "number",
    "num",
    "nomer",
    "name",
    "task_number",
    "nazvanie",
    "title",
)
_OPTIONAL_OGH_COLUMNS = ("order_name", "ozn_date", "executor")
_VISIBLE_STATUSES = ("free", "wip")
_PAIR_LIMIT = 20_000


class OznMatchError(Exception):
    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


def _quote_ident(name: str) -> str:
    if not _IDENT_RE.match(name):
        raise OznMatchError(f"Недопустимое имя колонки: {name}")
    return f'"{name}"'


def _geom_to_4326_sql(qualified_col: str) -> str:
    return (
        f"CASE "
        f"WHEN ST_SRID({qualified_col}) IN (0, 4326) THEN {qualified_col} "
        f"ELSE ST_Transform({qualified_col}, 4326) "
        f"END"
    )


def _parse_geometry(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if isinstance(value, dict) and value.get("type"):
        return value
    return None


def _serialize_area(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _serialize_text(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _pick_column(names: tuple[str, ...], available: set[str]) -> str | None:
    lower_map = {col.lower(): col for col in available}
    for candidate in names:
        if candidate in lower_map:
            return lower_map[candidate]
    return None


def resolve_ogh_analiz_columns(conn: PgConnection) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"{OGH_SCHEMA}.{OGH_TABLE}",))
        row = cur.fetchone()
    if not row or row[0] is None:
        raise OznMatchError(
            f"Таблица {OGH_SCHEMA}.{OGH_TABLE} не найдена",
            status_code=503,
        )

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT column_name, udt_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            """,
            (OGH_SCHEMA, OGH_TABLE),
        )
        columns = list(cur.fetchall())

    if not columns:
        raise OznMatchError(
            f"Таблица {OGH_SCHEMA}.{OGH_TABLE} не содержит колонок",
            status_code=503,
        )

    available = {str(col["column_name"]) for col in columns}
    geom_from_udt = next(
        (
            str(col["column_name"])
            for col in columns
            if str(col.get("udt_name") or "").lower() == "geometry"
        ),
        None,
    )
    geom_col = geom_from_udt or _pick_column(_GEOM_NAMES, available)
    if not geom_col:
        raise OznMatchError(
            f"В {OGH_SCHEMA}.{OGH_TABLE} нет колонки геометрии",
            status_code=503,
        )

    id_col = _pick_column(_ID_NAMES, available)
    if not id_col:
        raise OznMatchError(
            f"В {OGH_SCHEMA}.{OGH_TABLE} нет колонки идентификатора",
            status_code=503,
        )

    label_col = _pick_column(_LABEL_NAMES, available) or id_col
    resolved: dict[str, str] = {"geom": geom_col, "id": id_col, "label": label_col}
    for name in _OPTIONAL_OGH_COLUMNS:
        found = _pick_column((name,), available)
        if found:
            resolved[name] = found
    if resolved.get("order_name"):
        resolved["label"] = resolved["order_name"]
    return resolved


def fetch_ozn_matches(
    conn: PgConnection,
    *,
    rayon: str | None = None,
    allowed_rayons: list[str] | None = None,
) -> dict[str, Any]:
    cols = resolve_ogh_analiz_columns(conn)
    geom_ident = _quote_ident(cols["geom"])
    id_ident = _quote_ident(cols["id"])
    label_ident = _quote_ident(cols["label"])
    ozn_geom_4326 = _geom_to_4326_sql(f"o.{geom_ident}")
    label_sql = (
        f"COALESCE(NULLIF(TRIM(o.{label_ident}::text), ''), o.{id_ident}::text)"
        if cols["label"] != cols["id"]
        else f"o.{id_ident}::text"
    )
    order_name_sql = (
        f"NULLIF(TRIM(o.{_quote_ident(cols['order_name'])}::text), '')"
        if cols.get("order_name")
        else "NULL::text"
    )
    ozn_date_sql = (
        f"o.{_quote_ident(cols['ozn_date'])}::text"
        if cols.get("ozn_date")
        else "NULL::text"
    )
    ozn_executor_sql = (
        f"NULLIF(TRIM(o.{_quote_ident(cols['executor'])}::text), '')"
        if cols.get("executor")
        else "NULL::text"
    )

    filters = [
        "ta.geom IS NOT NULL",
        f"o.{geom_ident} IS NOT NULL",
        f"ta.status IN ({', '.join(repr(s) for s in _VISIBLE_STATUSES)})",
    ]
    if cols.get("executor"):
        filters.append(
            f"NULLIF(TRIM(o.{_quote_ident(cols['executor'])}::text), '') IS NOT NULL"
        )
    else:
        filters.append("FALSE")
    params: list[Any] = []
    rayon_norm_sql = sql_normalize_rayon_expr("ta.rayon")

    if rayon:
        filters.append(f"{rayon_norm_sql} = %s")
        params.append(normalize_rayon_name(rayon))
    elif allowed_rayons:
        normalized = [normalize_rayon_name(name) for name in allowed_rayons if name]
        if not normalized:
            return {
                "district_name": "Все районы",
                "orders": [],
                "ozn_objects": [],
                "matches": {},
                "errors": [],
            }
        filters.append(f"{rayon_norm_sql} = ANY(%s)")
        params.append(normalized)

    where = " AND ".join(filters)
    params.append(_PAIR_LIMIT)

    query = f"""
        SELECT
            ta.key::text AS order_key,
            ta.task_number,
            ta.rayon,
            ta.area,
            ta.status,
            ta.executor,
            ST_AsGeoJSON(ta.geom)::json AS order_geometry,
            o.{id_ident}::text AS ozn_id,
            {label_sql} AS ozn_label,
            {order_name_sql} AS ozn_order_name,
            {ozn_date_sql} AS ozn_date,
            {ozn_executor_sql} AS ozn_executor,
            ST_AsGeoJSON({ozn_geom_4326})::json AS ozn_geometry
        FROM crm.tasks_area ta
        JOIN "{OGH_SCHEMA}"."{OGH_TABLE}" o
          ON ST_Intersects(ta.geom, {ozn_geom_4326})
        WHERE {where}
        LIMIT %s
    """

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        raise OznMatchError(f"Не удалось сопоставить заказы: {exc}", status_code=500) from exc

    orders_by_key: dict[str, dict[str, Any]] = {}
    ozn_by_id: dict[str, dict[str, Any]] = {}
    matches: dict[str, list[str]] = {}

    for row in rows:
        order_key = str(row.get("order_key") or "")
        ozn_id = str(row.get("ozn_id") or "")
        if not order_key or not ozn_id:
            continue

        order_geom = _parse_geometry(row.get("order_geometry"))
        ozn_geom = _parse_geometry(row.get("ozn_geometry"))
        if not order_geom or not ozn_geom:
            continue

        order = orders_by_key.get(order_key)
        if order is None:
            task_number = row.get("task_number")
            rayon_value = row.get("rayon")
            orders_by_key[order_key] = {
                "order_key": order_key,
                "task_number": (
                    str(task_number).strip() if task_number is not None else None
                ),
                "rayon": (
                    normalize_rayon_name(str(rayon_value)) if rayon_value else None
                ),
                "area": _serialize_area(row.get("area")),
                "status": str(row["status"]) if row.get("status") is not None else None,
                "executor": _serialize_text(row.get("executor")),
                "match_count": 0,
                "geometry": order_geom,
            }
            order = orders_by_key[order_key]
            matches[order_key] = []

        if ozn_id not in matches[order_key]:
            matches[order_key].append(ozn_id)
            order["match_count"] += 1

        if ozn_id not in ozn_by_id:
            label = row.get("ozn_label")
            order_name = _serialize_text(row.get("ozn_order_name")) or _serialize_text(label)
            ozn_by_id[ozn_id] = {
                "id": ozn_id,
                "label": str(label).strip() if label is not None else ozn_id,
                "order_name": order_name,
                "ozn_date": _serialize_text(row.get("ozn_date")),
                "executor": _serialize_text(row.get("ozn_executor")),
                "geometry": ozn_geom,
            }

    orders = sorted(
        (order for order in orders_by_key.values() if order["match_count"] > 0),
        key=lambda item: (
            -int(item["match_count"]),
            -(item["area"] or 0.0),
            str(item.get("task_number") or ""),
        ),
    )
    for order in orders:
        matches[order["order_key"]] = sorted(matches[order["order_key"]])

    ozn_ids_used = {ozn_id for ids in matches.values() for ozn_id in ids}
    ozn_objects = [ozn_by_id[ozn_id] for ozn_id in sorted(ozn_ids_used) if ozn_id in ozn_by_id]

    district_name = normalize_rayon_name(rayon) if rayon else "Все районы"
    return {
        "district_name": district_name,
        "orders": orders,
        "ozn_objects": ozn_objects,
        "matches": {key: matches[key] for key in (item["order_key"] for item in orders)},
        "errors": [],
    }


def empty_ozn_match_result(*, district_name: str = "Все районы") -> dict[str, Any]:
    return {
        "district_name": district_name,
        "orders": [],
        "ozn_objects": [],
        "matches": {},
        "errors": [],
    }
