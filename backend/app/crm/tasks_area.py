"""CRM tasks_area list and status workflow."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.crm.collector import TaskFeature, TaskGroup, TaskResult, TaskSubgroup
from app.crm.executor import ensure_executor_column
from app.crm.user_audit import make_user_audit, user_audit_migration_statements

AREA_LAYER_KEY = "tasks_area"
AREA_LAYER_NAME = "Площадные заказы"
AREA_GROUP_NAME = "Площадные заказы"

AREA_STATUSES = ("free", "wip", "done")

AREA_STATUS_LABELS = {
    "free": "Свободные",
    "wip": "На обследовании",
    "done": "Завершённые",
}

TASKS_AREA_SCHEMA = "crm"
TASKS_AREA_TABLE = "tasks_area"
_tasks_area_audit_ready = False
_analise_audit_ready = False

ANALISE_AUDIT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("analise_started_by", "TEXT"),
    ("analise_started_at", "TIMESTAMPTZ"),
    ("analise_finished_by", "TEXT"),
    ("analise_finished_at", "TIMESTAMPTZ"),
    ("analise_paused_by", "TEXT"),
    ("analise_paused_at", "TIMESTAMPTZ"),
)


def ensure_tasks_area_audit_columns(conn: PgConnection) -> bool:
    global _tasks_area_audit_ready
    if _tasks_area_audit_ready:
        return True
    try:
        with conn.cursor() as cur:
            for stmt in user_audit_migration_statements(TASKS_AREA_SCHEMA, TASKS_AREA_TABLE):
                cur.execute(stmt)
        conn.commit()
        _tasks_area_audit_ready = True
        return True
    except Exception:
        conn.rollback()
        return False


def fetch_tasks_area_geojson(
    conn: PgConnection,
    rayon: str | None = None,
    status: str | None = None,
    statuses: list[str] | None = None,
    rayons: list[str] | None = None,
    limit: int = 5000,
    *,
    field_executor_login: str | None = None,
) -> dict[str, Any]:
    clear_stale_analise_locks(conn)

    filters = ['"geom" IS NOT NULL']
    params: list[Any] = []

    if rayon:
        filters.append('"rayon" = %s')
        params.append(rayon)
    elif rayons:
        filters.append('"rayon" = ANY(%s)')
        params.append(rayons)
    if status:
        filters.append('"status" = %s')
        params.append(status)
    elif statuses:
        placeholders = ", ".join("%s" for _ in statuses)
        filters.append(f'"status" IN ({placeholders})')
        params.extend(statuses)
    if field_executor_login is not None:
        ensure_executor_column(conn, TASKS_AREA_SCHEMA, TASKS_AREA_TABLE)
        filters.append('(executor IS NULL OR executor = %s)')
        params.append(field_executor_login)

    where = " AND ".join(filters)
    params.append(limit)

    query = f"""
        SELECT json_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(json_agg(feature), '[]'::json)
        ) AS geojson
        FROM (
            SELECT json_build_object(
                'type', 'Feature',
                'id', key::text,
                'geometry', ST_AsGeoJSON(geom)::json,
                'properties', to_jsonb(t) - 'geom'
            ) AS feature
            FROM crm.tasks_area t
            WHERE {where}
            ORDER BY loaded_at DESC NULLS LAST
            LIMIT %s
        ) sub
    """

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        row = cur.fetchone()

    if row and row["geojson"]:
        return row["geojson"]
    return {"type": "FeatureCollection", "features": []}


def collect_tasks_area(
    conn: PgConnection,
    rayon: str,
    status: str,
    *,
    field_executor_login: str | None = None,
) -> TaskResult:
    if status not in AREA_STATUSES:
        raise ValueError(f"Unknown area status: {status}")

    today = date.today()
    geojson = fetch_tasks_area_geojson(
        conn,
        rayon=rayon,
        status=status,
        field_executor_login=field_executor_login,
    )
    features: list[TaskFeature] = []

    for item in geojson.get("features", []):
        props = dict(item.get("properties") or {})
        features.append(
            TaskFeature(
                layer_name=AREA_LAYER_NAME,
                layer_key=AREA_LAYER_KEY,
                attributes=props,
                geometry=item.get("geometry"),
                task_key=str(props.get("key", item.get("id", ""))),
            )
        )

    subgroup = TaskSubgroup(
        name=AREA_STATUS_LABELS.get(status, status),
        features=features,
    )
    group = TaskGroup(name=AREA_GROUP_NAME, subgroups=[subgroup])

    return TaskResult(
        district_name=rayon,
        filter_date_from=today - timedelta(days=3),
        filter_date_to=today,
        apply_date_filter=False,
        groups=[group],
    )


def collect_tasks_area_all(
    conn: PgConnection,
    rayon: str,
    statuses: list[str],
    *,
    field_executor_login: str | None = None,
) -> TaskResult:
    if not statuses:
        raise ValueError("At least one area status is required")

    for status in statuses:
        if status not in AREA_STATUSES:
            raise ValueError(f"Unknown area status: {status}")

    today = date.today()
    geojson = fetch_tasks_area_geojson(
        conn,
        rayon=rayon,
        statuses=statuses,
        field_executor_login=field_executor_login,
    )
    features: list[TaskFeature] = []

    for item in geojson.get("features", []):
        props = dict(item.get("properties") or {})
        features.append(
            TaskFeature(
                layer_name=AREA_LAYER_NAME,
                layer_key=AREA_LAYER_KEY,
                attributes=props,
                geometry=item.get("geometry"),
                task_key=str(props.get("key", item.get("id", ""))),
            )
        )

    subgroup = TaskSubgroup(name="Заказы", features=features)
    group = TaskGroup(name=AREA_GROUP_NAME, subgroups=[subgroup])

    return TaskResult(
        district_name=rayon,
        filter_date_from=today - timedelta(days=3),
        filter_date_to=today,
        apply_date_filter=False,
        groups=[group],
    )


def tasks_area_result_to_dict(result: TaskResult, task_source: str = "area") -> dict[str, Any]:
    from app.crm.collector import task_result_to_dict

    data = task_result_to_dict(result)
    data["task_source"] = task_source
    return data


def send_area_to_survey(conn: PgConnection, key: str, login: str) -> str:
    return _transition_area_status(
        conn, key, login=login, from_status=None, to_status="wip", skip_if="wip"
    )


def release_area_from_survey(conn: PgConnection, key: str, login: str) -> str:
    return _transition_area_status(conn, key, login=login, from_status="wip", to_status="free")


def complete_area_survey(conn: PgConnection, key: str, login: str) -> str:
    return _transition_area_status(conn, key, login=login, from_status="wip", to_status="done")


def ensure_analise_audit_columns(conn: PgConnection) -> bool:
    global _analise_audit_ready
    if _analise_audit_ready:
        return True
    try:
        with conn.cursor() as cur:
            for col_name, col_type in ANALISE_AUDIT_COLUMNS:
                cur.execute(
                    f'ALTER TABLE "{TASKS_AREA_SCHEMA}"."{TASKS_AREA_TABLE}" '
                    f'ADD COLUMN IF NOT EXISTS "{col_name}" {col_type}'
                )
        conn.commit()
        _analise_audit_ready = True
        return True
    except Exception:
        conn.rollback()
        return False


def clear_stale_analise_locks(conn: PgConnection) -> int:
    """Release incomplete analise locks started on a previous Moscow calendar day."""
    ensure_analise_audit_columns(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE crm.tasks_area SET
                analise_started_by = NULL,
                analise_started_at = NULL,
                analise_paused_by = NULL,
                analise_paused_at = NULL
            WHERE COALESCE(analise, FALSE) = FALSE
              AND analise_started_at IS NOT NULL
              AND (analise_started_at AT TIME ZONE 'Europe/Moscow')::date
                  < (NOW() AT TIME ZONE 'Europe/Moscow')::date
            RETURNING key
            """
        )
        rows = cur.fetchall()
    conn.commit()
    return len(rows)


def _fetch_analise_state(conn: PgConnection, key: str) -> dict[str, Any] | None:
    ensure_analise_audit_columns(conn)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                analise,
                analise_started_by,
                analise_started_at,
                analise_paused_by,
                analise_paused_at
            FROM crm.tasks_area
            WHERE key = %s::uuid
            """,
            (key,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def start_area_analise(conn: PgConnection, key: str, login: str) -> str:
    ensure_tasks_area_audit_columns(conn)
    ensure_analise_audit_columns(conn)
    clear_stale_analise_locks(conn)
    state = _fetch_analise_state(conn, key)
    if state is None:
        return "not_found"
    if state.get("analise") is True:
        return "skipped"

    started_at = state.get("analise_started_at")
    started_by = (state.get("analise_started_by") or "").strip()
    paused_at = state.get("analise_paused_at")
    login = login.strip()

    if started_at is None:
        audit = make_user_audit(login)
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE crm.tasks_area SET
                    analise_started_by = %s,
                    analise_started_at = NOW(),
                    analise_paused_by = NULL,
                    analise_paused_at = NULL,
                    user_last_edit = %s::text[]
                WHERE key = %s::uuid
                  AND COALESCE(analise, FALSE) = FALSE
                  AND analise_started_at IS NULL
                RETURNING key
                """,
                (login, audit, key),
            )
            row = cur.fetchone()
        conn.commit()
        return "updated" if row else "not_found"

    if paused_at is not None:
        if started_by != login:
            return "conflict"
        audit = make_user_audit(login)
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE crm.tasks_area SET
                    analise_paused_by = NULL,
                    analise_paused_at = NULL,
                    user_last_edit = %s::text[]
                WHERE key = %s::uuid
                  AND COALESCE(analise, FALSE) = FALSE
                  AND analise_paused_at IS NOT NULL
                  AND analise_started_by = %s
                RETURNING key
                """,
                (audit, key, login),
            )
            row = cur.fetchone()
        conn.commit()
        return "updated" if row else "not_found"

    if started_by == login:
        return "skipped"
    return "conflict"


def pause_area_analise(conn: PgConnection, key: str, login: str) -> str:
    ensure_tasks_area_audit_columns(conn)
    ensure_analise_audit_columns(conn)
    audit = make_user_audit(login.strip())
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE crm.tasks_area SET
                analise_paused_by = %s,
                analise_paused_at = NOW(),
                user_last_edit = %s::text[]
            WHERE key = %s::uuid
              AND COALESCE(analise, FALSE) = FALSE
              AND analise_started_at IS NOT NULL
              AND analise_paused_at IS NULL
              AND analise_started_by = %s
            RETURNING key
            """,
            (login.strip(), audit, key, login.strip()),
        )
        row = cur.fetchone()
    conn.commit()
    if row:
        return "updated"

    state = _fetch_analise_state(conn, key)
    if state is None:
        return "not_found"
    if state.get("analise") is True:
        return "skipped"
    if state.get("analise_paused_at") is not None:
        return "skipped"
    return "not_found"


def analise_lock_holder(conn: PgConnection, key: str) -> str | None:
    state = _fetch_analise_state(conn, key)
    if state is None:
        return None
    if state.get("analise") is True:
        return None
    if state.get("analise_started_at") is None:
        return None
    if state.get("analise_paused_at") is not None:
        holder = (state.get("analise_started_by") or "").strip()
        return holder or None
    holder = (state.get("analise_started_by") or "").strip()
    return holder or None


def complete_area_analise(conn: PgConnection, key: str, login: str) -> str:
    ensure_tasks_area_audit_columns(conn)
    ensure_analise_audit_columns(conn)
    audit = make_user_audit(login)
    login = login.strip()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE crm.tasks_area SET
                analise = TRUE,
                analise_finished_by = %s,
                analise_finished_at = NOW(),
                analise_paused_by = NULL,
                analise_paused_at = NULL,
                user_last_edit = %s::text[]
            WHERE key = %s::uuid
              AND COALESCE(analise, FALSE) = FALSE
              AND analise_started_by = %s
              AND analise_started_at IS NOT NULL
              AND analise_paused_at IS NULL
            RETURNING key
            """,
            (login, audit, key, login),
        )
        row = cur.fetchone()
    conn.commit()
    if row:
        return "updated"

    state = _fetch_analise_state(conn, key)
    if state is None:
        return "not_found"
    if state.get("analise") is True:
        return "skipped"
    return "not_found"


def update_area_task_number(
    conn: PgConnection,
    key: str,
    task_number: str | None,
    login: str,
) -> str:
    ensure_tasks_area_audit_columns(conn)
    audit = make_user_audit(login)
    value = task_number.strip() if task_number else None
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE crm.tasks_area SET
                task_number = %s,
                user_last_edit = %s::text[]
            WHERE key = %s::uuid
            RETURNING key
            """,
            (value, audit, key),
        )
        row = cur.fetchone()
    conn.commit()
    return "updated" if row else "not_found"


def _transition_area_status(
    conn: PgConnection,
    key: str,
    *,
    login: str,
    from_status: str | None,
    to_status: str,
    skip_if: str | None = None,
) -> str:
    ensure_tasks_area_audit_columns(conn)
    audit = make_user_audit(login)

    if from_status is None:
        where = "key = %s::uuid AND COALESCE(status, '') <> %s"
        params: tuple[Any, ...] = (to_status, audit, audit, key, skip_if or to_status)
        sql = f"""
            UPDATE crm.tasks_area SET
                status = %s,
                user_last_edit = %s::text[],
                user_created = COALESCE(user_created, %s::text[])
            WHERE {where}
            RETURNING key
        """
    else:
        where = "key = %s::uuid AND status = %s"
        params = (to_status, audit, audit, key, from_status)
        sql = f"""
            UPDATE crm.tasks_area SET
                status = %s,
                user_last_edit = %s::text[],
                user_created = COALESCE(user_created, %s::text[])
            WHERE {where}
            RETURNING key
        """

    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    conn.commit()
    if row:
        return "updated"

    with conn.cursor() as cur:
        cur.execute(
            'SELECT status FROM crm.tasks_area WHERE key = %s::uuid',
            (key,),
        )
        existing = cur.fetchone()
    if not existing:
        return "not_found"
    if skip_if and existing[0] == skip_if:
        return "skipped"
    if from_status and existing[0] == from_status:
        return "skipped"
    return "not_found"
