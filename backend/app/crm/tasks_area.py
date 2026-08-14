"""CRM tasks_area list and status workflow."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.crm.collector import TaskFeature, TaskGroup, TaskResult, TaskSubgroup
from app.crm.executor import ensure_executor_column
from app.crm.user_audit import make_user_audit, user_audit_migration_statements

logger = logging.getLogger(__name__)

AREA_LAYER_KEY = "tasks_area"
AREA_LAYER_NAME = "Площадные заказы"
AREA_GROUP_NAME = "Площадные заказы"

AREA_STATUSES = ("free", "wip", "wip_field", "in_pause", "done")

AREA_STATUS_LABELS = {
    "free": "Свободные",
    "wip": "На обследовании",
    "wip_field": "В работе в поле",
    "in_pause": "Приостановлен в поле",
    "done": "Завершённые",
}

TASKS_AREA_SCHEMA = "crm"
TASKS_AREA_TABLE = "tasks_area"
_tasks_area_audit_ready = False
_analise_audit_ready = False
_pre_analise_audit_ready = False

ANALISE_RESET_HOUR = 7
_SNAPSHOT_RESET_TABLES = (
    ("field_table", "tasks_field"),
    ("done_legal_table", "tasks_done_legal"),
    ("done_illegal_table", "tasks_done_illegal"),
    ("clear_table", "tasks_clear"),
    ("delay_table", "tasks_delay"),
)

ANALISE_AUDIT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("analise_started_by", "TEXT"),
    ("analise_started_at", "TIMESTAMPTZ"),
    ("analise_finished_by", "TEXT"),
    ("analise_finished_at", "TIMESTAMPTZ"),
    ("analise_paused_by", "TEXT"),
    ("analise_paused_at", "TIMESTAMPTZ"),
)

PRE_ANALISE_AUDIT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("pre_analise", "BOOLEAN"),
    ("pre_analise_started_by", "TEXT"),
    ("pre_analise_started_at", "TIMESTAMPTZ"),
    ("pre_analise_finished_by", "TEXT"),
    ("pre_analise_finished_at", "TIMESTAMPTZ"),
    ("pre_analise_paused_by", "TEXT"),
    ("pre_analise_paused_at", "TIMESTAMPTZ"),
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
    try:
        clear_stale_analise_locks(conn)
        clear_stale_pre_analise_locks(conn)
    except Exception:
        conn.rollback()
        logger.exception("Failed to reset stale analise/pre_analise locks")

    from app.layers.geojson import normalize_rayon_name, sql_normalize_rayon_expr

    filters = ['"geom" IS NOT NULL']
    params: list[Any] = []
    rayon_norm_sql = sql_normalize_rayon_expr('"rayon"')

    if rayon:
        filters.append(f"{rayon_norm_sql} = %s")
        params.append(normalize_rayon_name(rayon))
    elif rayons:
        normalized = [normalize_rayon_name(r) for r in rayons if normalize_rayon_name(r)]
        filters.append(f"{rayon_norm_sql} = ANY(%s)")
        params.append(normalized)
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


def _moscow_reset_at_sql() -> str:
    """Most recent ANALISE_RESET_HOUR:00 Europe/Moscow as timestamptz."""
    hhmm = f"{ANALISE_RESET_HOUR:02d}:00:00"
    return (
        "("
        "CASE "
        f"WHEN (NOW() AT TIME ZONE 'Europe/Moscow')::time >= TIME '{hhmm}' "
        f"THEN date_trunc('day', NOW() AT TIME ZONE 'Europe/Moscow') + TIME '{hhmm}' "
        f"ELSE date_trunc('day', NOW() AT TIME ZONE 'Europe/Moscow') "
        f"- INTERVAL '1 day' + TIME '{hhmm}' "
        "END"
        ") AT TIME ZONE 'Europe/Moscow'"
    )


def _snapshot_table_names() -> list[tuple[str, str]]:
    from app.config import crm_task_store_config

    store_cfg = crm_task_store_config()
    schema = store_cfg.get("schema", "crm")
    return [
        (schema, store_cfg.get(config_key, default_table))
        for config_key, default_table in _SNAPSHOT_RESET_TABLES
    ]


def _not_in_snapshots_sql(task_alias: str = "t") -> str:
    clauses = [
        f'NOT EXISTS (SELECT 1 FROM "{schema}"."{table}" s '
        f"WHERE s.task_key = {task_alias}.key)"
        for schema, table in _snapshot_table_names()
    ]
    return " AND ".join(clauses) if clauses else "TRUE"


def _in_field_sql(task_alias: str = "t") -> str:
    schema, table = _snapshot_table_names()[0]
    return (
        f'EXISTS (SELECT 1 FROM "{schema}"."{table}" s '
        f"WHERE s.task_key = {task_alias}.key)"
    )


def _task_geom_union_sql() -> str:
    # tasks_field.geom was dropped (sql/29): resolve geometry from points, reports, items_*.
    parts = [
        "SELECT p.task_key, p.point AS geom "
        "FROM crm.office_task_points p WHERE p.point IS NOT NULL",
    ]
    try:
        from app.config import crm_task_store_config, crm_tasks_config
        from app.crm.field_data_loader import _field_data_mapping, _reports_qualified_table
        from app.layers.geojson import _is_data_mos_items_table
        from app.layers.registry import get_registry

        store_cfg = crm_task_store_config()
        mapping = _field_data_mapping(store_cfg)
        reports_table = _reports_qualified_table(mapping)
        tasks_key_col = mapping.get("reports_tasks_key", "tasks_key")
        report_geom_col = mapping.get("reports_geometry", "point")
        parts.append(
            f'SELECT r."{tasks_key_col}" AS task_key, r."{report_geom_col}" AS geom '
            f"FROM {reports_table} r "
            f'WHERE r."{tasks_key_col}" IS NOT NULL AND r."{report_geom_col}" IS NOT NULL'
        )

        registry = get_registry()
        crm_cfg = crm_tasks_config()
        seen_tables: set[str] = set()
        for group_cfg in crm_cfg.get("groups", []):
            for sub_cfg in group_cfg.get("subgroups", []):
                subgroup_name = sub_cfg.get("name", "")
                sub_mapping = store_cfg.get("subgroups", {}).get(subgroup_name) or {}
                if not sub_mapping.get("scoped_geometry_id"):
                    continue
                layers, _ = registry.resolve_subgroup_layers(
                    sub_cfg.get("layers", []),
                    sub_cfg.get("groups", []),
                )
                for layer in layers:
                    if not _is_data_mos_items_table(layer.qualified_table):
                        continue
                    if layer.qualified_table in seen_tables:
                        continue
                    seen_tables.add(layer.qualified_table)
                    layer_geom_col = layer.geometry_column
                    parts.append(
                        f'SELECT i.task_key, i."{layer_geom_col}" AS geom '
                        f"FROM {layer.qualified_table} i "
                        f'WHERE i.task_key IS NOT NULL AND i."{layer_geom_col}" IS NOT NULL'
                    )
    except Exception:
        pass
    return " UNION ALL ".join(f"({p})" for p in parts)


def _new_stage_tasks_exist_sql(stage: str) -> str:
    """EXISTS: new CRM tasks inside the order polygon after the stage finished."""
    finished_col = (
        "a.analise_finished_at" if stage == "analise" else "a.pre_analise_finished_at"
    )
    started_col = (
        "a.analise_started_at" if stage == "analise" else "a.pre_analise_started_at"
    )
    observed_pred = (
        "t.field_observed IS TRUE"
        if stage == "analise"
        else "COALESCE(t.field_observed, FALSE) = FALSE"
    )
    if stage == "analise":
        section_pred = _not_in_snapshots_sql("t")
    else:
        section_pred = f"({_in_field_sql('t')} OR ({_not_in_snapshots_sql('t')}))"
    geom_union = _task_geom_union_sql()
    return f"""
              EXISTS (
                SELECT 1
                FROM crm.tasks t
                WHERE {observed_pred}
                  AND {section_pred}
                  AND (t.user_created)[2]::timestamptz
                      > COALESCE({finished_col}, {started_col}, TIMESTAMPTZ '1970-01-01')
                  AND EXISTS (
                    SELECT 1
                    FROM ({geom_union}) g
                    WHERE g.task_key = t.key
                      AND g.geom IS NOT NULL
                      AND a.geom IS NOT NULL
                      AND ST_Intersects(ST_Transform(g.geom, 4326), a.geom)
                  )
              )
    """


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
    """Reset analise after the 07:00 Europe/Moscow cutoff.

    - Completed analyses finished before the last 07:00, if new Active tasks
      with field_observed=true appeared in the order after completion → idle
    - Incomplete locks started before the last 07:00 → lock released
    """
    ensure_analise_audit_columns(conn)
    reset_at = _moscow_reset_at_sql()
    new_tasks = _new_stage_tasks_exist_sql("analise")
    cleared = 0
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE crm.tasks_area AS a SET
                analise = FALSE,
                analise_started_by = NULL,
                analise_started_at = NULL,
                analise_finished_by = NULL,
                analise_finished_at = NULL,
                analise_paused_by = NULL,
                analise_paused_at = NULL
            WHERE COALESCE(a.analise, FALSE) = TRUE
              AND COALESCE(
                    a.analise_finished_at,
                    a.analise_started_at,
                    TIMESTAMPTZ '1970-01-01'
                  ) < {reset_at}
              AND {new_tasks}
            RETURNING a.key
            """
        )
        cleared += len(cur.fetchall())

        cur.execute(
            f"""
            UPDATE crm.tasks_area AS a SET
                analise_started_by = NULL,
                analise_started_at = NULL,
                analise_paused_by = NULL,
                analise_paused_at = NULL
            WHERE COALESCE(a.analise, FALSE) = FALSE
              AND a.analise_started_at IS NOT NULL
              AND a.analise_started_at < {reset_at}
            RETURNING a.key
            """
        )
        cleared += len(cur.fetchall())
    conn.commit()
    return cleared


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


def ensure_pre_analise_audit_columns(conn: PgConnection) -> bool:
    global _pre_analise_audit_ready
    if _pre_analise_audit_ready:
        return True
    try:
        with conn.cursor() as cur:
            for col_name, col_type in PRE_ANALISE_AUDIT_COLUMNS:
                cur.execute(
                    f'ALTER TABLE "{TASKS_AREA_SCHEMA}"."{TASKS_AREA_TABLE}" '
                    f'ADD COLUMN IF NOT EXISTS "{col_name}" {col_type}'
                )
        conn.commit()
        _pre_analise_audit_ready = True
        return True
    except Exception:
        conn.rollback()
        return False


def clear_stale_pre_analise_locks(conn: PgConnection) -> int:
    """Reset pre_analise after the 07:00 Europe/Moscow cutoff.

    - Completed preparations finished before the last 07:00, if new Active or
      Field tasks with field_observed=false appeared in the order after
      completion → idle
    - Incomplete locks started before the last 07:00 → lock released
    """
    ensure_pre_analise_audit_columns(conn)
    reset_at = _moscow_reset_at_sql()
    new_tasks = _new_stage_tasks_exist_sql("pre_analise")
    cleared = 0
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE crm.tasks_area AS a SET
                pre_analise = FALSE,
                pre_analise_started_by = NULL,
                pre_analise_started_at = NULL,
                pre_analise_finished_by = NULL,
                pre_analise_finished_at = NULL,
                pre_analise_paused_by = NULL,
                pre_analise_paused_at = NULL
            WHERE COALESCE(a.pre_analise, FALSE) = TRUE
              AND COALESCE(
                    a.pre_analise_finished_at,
                    a.pre_analise_started_at,
                    TIMESTAMPTZ '1970-01-01'
                  ) < {reset_at}
              AND {new_tasks}
            RETURNING a.key
            """
        )
        cleared += len(cur.fetchall())

        cur.execute(
            f"""
            UPDATE crm.tasks_area AS a SET
                pre_analise_started_by = NULL,
                pre_analise_started_at = NULL,
                pre_analise_paused_by = NULL,
                pre_analise_paused_at = NULL
            WHERE COALESCE(a.pre_analise, FALSE) = FALSE
              AND a.pre_analise_started_at IS NOT NULL
              AND a.pre_analise_started_at < {reset_at}
            RETURNING a.key
            """
        )
        cleared += len(cur.fetchall())
    conn.commit()
    return cleared


def _fetch_pre_analise_state(conn: PgConnection, key: str) -> dict[str, Any] | None:
    ensure_pre_analise_audit_columns(conn)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                pre_analise,
                pre_analise_started_by,
                pre_analise_started_at,
                pre_analise_paused_by,
                pre_analise_paused_at
            FROM crm.tasks_area
            WHERE key = %s::uuid
            """,
            (key,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def start_area_pre_analise(conn: PgConnection, key: str, login: str) -> str:
    ensure_tasks_area_audit_columns(conn)
    ensure_pre_analise_audit_columns(conn)
    clear_stale_pre_analise_locks(conn)
    state = _fetch_pre_analise_state(conn, key)
    if state is None:
        return "not_found"
    if state.get("pre_analise") is True:
        return "skipped"

    started_at = state.get("pre_analise_started_at")
    started_by = (state.get("pre_analise_started_by") or "").strip()
    paused_at = state.get("pre_analise_paused_at")
    login = login.strip()

    if started_at is None:
        audit = make_user_audit(login)
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE crm.tasks_area SET
                    pre_analise_started_by = %s,
                    pre_analise_started_at = NOW(),
                    pre_analise_paused_by = NULL,
                    pre_analise_paused_at = NULL,
                    user_last_edit = %s::text[]
                WHERE key = %s::uuid
                  AND COALESCE(pre_analise, FALSE) = FALSE
                  AND pre_analise_started_at IS NULL
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
                    pre_analise_paused_by = NULL,
                    pre_analise_paused_at = NULL,
                    user_last_edit = %s::text[]
                WHERE key = %s::uuid
                  AND COALESCE(pre_analise, FALSE) = FALSE
                  AND pre_analise_paused_at IS NOT NULL
                  AND pre_analise_started_by = %s
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


def pause_area_pre_analise(conn: PgConnection, key: str, login: str) -> str:
    ensure_tasks_area_audit_columns(conn)
    ensure_pre_analise_audit_columns(conn)
    audit = make_user_audit(login.strip())
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE crm.tasks_area SET
                pre_analise_paused_by = %s,
                pre_analise_paused_at = NOW(),
                user_last_edit = %s::text[]
            WHERE key = %s::uuid
              AND COALESCE(pre_analise, FALSE) = FALSE
              AND pre_analise_started_at IS NOT NULL
              AND pre_analise_paused_at IS NULL
              AND pre_analise_started_by = %s
            RETURNING key
            """,
            (login.strip(), audit, key, login.strip()),
        )
        row = cur.fetchone()
    conn.commit()
    if row:
        return "updated"

    state = _fetch_pre_analise_state(conn, key)
    if state is None:
        return "not_found"
    if state.get("pre_analise") is True:
        return "skipped"
    if state.get("pre_analise_paused_at") is not None:
        return "skipped"
    return "not_found"


def pre_analise_lock_holder(conn: PgConnection, key: str) -> str | None:
    state = _fetch_pre_analise_state(conn, key)
    if state is None:
        return None
    if state.get("pre_analise") is True:
        return None
    if state.get("pre_analise_started_at") is None:
        return None
    if state.get("pre_analise_paused_at") is not None:
        holder = (state.get("pre_analise_started_by") or "").strip()
        return holder or None
    holder = (state.get("pre_analise_started_by") or "").strip()
    return holder or None


def complete_area_pre_analise(conn: PgConnection, key: str, login: str) -> str:
    ensure_tasks_area_audit_columns(conn)
    ensure_pre_analise_audit_columns(conn)
    audit = make_user_audit(login)
    login = login.strip()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE crm.tasks_area SET
                pre_analise = TRUE,
                pre_analise_finished_by = %s,
                pre_analise_finished_at = NOW(),
                pre_analise_paused_by = NULL,
                pre_analise_paused_at = NULL,
                user_last_edit = %s::text[]
            WHERE key = %s::uuid
              AND COALESCE(pre_analise, FALSE) = FALSE
              AND pre_analise_started_by = %s
              AND pre_analise_started_at IS NOT NULL
              AND pre_analise_paused_at IS NULL
            RETURNING key
            """,
            (login, audit, key, login),
        )
        row = cur.fetchone()
    conn.commit()
    if row:
        return "updated"

    state = _fetch_pre_analise_state(conn, key)
    if state is None:
        return "not_found"
    if state.get("pre_analise") is True:
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
