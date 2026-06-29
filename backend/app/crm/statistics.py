"""CRM employee action statistics logging and dashboard queries."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, datetime, time, timezone
from typing import Any, Iterator

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

STATISTICS_SCHEMA = "crm"
STATISTICS_TABLE = "statistics"

OFFICE_SESSION_ROLES = frozenset({"office", "manager", "admin"})


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
            COUNT(*) FILTER (WHERE s.action = 'task_completed') AS tasks_completed,
            COUNT(*) FILTER (WHERE s.action = 'order_completed') AS orders_completed,
            COUNT(*) FILTER (WHERE s.action = 'task_created') AS tasks_created,
            MIN(s.created_at) AS period_from,
            MAX(s.created_at) AS period_to
        FROM "{STATISTICS_SCHEMA}"."{STATISTICS_TABLE}" s
        WHERE {where}
        GROUP BY s.user_login, s.user_role
        ORDER BY tasks_completed DESC, orders_completed DESC, tasks_created DESC
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    return [_row_with_iso_dates(dict(row)) for row in rows]


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

    where = " AND ".join(filters)
    query = f"""
        SELECT
            s.user_login,
            s.user_role,
            s.object_type,
            s.action,
            COUNT(*) AS action_count,
            MIN(s.created_at) AS period_from,
            MAX(s.created_at) AS period_to
        FROM "{STATISTICS_SCHEMA}"."{STATISTICS_TABLE}" s
        WHERE {where}
        GROUP BY s.user_login, s.user_role, s.object_type, s.action
        ORDER BY s.user_login, s.object_type, action_count DESC
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    return [_row_with_iso_dates(dict(row)) for row in rows]


def _row_with_iso_dates(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("period_from", "period_to"):
        value = row.get(key)
        if hasattr(value, "isoformat"):
            row[key] = value.isoformat()
    return row
