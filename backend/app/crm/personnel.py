"""Personnel management: work zones and task executor assignment."""

from __future__ import annotations

from typing import Any, Literal

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.auth.session import HOOD_SCHEMA, HOOD_TABLE
from app.config import crm_task_store_config, crm_tasks_config
from app.crm.executor import ensure_all_executor_columns
from app.crm.user_audit import make_user_audit
from app.crm.store import (
    ensure_task_snapshot_table,
    fetch_active_task_summaries,
    fetch_task_types_by_keys,
    fetch_tasks_by_keys,
    fetch_workflow_status_map,
    set_task_workflow_status,
)
from app.layers.geojson import list_districts_with_gid

MANAGEABLE_ROLES = ("field", "office")
PERSONNEL_LIST_ROLES = ("field", "office", "manager")
CREATABLE_ROLES = ("field", "office", "manager")
WorkflowTarget = Literal["active", "field", "clear"]
TaskTable = Literal["field", "area"]


class PersonnelError(ValueError):
    """Validation error for personnel operations."""


def list_personnel_districts(conn: PgConnection) -> list[dict[str, Any]]:
    cfg = crm_tasks_config()
    district_cfg = cfg.get("district_filter", {})
    field = district_cfg.get("field", "rayon")
    return list_districts_with_gid(
        conn,
        HOOD_SCHEMA,
        HOOD_TABLE,
        field,
        exclude_okrug_shor=["НАО", "ТАО"],
    )


def _active_task_row(
    task_key: str,
    task_type: str = "",
    *,
    rayon: str | None = None,
) -> dict[str, Any]:
    return {
        "key": task_key,
        "task_key": task_key,
        "type": task_type,
        "executor": None,
        "sent_at": None,
        "rayon": rayon,
        "table": "active",
    }


def list_active_tasks_for_management(
    conn: PgConnection,
    *,
    rayon: str | None = None,
) -> list[dict[str, Any]]:
    store_cfg = crm_task_store_config()
    if not rayon:
        summaries = fetch_active_task_summaries(conn, store_cfg)
        return [_active_task_row(key, task_type) for key, task_type in summaries]

    from app.crm.collector import collect_tasks

    result, _ = collect_tasks(
        conn,
        rayon,
        apply_date_filter=False,
        persist=False,
        filter_sent=True,
    )
    seen: set[str] = set()
    keys: list[str] = []
    for group in result.groups:
        for subgroup in group.subgroups:
            for feat in subgroup.features:
                if feat.task_key and feat.task_key not in seen:
                    seen.add(feat.task_key)
                    keys.append(feat.task_key)
    if not keys:
        return []

    types = fetch_task_types_by_keys(conn, store_cfg, keys)
    return [
        _active_task_row(k, types.get(k, ""), rayon=rayon)
        for k in keys[:2000]
    ]


def _clear_task_row(row: dict[str, Any], rayon: str | None = None) -> dict[str, Any]:
    sent_at = row.get("sent_at")
    return {
        "key": row["key"],
        "task_key": row["task_key"],
        "type": row.get("type") or "",
        "executor": None,
        "sent_at": sent_at.isoformat() if hasattr(sent_at, "isoformat") else sent_at,
        "rayon": rayon,
        "table": "clear",
    }


def list_clear_tasks_for_management(
    conn: PgConnection,
    *,
    rayon: str | None = None,
) -> list[dict[str, Any]]:
    store_cfg = crm_task_store_config()
    schema = store_cfg.get("schema", "crm")
    table = store_cfg.get("clear_table", "tasks_clear")
    from app.crm.store import ensure_rayon_column
    from app.layers.geojson import normalize_rayon_name

    ensure_rayon_column(conn, schema, table)

    filters: list[str] = []
    params: list[Any] = []
    if rayon:
        rayon_norm = normalize_rayon_name(rayon)
        filters.append("(rayon = %s OR rayon IS NULL)")
        params.append(rayon_norm)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = f"""
        SELECT key::text, task_key::text, type, sent_at, rayon
        FROM "{schema}"."{table}"
        {where}
        ORDER BY sent_at DESC NULLS LAST
        LIMIT 2000
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    if not rayon:
        return [_clear_task_row(r) for r in rows]

    from app.crm.snapshot_loader import fetch_snapshot_rows_by_keys, snapshot_row_to_feature
    from app.layers.geojson import fetch_district_wkt

    metric_crs = crm_tasks_config().get("metric_crs", "EPSG:32637")
    metric_srid = int(metric_crs.split(":")[-1]) if ":" in metric_crs else 32637
    district_wkt = fetch_district_wkt(conn, rayon, metric_srid=metric_srid)
    if not district_wkt:
        return []

    rayon_norm = normalize_rayon_name(rayon)
    matched: list[dict[str, Any]] = []
    need_geometry: list[dict[str, Any]] = []
    for row in rows:
        row_rayon = row.get("rayon")
        if row_rayon and normalize_rayon_name(str(row_rayon)) == rayon_norm:
            matched.append(_clear_task_row(row, rayon=rayon))
        elif not row_rayon:
            need_geometry.append(row)

    if need_geometry:
        key_set = {r["key"] for r in need_geometry}
        snaps = fetch_snapshot_rows_by_keys(
            conn, store_cfg, "clear_table", "tasks_clear", list(key_set)
        )
        snap_by_key = {s.snapshot_key: s for s in snaps}
        for row in need_geometry:
            snap = snap_by_key.get(row["key"])
            if snap is None:
                continue
            feat = snapshot_row_to_feature(
                conn, snap, store_cfg, district_wkt, metric_srid, requested_rayon=rayon
            )
            if feat is None:
                continue
            matched.append(_clear_task_row(row, rayon=rayon))
    return matched


def bulk_change_task_workflow_status(
    conn: PgConnection,
    task_keys: list[str],
    target_status: WorkflowTarget,
    login: str,
    *,
    rayon: str | None = None,
) -> dict[str, Any]:
    store_cfg = crm_task_store_config()
    updated = 0
    skipped = 0
    not_found = 0
    failed: list[dict[str, str]] = []

    if not task_keys:
        return {"updated": 0, "skipped": 0, "not_found": 0, "failed": []}

    if target_status == "field":
        ensure_task_snapshot_table(conn, store_cfg, "field_table", "tasks_field")
    elif target_status == "clear":
        ensure_task_snapshot_table(conn, store_cfg, "clear_table", "tasks_clear")

    records_map = fetch_tasks_by_keys(conn, store_cfg, task_keys)
    status_map = fetch_workflow_status_map(conn, store_cfg, list(records_map.keys()))

    for task_key in task_keys:
        record = records_map.get(task_key)
        if record is None:
            not_found += 1
            continue
        try:
            current = status_map.get(task_key, "active")
            if current in ("done_legal", "done_illegal"):
                failed.append(
                    {
                        "task_key": task_key,
                        "error": "Закрытая задача недоступна для смены статуса",
                    }
                )
                continue
            result = set_task_workflow_status(
                conn,
                record,
                store_cfg,
                target_status,
                login,
                current=current,
                ensure_snapshot=False,
                rayon=rayon,
            )
            if result == "skipped":
                skipped += 1
            elif result in ("updated", "inserted", "deleted"):
                updated += 1
            elif result == "not_found":
                failed.append({"task_key": task_key, "error": "Задача не найдена в текущем статусе"})
            else:
                updated += 1
        except ValueError as exc:
            failed.append({"task_key": task_key, "error": str(exc)})
        except Exception as exc:
            failed.append({"task_key": task_key, "error": str(exc)})

    return {
        "updated": updated,
        "skipped": skipped,
        "not_found": not_found,
        "failed": failed,
    }


def _district_names_for_gids(conn: PgConnection, gids: list[int]) -> list[str]:
    if not gids:
        return []
    districts = list_personnel_districts(conn)
    gid_to_rayon = {d["gid"]: d["rayon"] for d in districts}
    return [gid_to_rayon[g] for g in gids if g in gid_to_rayon]


def _validate_work_zone_gids(conn: PgConnection, gids: list[int]) -> None:
    if not gids:
        return
    districts = list_personnel_districts(conn)
    valid = {d["gid"] for d in districts}
    invalid = [g for g in gids if g not in valid]
    if invalid:
        raise PersonnelError(f"Неизвестные gid районов: {invalid}")


def list_personnel_users(conn: PgConnection) -> list[dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT uuid::text, login, role, work_zones
            FROM crm.users
            WHERE role = ANY(%s)
            ORDER BY login
            """,
            (list(PERSONNEL_LIST_ROLES),),
        )
        rows = cur.fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        work_zones = [int(g) for g in (row["work_zones"] or [])]
        result.append(
            {
                "uuid": row["uuid"],
                "login": row["login"],
                "role": row["role"],
                "work_zones": work_zones,
                "district_names": _district_names_for_gids(conn, work_zones),
            }
        )
    return result


def update_user_work_zones(
    conn: PgConnection,
    user_uuid: str,
    work_zones: list[int],
) -> dict[str, Any] | None:
    _validate_work_zone_gids(conn, work_zones)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            UPDATE crm.users
            SET work_zones = %s
            WHERE uuid = %s::uuid AND role = ANY(%s)
            RETURNING uuid::text, login, role, work_zones
            """,
            (work_zones, user_uuid, list(PERSONNEL_LIST_ROLES)),
        )
        row = cur.fetchone()
    if not row:
        return None
    conn.commit()
    zones = [int(g) for g in (row["work_zones"] or [])]
    return {
        "uuid": row["uuid"],
        "login": row["login"],
        "role": row["role"],
        "work_zones": zones,
        "district_names": _district_names_for_gids(conn, zones),
    }


def create_personnel_user(
    conn: PgConnection,
    login: str,
    password: str,
    role: str,
    work_zones: list[int],
) -> dict[str, Any]:
    login = login.strip()
    password = password.strip()
    role = role.strip()

    if not login:
        raise PersonnelError("Логин не может быть пустым")
    if not password:
        raise PersonnelError("Пароль не может быть пустым")
    if role not in CREATABLE_ROLES:
        raise PersonnelError(f"Роль должна быть одной из: {', '.join(CREATABLE_ROLES)}")

    _validate_work_zone_gids(conn, work_zones)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT 1 FROM crm.users WHERE login = %s", (login,))
        if cur.fetchone():
            raise PersonnelError(f"Пользователь «{login}» уже существует")

        cur.execute(
            """
            INSERT INTO crm.users (login, password, role, work_zones)
            VALUES (%s, crypt(%s, gen_salt('bf')), %s, %s)
            RETURNING uuid::text, login, role, work_zones
            """,
            (login, password, role, work_zones),
        )
        row = cur.fetchone()
    conn.commit()

    if not row:
        raise PersonnelError("Не удалось создать пользователя")

    zones = [int(g) for g in (row["work_zones"] or [])]
    return {
        "uuid": row["uuid"],
        "login": row["login"],
        "role": row["role"],
        "work_zones": zones,
        "district_names": _district_names_for_gids(conn, zones),
    }


def _validate_executor(conn: PgConnection, executor: str | None) -> None:
    if executor is None:
        return
    login = executor.strip()
    if not login:
        raise PersonnelError("Пустой логин исполнителя")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM crm.users WHERE login = %s AND role = ANY(%s)",
            (login, list(MANAGEABLE_ROLES)),
        )
        if not cur.fetchone():
            raise PersonnelError(f"Исполнитель «{login}» не найден или недоступен для назначения")


def _executor_filter_sql(
    executor: str | None,
    *,
    unassigned_only: bool,
) -> tuple[str, list[Any]]:
    if unassigned_only:
        return '("executor" IS NULL OR TRIM("executor") = \'\')', []
    if executor is not None:
        return '"executor" = %s', [executor.strip()]
    return "", []


def list_field_tasks_for_assignment(
    conn: PgConnection,
    *,
    rayon: str | None = None,
    executor: str | None = None,
    unassigned_only: bool = False,
) -> list[dict[str, Any]]:
    ensure_all_executor_columns(conn)
    store_cfg = crm_task_store_config()
    schema = store_cfg.get("schema", "crm")
    table = store_cfg.get("field_table", "tasks_field")

    filters: list[str] = []
    params: list[Any] = []

    exec_sql, exec_params = _executor_filter_sql(executor, unassigned_only=unassigned_only)
    if exec_sql:
        filters.append(exec_sql)
        params.extend(exec_params)

    if rayon:
        from app.crm.store import ensure_rayon_column
        from app.layers.geojson import normalize_rayon_name

        ensure_rayon_column(conn, schema, table)
        filters.append("(rayon = %s OR rayon IS NULL)")
        params.append(normalize_rayon_name(rayon))

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = f"""
        SELECT key::text, task_key::text, type, executor, sent_at, rayon
        FROM "{schema}"."{table}"
        {where}
        ORDER BY sent_at DESC NULLS LAST
        LIMIT 2000
    """

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    if not rayon:
        return [_field_task_row(r) for r in rows]

    from app.crm.snapshot_loader import fetch_snapshot_rows_by_keys, snapshot_row_to_feature
    from app.layers.geojson import fetch_district_wkt, normalize_rayon_name

    rayon_norm = normalize_rayon_name(rayon)
    metric_crs = crm_tasks_config().get("metric_crs", "EPSG:32637")
    metric_srid = int(metric_crs.split(":")[-1]) if ":" in metric_crs else 32637
    district_wkt = fetch_district_wkt(conn, rayon_norm, metric_srid=metric_srid)
    if not district_wkt:
        return []

    key_set = {r["key"] for r in rows}
    snaps = fetch_snapshot_rows_by_keys(
        conn, store_cfg, "field_table", "tasks_field", list(key_set)
    )
    snap_by_key = {s.snapshot_key: s for s in snaps}
    matched: list[dict[str, Any]] = []
    for row in rows:
        snap = snap_by_key.get(row["key"])
        if snap is None:
            continue
        row_rayon = row.get("rayon")
        if row_rayon and normalize_rayon_name(str(row_rayon)) == rayon_norm:
            matched.append(_field_task_row(row, rayon=rayon_norm))
            continue
        feat = snapshot_row_to_feature(
            conn,
            snap,
            store_cfg,
            district_wkt,
            metric_srid,
            requested_rayon=rayon_norm,
        )
        if feat is None:
            continue
        matched.append(_field_task_row(row, rayon=rayon_norm))
    return matched


def _field_task_row(row: dict[str, Any], rayon: str | None = None) -> dict[str, Any]:
    sent_at = row.get("sent_at")
    return {
        "key": row["key"],
        "task_key": row["task_key"],
        "type": row.get("type") or "",
        "executor": row.get("executor"),
        "sent_at": sent_at.isoformat() if hasattr(sent_at, "isoformat") else sent_at,
        "rayon": rayon,
        "table": "field",
    }


def list_area_tasks_for_assignment(
    conn: PgConnection,
    *,
    rayon: str | None = None,
    status: str | None = None,
    executor: str | None = None,
    unassigned_only: bool = False,
) -> list[dict[str, Any]]:
    ensure_all_executor_columns(conn)
    filters: list[str] = []
    params: list[Any] = []

    if rayon:
        filters.append('"rayon" = %s')
        params.append(rayon)
    if status:
        filters.append('"status" = %s')
        params.append(status)

    exec_sql, exec_params = _executor_filter_sql(executor, unassigned_only=unassigned_only)
    if exec_sql:
        filters.append(exec_sql)
        params.extend(exec_params)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = f"""
        SELECT key::text, rayon, status, executor, area, date_survey, task_number
        FROM crm.tasks_area
        {where}
        ORDER BY loaded_at DESC NULLS LAST
        LIMIT 2000
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        date_survey = row.get("date_survey")
        result.append(
            {
                "key": row["key"],
                "rayon": row.get("rayon"),
                "status": row.get("status"),
                "executor": row.get("executor"),
                "area": row.get("area"),
                "task_number": row.get("task_number"),
                "date_survey": date_survey.isoformat()
                if hasattr(date_survey, "isoformat")
                else date_survey,
                "table": "area",
            }
        )
    return result


def _table_ref(table: TaskTable) -> tuple[str, str]:
    if table == "field":
        store_cfg = crm_task_store_config()
        return store_cfg.get("schema", "crm"), store_cfg.get("field_table", "tasks_field")
    return "crm", "tasks_area"


def lookup_field_snapshot_by_task_key(
    conn: PgConnection,
    task_key: str,
) -> dict[str, Any] | None:
    ensure_all_executor_columns(conn)
    store_cfg = crm_task_store_config()
    schema = store_cfg.get("schema", "crm")
    table = store_cfg.get("field_table", "tasks_field")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT key::text AS snapshot_key, executor
            FROM "{schema}"."{table}"
            WHERE task_key = %s::uuid
            ORDER BY sent_at DESC NULLS LAST
            LIMIT 1
            """,
            (task_key,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "snapshot_key": row["snapshot_key"],
        "executor": row.get("executor"),
    }


def assign_task_executor(
    conn: PgConnection,
    table: TaskTable,
    key: str,
    executor: str | None,
    login: str,
) -> str:
    ensure_all_executor_columns(conn)
    _validate_executor(conn, executor)
    schema, tbl = _table_ref(table)
    audit = make_user_audit(login)
    exec_value = executor.strip() if executor else None

    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE "{schema}"."{tbl}" SET
                executor = %s,
                user_last_edit = %s::text[]
            WHERE key = %s::uuid
            RETURNING key
            """,
            (exec_value, audit, key),
        )
        row = cur.fetchone()
    conn.commit()
    return "updated" if row else "not_found"


def bulk_assign_task_executor(
    conn: PgConnection,
    table: TaskTable,
    keys: list[str],
    executor: str | None,
    login: str,
) -> dict[str, int]:
    ensure_all_executor_columns(conn)
    _validate_executor(conn, executor)
    if not keys:
        return {"updated": 0, "not_found": 0}
    schema, tbl = _table_ref(table)
    audit = make_user_audit(login)
    exec_value = executor.strip() if executor else None

    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE "{schema}"."{tbl}" SET
                executor = %s,
                user_last_edit = %s::text[]
            WHERE key = ANY(%s::uuid[])
            RETURNING key
            """,
            (exec_value, audit, keys),
        )
        updated = cur.rowcount
    conn.commit()
    return {"updated": updated, "not_found": len(keys) - updated}
