"""CRM employee action statistics logging and dashboard queries."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, datetime, time, timezone
from typing import Any, Iterator

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.config import order_tracks_config

STATISTICS_SCHEMA = "crm"
STATISTICS_TABLE = "statistics"

OFFICE_SESSION_ROLES = frozenset({"office", "manager", "admin"})

OFFICE_STATISTICS_ACTIONS = (
    "office_analise_started",
    "office_analise_completed",
    "office_disruption_absent",
    "office_camera_tasks_created",
    "office_closed_illegal",
    "office_closed_legal",
)

# Closed / analyzed actions shown in the per-employee detail list.
DETAIL_STATISTICS_ACTIONS = (
    "field_order_closed",
    "office_analise_completed",
    "office_closed_illegal",
    "office_closed_legal",
)


def map_session_role_to_statistics(role: str) -> str | None:
    role = (role or "").strip()
    if role == "field":
        return "field"
    if role in OFFICE_SESSION_ROLES:
        return "office"
    return None


@contextmanager
def skip_field_complete_trigger(conn: PgConnection) -> Iterator[None]:
    """Prevent mobile completion trigger when web CRM removes tasks from field."""
    with conn.cursor() as cur:
        cur.execute("SET LOCAL crm.statistics_skip_field_complete = 'true'")
    try:
        yield
    finally:
        pass


@contextmanager
def skip_area_complete_trigger(conn: PgConnection) -> Iterator[None]:
    """Let web CRM log area completion explicitly (field vs office action)."""
    with conn.cursor() as cur:
        cur.execute("SET LOCAL crm.statistics_skip_area_complete = 'true'")
    try:
        yield
    finally:
        pass


def _serialize_metadata(metadata: dict[str, Any] | None) -> str:
    payload = dict(metadata or {})
    payload.setdefault("source", "web")
    return json.dumps(payload)


def resolve_role_from_login(conn: PgConnection, login: str) -> str | None:
    login = (login or "").strip()
    if not login:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT role FROM crm.users WHERE login = %s LIMIT 1", (login,))
        row = cur.fetchone()
    if not row:
        return None
    return map_session_role_to_statistics(str(row[0]))


def log_statistic(
    conn: PgConnection,
    *,
    login: str,
    object_type: str,
    action: str,
    object_key: str,
    session_role: str | None = None,
    created_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
    skip_if_exists: bool = True,
) -> None:
    login = (login or "").strip()
    if not login:
        return
    user_role = map_session_role_to_statistics(session_role) if session_role else None
    if user_role is None:
        user_role = resolve_role_from_login(conn, login)
    if user_role is None:
        return

    stamp = created_at or datetime.now(timezone.utc)
    meta_json = _serialize_metadata(metadata)

    if skip_if_exists:
        exists_sql = f"""
            SELECT 1
            FROM "{STATISTICS_SCHEMA}"."{STATISTICS_TABLE}"
            WHERE object_type = %s AND object_key = %s::uuid AND action = %s
            LIMIT 1
        """
        with conn.cursor() as cur:
            cur.execute(exists_sql, (object_type, object_key, action))
            if cur.fetchone():
                return

    query = f"""
        INSERT INTO "{STATISTICS_SCHEMA}"."{STATISTICS_TABLE}" (
            user_id, user_login, user_role, object_type, action, object_key, created_at, metadata
        )
        SELECT
            u.uuid,
            %s,
            %s,
            %s,
            %s,
            %s::uuid,
            %s,
            %s::jsonb
        FROM (SELECT 1) AS _dummy
        LEFT JOIN crm.users u ON u.login = %s
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(
            query,
            (
                login,
                user_role,
                object_type,
                action,
                object_key,
                stamp,
                meta_json,
                login,
            ),
        )


def _period_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
    end = datetime.combine(date_to, time.max, tzinfo=timezone.utc)
    return start, end


def fetch_field_statistics_summary(
    conn: PgConnection,
    *,
    date_from: date,
    date_to: date,
    object_type: str | None = None,
    user_login: str | None = None,
) -> list[dict[str, Any]]:
    start, end = _period_bounds(date_from, date_to)
    filters = [
        "s.user_role = 'field'",
        "s.created_at >= %s",
        "s.created_at <= %s",
    ]
    params: list[Any] = [start, end]

    if object_type:
        filters.append("s.object_type = %s")
        params.append(object_type)
    if user_login:
        filters.append("s.user_login = %s")
        params.append(user_login.strip())

    where = " AND ".join(filters)
    query = f"""
        SELECT
            s.user_login,
            s.user_role,
            COUNT(*) FILTER (WHERE s.action = 'field_camera_survey') AS camera_surveys,
            COUNT(*) FILTER (WHERE s.action = 'field_disruption_absent') AS disruption_absent,
            COUNT(*) FILTER (WHERE s.action = 'field_disruption_found') AS disruption_found,
            COUNT(*) FILTER (WHERE s.action = 'field_order_closed') AS orders_closed,
            COALESCE(
                SUM(ta.area) FILTER (WHERE s.action = 'field_order_closed'),
                0
            ) / 10000.0 AS orders_closed_ha,
            MIN(s.created_at) AS period_from,
            MAX(s.created_at) AS period_to
        FROM "{STATISTICS_SCHEMA}"."{STATISTICS_TABLE}" s
        LEFT JOIN crm.tasks_area ta
          ON s.object_type = 'order'
         AND s.object_key = ta.key
        WHERE {where}
        GROUP BY s.user_login, s.user_role
        ORDER BY camera_surveys DESC, disruption_found DESC, orders_closed DESC
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    return [_normalize_area_floats(_row_with_iso_dates(dict(row))) for row in rows]


def fetch_office_statistics_breakdown(
    conn: PgConnection,
    *,
    date_from: date,
    date_to: date,
    object_type: str | None = None,
    user_login: str | None = None,
) -> list[dict[str, Any]]:
    start, end = _period_bounds(date_from, date_to)
    filters = [
        "s.user_role = 'office'",
        "s.created_at >= %s",
        "s.created_at <= %s",
    ]
    params: list[Any] = [start, end]

    if object_type:
        filters.append("s.object_type = %s")
        params.append(object_type)
    if user_login:
        filters.append("s.user_login = %s")
        params.append(user_login.strip())

    action_placeholders = ", ".join(["%s"] * len(OFFICE_STATISTICS_ACTIONS))
    filters.append(f"s.action IN ({action_placeholders})")
    params.extend(OFFICE_STATISTICS_ACTIONS)

    where = " AND ".join(filters)
    action_order = ", ".join(
        f"'{action}'" for action in OFFICE_STATISTICS_ACTIONS
    )
    query = f"""
        SELECT
            s.user_login,
            s.user_role,
            s.object_type,
            s.action,
            COUNT(*) AS action_count,
            COALESCE(SUM(ta.area), 0) / 10000.0 AS area_hectares,
            MIN(s.created_at) AS period_from,
            MAX(s.created_at) AS period_to
        FROM "{STATISTICS_SCHEMA}"."{STATISTICS_TABLE}" s
        LEFT JOIN crm.tasks_area ta
          ON s.object_type = 'order'
         AND s.object_key = ta.key
        WHERE {where}
        GROUP BY s.user_login, s.user_role, s.object_type, s.action
        ORDER BY s.user_login,
            array_position(ARRAY[{action_order}]::text[], s.action),
            s.object_type
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    return [_normalize_area_floats(_row_with_iso_dates(dict(row))) for row in rows]


def fetch_employee_action_details(
    conn: PgConnection,
    *,
    date_from: date,
    date_to: date,
    user_login: str,
    object_type: str | None = None,
    user_role: str | None = None,
) -> list[dict[str, Any]]:
    """Per-object closed/analyzed events for one employee, with duration in minutes."""
    login = (user_login or "").strip()
    if not login:
        return []

    start, end = _period_bounds(date_from, date_to)
    filters = [
        "s.user_login = %s",
        "s.created_at >= %s",
        "s.created_at <= %s",
    ]
    params: list[Any] = [login, start, end]

    if user_role:
        filters.append("s.user_role = %s")
        params.append(user_role)
    if object_type:
        filters.append("s.object_type = %s")
        params.append(object_type)

    action_placeholders = ", ".join(["%s"] * len(DETAIL_STATISTICS_ACTIONS))
    filters.append(f"s.action IN ({action_placeholders})")
    params.extend(DETAIL_STATISTICS_ACTIONS)

    tracks_cfg = order_tracks_config()
    tracks_schema = tracks_cfg.get("schema", "mggt_field")
    tracks_table = tracks_cfg.get("table", "tracks")
    task_col = tracks_cfg.get("task_column", "task")

    where = " AND ".join(filters)
    query = f"""
        SELECT
            s.user_login,
            s.user_role,
            s.object_type,
            s.action,
            s.object_key::text AS object_key,
            s.created_at,
            ta.task_number,
            ta.rayon,
            CASE
                WHEN s.object_type = 'order' THEN COALESCE(ta.area, 0) / 10000.0
                ELSE 0
            END AS area_hectares,
            CASE
                WHEN s.action = 'field_order_closed' THEN tr.duration_sec
                WHEN s.action = 'office_analise_completed'
                     AND ta.analise_started_at IS NOT NULL
                     AND ta.analise_finished_at IS NOT NULL
                THEN EXTRACT(
                    EPOCH FROM (ta.analise_finished_at - ta.analise_started_at)
                )
                ELSE NULL
            END AS duration_seconds
        FROM "{STATISTICS_SCHEMA}"."{STATISTICS_TABLE}" s
        LEFT JOIN crm.tasks_area ta
          ON s.object_type = 'order'
         AND s.object_key = ta.key
        LEFT JOIN (
            SELECT
                CASE
                    WHEN position(':' IN NULLIF(TRIM(t."{task_col}"::text), '')) > 0
                    THEN split_part(TRIM(t."{task_col}"::text), ':', 2)
                    ELSE TRIM(t."{task_col}"::text)
                END AS task_key,
                SUM(t.duration_sec) AS duration_sec
            FROM "{tracks_schema}"."{tracks_table}" t
            WHERE t."{task_col}" IS NOT NULL
              AND NULLIF(TRIM(t."{task_col}"::text), '') IS NOT NULL
              AND t.duration_sec IS NOT NULL
            GROUP BY 1
        ) tr ON s.action = 'field_order_closed'
           AND s.object_type = 'order'
           AND s.object_key::text = tr.task_key
        WHERE {where}
        ORDER BY s.created_at DESC
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    return [_normalize_detail_row(dict(row)) for row in rows]


def _row_with_iso_dates(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("period_from", "period_to", "created_at"):
        value = row.get(key)
        if hasattr(value, "isoformat"):
            row[key] = value.isoformat()
    return row


def _normalize_area_floats(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("orders_closed_ha", "area_hectares"):
        if key not in row:
            continue
        value = row.get(key)
        if value is None:
            row[key] = 0.0
        else:
            row[key] = float(value)
    return row


def _normalize_detail_row(row: dict[str, Any]) -> dict[str, Any]:
    row = _normalize_area_floats(_row_with_iso_dates(row))
    seconds = row.pop("duration_seconds", None)
    if seconds is None:
        row["duration_minutes"] = None
    else:
        row["duration_minutes"] = int(round(float(seconds) / 60.0))
    if row.get("task_number") is not None:
        row["task_number"] = str(row["task_number"]).strip() or None
    if row.get("rayon") is not None:
        row["rayon"] = str(row["rayon"]).strip() or None
    return row


_GEO_INT_METRICS = (
    "orders_closed",
    "orders_open",
    "analise_completed",
)

_GEO_HA_METRICS = (
    "orders_closed_ha",
    "orders_open_ha",
)

_GEO_ORDER_ACTIONS = (
    "field_order_closed",
    "office_analise_completed",
    "office_analise_started",
)


def fetch_geo_statistics(
    conn: PgConnection,
    *,
    date_from: date,
    date_to: date,
    object_type: str | None = None,
    user_login: str | None = None,
    user_role: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Aggregate order statistics by rayon and okrug (hierarchy Okrug → Rayon).

    Point/task metrics are excluded — only area orders. Open orders come from
    current ``crm.tasks_area`` (status free/wip) for progress context.
    """
    # Territory view is order-centric; task filter yields empty order stats.
    if object_type == "task":
        return {"okrugs": [], "rayons": []}

    start, end = _period_bounds(date_from, date_to)
    event_filters = [
        "s.created_at >= %s",
        "s.created_at <= %s",
        "s.object_type = 'order'",
    ]
    event_params: list[Any] = [start, end]

    if user_role:
        event_filters.append("s.user_role = %s")
        event_params.append(user_role)
    if user_login:
        event_filters.append("s.user_login = %s")
        event_params.append(user_login.strip())

    action_placeholders = ", ".join(["%s"] * len(_GEO_ORDER_ACTIONS))
    event_filters.append(f"s.action IN ({action_placeholders})")
    event_params.extend(_GEO_ORDER_ACTIONS)

    open_filters = [
        "ta.status IN ('free', 'wip')",
        "NULLIF(TRIM(ta.rayon), '') IS NOT NULL",
    ]
    open_params: list[Any] = []
    if user_login:
        open_filters.append("NULLIF(TRIM(ta.executor), '') = %s")
        open_params.append(user_login.strip())

    event_where = " AND ".join(event_filters)
    open_where = " AND ".join(open_filters)

    query = f"""
        WITH hood AS (
            SELECT DISTINCT ON (rayon_norm)
                rayon_norm,
                NULLIF(TRIM(okrug_shor), '') AS okrug
            FROM (
                SELECT
                    regexp_replace(TRIM(rayon::text), '\\s+', ' ', 'g') AS rayon_norm,
                    okrug_shor,
                    gid
                FROM odh_export.hood
                WHERE rayon IS NOT NULL
                  AND TRIM(rayon::text) <> ''
                  AND TRIM(COALESCE(okrug_shor, '')) NOT IN ('НАО', 'ТАО')
            ) h
            ORDER BY rayon_norm, gid
        ),
        events AS (
            SELECT
                s.action,
                ta.area,
                NULLIF(
                    regexp_replace(
                        TRIM(COALESCE(NULLIF(TRIM(ta.rayon), ''), s.metadata->>'rayon')),
                        '\\s+', ' ', 'g'
                    ),
                    ''
                ) AS rayon_norm
            FROM "{STATISTICS_SCHEMA}"."{STATISTICS_TABLE}" s
            LEFT JOIN crm.tasks_area ta
              ON s.object_key = ta.key
            WHERE {event_where}
        ),
        closed AS (
            SELECT
                rayon_norm,
                COUNT(*) FILTER (WHERE action = 'field_order_closed') AS orders_closed,
                COALESCE(
                    SUM(area) FILTER (WHERE action = 'field_order_closed'),
                    0
                ) / 10000.0 AS orders_closed_ha,
                COUNT(*) FILTER (WHERE action = 'office_analise_completed') AS analise_completed
            FROM events
            WHERE rayon_norm IS NOT NULL
            GROUP BY rayon_norm
        ),
        open_orders AS (
            SELECT
                regexp_replace(TRIM(ta.rayon), '\\s+', ' ', 'g') AS rayon_norm,
                COUNT(*) AS orders_open,
                COALESCE(SUM(ta.area), 0) / 10000.0 AS orders_open_ha
            FROM crm.tasks_area ta
            WHERE {open_where}
            GROUP BY 1
        ),
        combined AS (
            SELECT
                COALESCE(c.rayon_norm, o.rayon_norm) AS rayon_norm,
                COALESCE(c.orders_closed, 0) AS orders_closed,
                COALESCE(c.orders_closed_ha, 0) AS orders_closed_ha,
                COALESCE(c.analise_completed, 0) AS analise_completed,
                COALESCE(o.orders_open, 0) AS orders_open,
                COALESCE(o.orders_open_ha, 0) AS orders_open_ha
            FROM closed c
            FULL OUTER JOIN open_orders o ON c.rayon_norm = o.rayon_norm
        )
        SELECT
            h.okrug,
            c.rayon_norm AS rayon,
            c.orders_closed,
            c.orders_closed_ha,
            c.orders_open,
            c.orders_open_ha,
            c.analise_completed
        FROM combined c
        LEFT JOIN hood h ON c.rayon_norm = h.rayon_norm
        ORDER BY
            CASE WHEN h.okrug IS NULL OR TRIM(h.okrug) = '' THEN 1 ELSE 0 END,
            c.orders_closed DESC,
            c.orders_closed_ha DESC,
            c.orders_open DESC,
            c.rayon_norm
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, event_params + open_params)
        rayon_rows = [_normalize_geo_row(dict(row), level="rayon") for row in cur.fetchall()]

    okrug_totals: dict[str, dict[str, Any]] = {}
    for row in rayon_rows:
        okrug_key = row["okrug"] or ""
        bucket = okrug_totals.get(okrug_key)
        if bucket is None:
            bucket = {
                "okrug": okrug_key,
                "rayon": None,
                **{key: 0 for key in _GEO_INT_METRICS},
                **{key: 0.0 for key in _GEO_HA_METRICS},
            }
            okrug_totals[okrug_key] = bucket
        for key in _GEO_INT_METRICS:
            bucket[key] += int(row.get(key) or 0)
        for key in _GEO_HA_METRICS:
            bucket[key] += float(row.get(key) or 0.0)

    okrug_rows = [
        _normalize_geo_row(bucket, level="okrug")
        for bucket in okrug_totals.values()
    ]
    okrug_rows.sort(
        key=lambda r: (
            1 if not r["okrug"] else 0,
            -int(r["orders_closed"]),
            -float(r["orders_closed_ha"]),
            -int(r["orders_open"]),
            r["okrug"] or "",
        )
    )
    return {"okrugs": okrug_rows, "rayons": rayon_rows}


def _normalize_geo_row(row: dict[str, Any], *, level: str) -> dict[str, Any]:
    for key in _GEO_INT_METRICS:
        row[key] = int(row.get(key) or 0)
    for key in _GEO_HA_METRICS:
        value = row.get(key)
        row[key] = 0.0 if value is None else float(value)
    okrug = row.get("okrug")
    row["okrug"] = (str(okrug).strip() if okrug else "") or None
    if level == "okrug":
        row["rayon"] = None
    else:
        rayon = row.get("rayon")
        row["rayon"] = (str(rayon).strip() if rayon else "") or None
    closed_ha = float(row["orders_closed_ha"])
    open_ha = float(row["orders_open_ha"])
    total_ha = closed_ha + open_ha
    if total_ha > 0:
        row["progress_pct"] = round(100.0 * closed_ha / total_ha, 1)
    else:
        closed_n = int(row["orders_closed"])
        open_n = int(row["orders_open"])
        total_n = closed_n + open_n
        row["progress_pct"] = (
            round(100.0 * closed_n / total_n, 1) if total_n > 0 else None
        )
    return row
