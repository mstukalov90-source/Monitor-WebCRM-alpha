"""Fetch report dataset rows for Excel export."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.config import crm_task_store_config
from app.crm.reports.catalog import (
    DATASETS,
    MAX_EXPORT_ROWS,
    MAX_PARENT_KEYS,
    NEST_NESTED,
    NEST_RELATED,
    SURVEYED_TASK_SOURCES,
    ColumnDef,
    ReportSheetSpec,
    ReportSpec,
    resolve_sheet_columns,
)
from app.crm.reports.errors import ReportError
from app.crm.statistics import (
    fetch_employee_action_details,
    fetch_field_statistics_summary,
    fetch_geo_statistics,
    fetch_office_statistics_breakdown,
    fetch_recent_order_closures,
)
from app.crm.store import TASK_ID_COLUMNS
from app.crm.tasks_area import _task_geom_union_sql
from app.layers.geojson import normalize_rayon_name, sql_normalize_rayon_expr

EXPORT_STATEMENT_TIMEOUT = "120s"
TASK_QUERY_CHUNK = 400

SNAPSHOT_SOURCE_MAP = {
    "done_legal": ("done_legal_table", "tasks_done_legal"),
    "done_illegal": ("done_illegal_table", "tasks_done_illegal"),
    "clear": ("clear_table", "tasks_clear"),
}

SURVEYED_OUTCOME_PRIORITY = ("done_illegal", "done_legal", "clear", "open")
EMPTY_SURVEYED_COUNTS = {
    "tasks_surveyed": 0,
    "tasks_clear": 0,
    "tasks_done_legal": 0,
    "tasks_done_illegal": 0,
    "tasks_open": 0,
}

ID_COLUMN_SQL = ", ".join(f'sn."{col}"' for col in TASK_ID_COLUMNS)
ACTIVE_ID_COLUMN_SQL = ", ".join(f't."{col}"' for col in TASK_ID_COLUMNS)


@dataclass
class SheetData:
    id: str
    title: str
    dataset: str
    columns: list[ColumnDef]
    rows: list[dict[str, Any]]
    nested_children: list["SheetData"] = field(default_factory=list)


@dataclass(frozen=True)
class QueryScope:
    date_from: date
    date_to: date
    user_login: str | None = None
    user_role: str | None = None
    object_type: str | None = None
    rayons: tuple[str, ...] = ()


def apply_export_timeout(conn: PgConnection, timeout: str = EXPORT_STATEMENT_TIMEOUT) -> None:
    if timeout != EXPORT_STATEMENT_TIMEOUT:
        timeout = EXPORT_STATEMENT_TIMEOUT
    with conn.cursor() as cur:
        cur.execute(f"SET LOCAL statement_timeout = '{timeout}'")


def _raise_if_timeout(exc: BaseException) -> None:
    text = str(exc).lower()
    if "timeout" in text or "canceling statement" in text:
        raise ReportError(
            "Отчёт слишком большой или база не успела ответить. Сузьте период или набор данных.",
            503,
        ) from exc


def _check_row_budget(count: int) -> None:
    if count > MAX_EXPORT_ROWS:
        raise ReportError(
            f"Слишком много строк для выгрузки (больше {MAX_EXPORT_ROWS}). "
            "Сузьте период, фильтры или число листов."
        )


def _normalized_rayons(rayons: tuple[str, ...]) -> list[str]:
    seen: list[str] = []
    for raw in rayons:
        name = normalize_rayon_name(raw)
        if name and name not in seen:
            seen.append(name)
    return seen


def _rayon_in_sql(field_sql: str, rayons: list[str]) -> tuple[str, list[Any]]:
    if not rayons:
        return "TRUE", []
    placeholders = ", ".join(["%s"] * len(rayons))
    expr = sql_normalize_rayon_expr(field_sql)
    return f"{expr} IN ({placeholders})", list(rayons)


def _snapshot_table(config_key: str, default_table: str) -> tuple[str, str]:
    store_cfg = crm_task_store_config()
    schema = store_cfg.get("schema", "crm")
    table = store_cfg.get(config_key, default_table)
    return schema, table


def _parent_order_keys(rows: list[dict[str, Any]]) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        key = str(row.get("order_key") or row.get("object_key") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    if len(keys) > MAX_PARENT_KEYS:
        raise ReportError(
            f"Слишком много заказов для связанных задач (больше {MAX_PARENT_KEYS}). "
            "Сузьте период или районы."
        )
    return keys


def fetch_report_sheets(conn: PgConnection, spec: ReportSpec, scope: QueryScope) -> list[SheetData]:
    by_id: dict[str, SheetData] = {}
    try:
        for sheet in _ordered_sheets(spec):
            dataset = DATASETS[sheet.dataset]
            related_child = bool(sheet.parent_sheet) and sheet.nest == NEST_RELATED
            columns = resolve_sheet_columns(
                dataset, sheet.columns, related_child=related_child
            )
            parent_keys: list[str] = []
            if sheet.parent_sheet:
                parent = by_id.get(sheet.parent_sheet)
                if parent is None:
                    raise ReportError("Родительский лист ещё не рассчитан")
                parent_keys = _parent_order_keys(parent.rows)

            rows = _fetch_dataset(
                conn,
                dataset.id,
                scope,
                sheet.filters,
                parent_keys=parent_keys,
            )
            _check_row_budget(len(rows))
            data = SheetData(
                id=sheet.id,
                title=sheet.title,
                dataset=dataset.id,
                columns=columns,
                rows=rows,
            )
            if sheet.parent_sheet and sheet.nest == NEST_NESTED:
                parent = by_id[sheet.parent_sheet]
                parent.nested_children.append(data)
            else:
                by_id[sheet.id] = data
    except ReportError:
        raise
    except Exception as exc:
        _raise_if_timeout(exc)
        raise

    result = [by_id[sheet.id] for sheet in spec.sheets if sheet.id in by_id]
    total = sum(len(item.rows) for item in result)
    for item in result:
        for child in item.nested_children:
            total += len(child.rows)
    _check_row_budget(total)
    return result


def _ordered_sheets(spec: ReportSpec) -> list[ReportSheetSpec]:
    remaining = {sheet.id: sheet for sheet in spec.sheets}
    ordered: list[ReportSheetSpec] = []
    while remaining:
        progress = False
        for sheet_id, sheet in list(remaining.items()):
            parent_id = sheet.parent_sheet
            if not parent_id or parent_id not in remaining:
                ordered.append(sheet)
                del remaining[sheet_id]
                progress = True
        if not progress:
            raise ReportError("Цикл вложенности листов")
    return ordered


def _fetch_dataset(
    conn: PgConnection,
    dataset_id: str,
    scope: QueryScope,
    filters: dict[str, Any],
    *,
    parent_keys: list[str],
) -> list[dict[str, Any]]:
    if dataset_id == "field_summary":
        return _as_dicts(
            fetch_field_statistics_summary(
                conn,
                date_from=scope.date_from,
                date_to=scope.date_to,
                object_type=scope.object_type,
                user_login=scope.user_login,
            )
        )
    if dataset_id == "office_breakdown":
        return _as_dicts(
            fetch_office_statistics_breakdown(
                conn,
                date_from=scope.date_from,
                date_to=scope.date_to,
                object_type=scope.object_type,
                user_login=scope.user_login,
            )
        )
    if dataset_id in ("geo_okrugs", "geo_rayons"):
        geo = fetch_geo_statistics(
            conn,
            date_from=scope.date_from,
            date_to=scope.date_to,
            object_type=scope.object_type,
            user_login=scope.user_login,
            user_role=scope.user_role,
        )
        key = "okrugs" if dataset_id == "geo_okrugs" else "rayons"
        rows = _as_dicts(geo.get(key) or [])
        return _filter_geo_rayons(rows, scope.rayons)
    if dataset_id == "order_closures":
        rows = _as_dicts(
            fetch_recent_order_closures(
                conn,
                date_from=scope.date_from,
                date_to=scope.date_to,
                user_login=scope.user_login,
                user_role=scope.user_role,
            )
        )
        return _filter_rows_by_rayon(rows, "rayon", scope.rayons)
    if dataset_id == "action_details":
        if not scope.user_login:
            return []
        rows = _as_dicts(
            fetch_employee_action_details(
                conn,
                date_from=scope.date_from,
                date_to=scope.date_to,
                user_login=scope.user_login,
                object_type=scope.object_type,
                user_role=scope.user_role,
            )
        )
        return _filter_rows_by_rayon(rows, "rayon", scope.rayons)
    if dataset_id == "closed_orders":
        return fetch_closed_orders(conn, scope, filters)
    if dataset_id == "closed_tasks":
        return fetch_closed_tasks_in_orders(conn, parent_keys, filters)
    if dataset_id == "active_tasks_in_orders":
        return fetch_active_tasks_in_orders(conn, parent_keys)
    if dataset_id == "surveyed_order_summary":
        return fetch_surveyed_order_summary(conn, scope)
    raise ReportError(f"Неизвестный набор данных: {dataset_id}")


def _as_dicts(rows: list[Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _filter_rows_by_rayon(
    rows: list[dict[str, Any]],
    field_name: str,
    rayons: tuple[str, ...],
) -> list[dict[str, Any]]:
    wanted = set(_normalized_rayons(rayons))
    if not wanted:
        return rows
    return [
        row
        for row in rows
        if normalize_rayon_name(str(row.get(field_name) or "")) in wanted
    ]


def _filter_geo_rayons(
    rows: list[dict[str, Any]],
    rayons: tuple[str, ...],
) -> list[dict[str, Any]]:
    wanted = set(_normalized_rayons(rayons))
    if not wanted:
        return rows
    return [
        row
        for row in rows
        if normalize_rayon_name(str(row.get("rayon") or "")) in wanted
        or (
            not row.get("rayon")
            and normalize_rayon_name(str(row.get("okrug") or "")) in wanted
        )
    ]


def fetch_closed_orders(
    conn: PgConnection,
    scope: QueryScope,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    from app.crm.statistics import STATISTICS_SCHEMA, STATISTICS_TABLE, _period_bounds

    start, end = _period_bounds(scope.date_from, scope.date_to)
    clauses = [
        "s.object_type = 'order'",
        "s.action = 'field_order_closed'",
        "s.created_at >= %s",
        "s.created_at <= %s",
    ]
    params: list[Any] = [start, end]
    if scope.user_role:
        clauses.append("s.user_role = %s")
        params.append(scope.user_role)
    if scope.user_login:
        clauses.append("s.user_login = %s")
        params.append(scope.user_login.strip())

    statuses = [str(item) for item in (filters.get("status") or []) if str(item).strip()]
    if statuses:
        placeholders = ", ".join(["%s"] * len(statuses))
        clauses.append(f"ta.status IN ({placeholders})")
        params.extend(statuses)

    rayon_sql, rayon_params = _rayon_in_sql("ta.rayon", _normalized_rayons(scope.rayons))
    if rayon_params:
        clauses.append(rayon_sql)
        params.extend(rayon_params)

    where = " AND ".join(clauses)
    query = f"""
        SELECT
            ta.key::text AS order_key,
            ta.task_number,
            ta.rayon,
            ta.status,
            s.created_at AS closed_at,
            s.user_login AS closed_by,
            COALESCE(ta.area, 0) / 10000.0 AS area_hectares,
            ta.executor,
            fs.order_score
        FROM "{STATISTICS_SCHEMA}"."{STATISTICS_TABLE}" s
        JOIN crm.tasks_area ta ON s.object_key = ta.key
        LEFT JOIN crm.field_score fs ON fs.order_key = ta.key
        WHERE {where}
        ORDER BY s.created_at DESC, ta.task_number
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        _iso_datetime(row, "closed_at")
        area = row.get("area_hectares")
        row["area_hectares"] = 0.0 if area is None else float(area)
        number = row.get("task_number")
        row["task_number"] = str(number).strip() if number is not None else None
        rayon = row.get("rayon")
        row["rayon"] = str(rayon).strip() if rayon else None
        executor = row.get("executor")
        row["executor"] = str(executor).strip() if executor else None
        score = row.get("order_score")
        row["order_score"] = str(score).strip() if score else None
    return rows


def fetch_closed_tasks_in_orders(
    conn: PgConnection,
    parent_keys: list[str],
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    if not parent_keys:
        return []
    sources = [str(item) for item in (filters.get("sources") or []) if str(item).strip()]
    if not sources:
        sources = ["done_legal", "done_illegal"]

    snap_parts: list[str] = []
    for source in sources:
        mapping = SNAPSHOT_SOURCE_MAP.get(source)
        if mapping is None:
            continue
        schema, table = _snapshot_table(*mapping)
        snap_parts.append(
            f"""
            SELECT
                '{source}' AS closure_kind,
                sn.task_key,
                sn.type AS group_name,
                sn.sent_at,
                COALESCE(sn.is_field_data, FALSE) AS is_field_data,
                COALESCE(sn.is_office_task, FALSE) AS is_office_task,
                {ID_COLUMN_SQL}
            FROM "{schema}"."{table}" sn
            """
        )
    if not snap_parts:
        return []

    geom_union = _task_geom_union_sql()
    snaps_sql = " UNION ALL ".join(snap_parts)
    query = f"""
        WITH orders AS (
            SELECT
                ta.key,
                ta.task_number,
                ta.rayon,
                ta.geom
            FROM crm.tasks_area ta
            WHERE ta.key = ANY(%s::uuid[])
              AND ta.geom IS NOT NULL
        ),
        snaps AS (
            {snaps_sql}
        ),
        geoms AS (
            SELECT task_key, geom
            FROM ({geom_union}) g
            WHERE g.task_key IS NOT NULL AND g.geom IS NOT NULL
        )
        SELECT DISTINCT ON (o.key, sn.task_key, sn.closure_kind)
            o.key::text AS order_key,
            o.task_number AS order_task_number,
            o.rayon AS order_rayon,
            sn.closure_kind,
            sn.group_name,
            sn.task_key::text AS task_key,
            sn.sent_at,
            sn.is_field_data,
            sn.is_office_task,
            {", ".join(f"sn.{col}" for col in TASK_ID_COLUMNS)}
        FROM snaps sn
        JOIN geoms g ON g.task_key = sn.task_key
        JOIN orders o
          ON o.geom && ST_Transform(g.geom, 4326)
         AND ST_Intersects(ST_Transform(g.geom, 4326), o.geom)
        ORDER BY o.key, sn.task_key, sn.closure_kind, sn.sent_at DESC
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (parent_keys,))
        rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        _iso_datetime(row, "sent_at")
        number = row.get("order_task_number")
        row["order_task_number"] = str(number).strip() if number is not None else None
        rayon = row.get("order_rayon")
        row["order_rayon"] = str(rayon).strip() if rayon else None
        row["is_field_data"] = bool(row.get("is_field_data"))
        row["is_office_task"] = bool(row.get("is_office_task"))
        for col in TASK_ID_COLUMNS:
            value = row.get(col)
            row[col] = str(value).strip() if value not in (None, "") else None
    return rows


def fetch_active_tasks_in_orders(
    conn: PgConnection,
    parent_keys: list[str],
) -> list[dict[str, Any]]:
    if not parent_keys:
        return []
    geom_union = _task_geom_union_sql()
    query = f"""
        WITH orders AS (
            SELECT
                ta.key,
                ta.task_number,
                ta.rayon,
                ta.geom
            FROM crm.tasks_area ta
            WHERE ta.key = ANY(%s::uuid[])
              AND ta.geom IS NOT NULL
        ),
        geoms AS (
            SELECT task_key, geom
            FROM ({geom_union}) g
            WHERE g.task_key IS NOT NULL AND g.geom IS NOT NULL
        )
        SELECT DISTINCT ON (o.key, t.key)
            o.key::text AS order_key,
            o.task_number AS order_task_number,
            o.rayon AS order_rayon,
            t.type AS group_name,
            t.key::text AS task_key,
            t.field_observed,
            COALESCE(t.is_field_data, FALSE) AS is_field_data,
            COALESCE(t.is_office_task, FALSE) AS is_office_task,
            {ACTIVE_ID_COLUMN_SQL}
        FROM crm.tasks t
        JOIN geoms g ON g.task_key = t.key
        JOIN orders o
          ON o.geom && ST_Transform(g.geom, 4326)
         AND ST_Intersects(ST_Transform(g.geom, 4326), o.geom)
        ORDER BY o.key, t.key
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (parent_keys,))
        rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        number = row.get("order_task_number")
        row["order_task_number"] = str(number).strip() if number is not None else None
        rayon = row.get("order_rayon")
        row["order_rayon"] = str(rayon).strip() if rayon else None
        observed = row.get("field_observed")
        row["field_observed"] = None if observed is None else bool(observed)
        row["is_field_data"] = bool(row.get("is_field_data"))
        row["is_office_task"] = bool(row.get("is_office_task"))
        for col in TASK_ID_COLUMNS:
            value = row.get(col)
            row[col] = str(value).strip() if value not in (None, "") else None
    return rows


def resolve_surveyed_task_outcome(kinds: list[str] | set[str] | tuple[str, ...]) -> str | None:
    """Pick the latest outcome: illegal > legal > clear > still open."""
    kind_set = {str(item) for item in kinds if item}
    for kind in SURVEYED_OUTCOME_PRIORITY:
        if kind in kind_set:
            return kind
    return None


def aggregate_surveyed_order_counts(
    snapshot_rows: list[dict[str, Any]],
    active_rows: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    """Group field-surveyed tasks by order and count mutually exclusive outcomes."""
    kinds_by_order_task: dict[tuple[str, str], set[str]] = {}
    for row in snapshot_rows:
        order_key = str(row.get("order_key") or "").strip()
        task_key = str(row.get("task_key") or "").strip()
        kind = str(row.get("closure_kind") or "").strip()
        if not order_key or not task_key or not kind:
            continue
        kinds_by_order_task.setdefault((order_key, task_key), set()).add(kind)

    snapshotted = set(kinds_by_order_task)
    for row in active_rows:
        if row.get("field_observed") is not True:
            continue
        order_key = str(row.get("order_key") or "").strip()
        task_key = str(row.get("task_key") or "").strip()
        if not order_key or not task_key:
            continue
        key = (order_key, task_key)
        if key in snapshotted:
            continue
        kinds_by_order_task.setdefault(key, set()).add("open")

    counts: dict[str, dict[str, int]] = {}
    for (order_key, _task_key), kinds in kinds_by_order_task.items():
        outcome = resolve_surveyed_task_outcome(kinds)
        if outcome is None:
            continue
        bucket = counts.setdefault(order_key, dict(EMPTY_SURVEYED_COUNTS))
        bucket["tasks_surveyed"] += 1
        if outcome == "clear":
            bucket["tasks_clear"] += 1
        elif outcome == "done_legal":
            bucket["tasks_done_legal"] += 1
        elif outcome == "done_illegal":
            bucket["tasks_done_illegal"] += 1
        elif outcome == "open":
            bucket["tasks_open"] += 1
    return counts


def fetch_surveyed_orders(conn: PgConnection, scope: QueryScope) -> list[dict[str, Any]]:
    """All field_order_closed orders (no date filter); one row per order, latest event."""
    from app.crm.statistics import STATISTICS_SCHEMA, STATISTICS_TABLE

    clauses = [
        "s.object_type = 'order'",
        "s.action = 'field_order_closed'",
    ]
    params: list[Any] = []
    if scope.user_role:
        clauses.append("s.user_role = %s")
        params.append(scope.user_role)
    if scope.user_login:
        clauses.append("s.user_login = %s")
        params.append(scope.user_login.strip())

    rayon_sql, rayon_params = _rayon_in_sql("ta.rayon", _normalized_rayons(scope.rayons))
    if rayon_params:
        clauses.append(rayon_sql)
        params.extend(rayon_params)

    where = " AND ".join(clauses)
    query = f"""
        SELECT *
        FROM (
            SELECT DISTINCT ON (ta.key)
                ta.key::text AS order_key,
                ta.task_number,
                ta.rayon,
                s.created_at AS closed_at,
                s.user_login AS closed_by,
                COALESCE(ta.area, 0) / 10000.0 AS area_hectares,
                COALESCE(ta.pre_analise, FALSE) AS pre_analise,
                COALESCE(ta.analise, FALSE) AS analise
            FROM "{STATISTICS_SCHEMA}"."{STATISTICS_TABLE}" s
            JOIN crm.tasks_area ta ON s.object_key = ta.key
            WHERE {where}
            ORDER BY ta.key, s.created_at DESC
        ) orders
        ORDER BY closed_at DESC, task_number
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        _iso_datetime(row, "closed_at")
        area = row.get("area_hectares")
        row["area_hectares"] = 0.0 if area is None else float(area)
        number = row.get("task_number")
        row["task_number"] = str(number).strip() if number is not None else None
        rayon = row.get("rayon")
        row["rayon"] = str(rayon).strip() if rayon else None
        closed_by = row.get("closed_by")
        row["closed_by"] = str(closed_by).strip() if closed_by else None
        row["pre_analise"] = bool(row.get("pre_analise"))
        row["analise"] = bool(row.get("analise"))
    return rows


def _chunked_keys(keys: list[str], size: int = TASK_QUERY_CHUNK) -> list[list[str]]:
    if size <= 0:
        return [keys] if keys else []
    return [keys[index : index + size] for index in range(0, len(keys), size)]


def fetch_surveyed_order_summary(
    conn: PgConnection,
    scope: QueryScope,
) -> list[dict[str, Any]]:
    orders = fetch_surveyed_orders(conn, scope)
    keys: list[str] = []
    seen: set[str] = set()
    for row in orders:
        key = str(row.get("order_key") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        keys.append(key)

    snapshot_rows: list[dict[str, Any]] = []
    active_rows: list[dict[str, Any]] = []
    sources_filter = {"sources": list(SURVEYED_TASK_SOURCES)}
    for chunk in _chunked_keys(keys):
        snapshot_rows.extend(
            fetch_closed_tasks_in_orders(conn, chunk, sources_filter)
        )
        active_rows.extend(fetch_active_tasks_in_orders(conn, chunk))

    counts_by_order = aggregate_surveyed_order_counts(snapshot_rows, active_rows)
    for row in orders:
        counts = counts_by_order.get(str(row.get("order_key") or ""))
        row.update(dict(counts if counts is not None else EMPTY_SURVEYED_COUNTS))
    return orders


def _iso_datetime(row: dict[str, Any], key: str) -> None:
    value = row.get(key)
    if hasattr(value, "isoformat"):
        row[key] = value.isoformat()
