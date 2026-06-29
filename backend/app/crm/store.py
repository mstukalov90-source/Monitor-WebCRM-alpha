"""CRM task storage (ported from MONITOR_QGIS crm_task_store.py)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

from psycopg2.extensions import connection as PgConnection

from app.crm.statistics import log_statistic, skip_field_complete_trigger
from app.crm.user_audit import (
    USER_AUDIT_COLUMNS,
    make_user_audit,
    user_audit_migration_statements,
)

logger = logging.getLogger(__name__)

SendTaskSnapshotResult = Literal["inserted", "skipped", "deleted", "not_found"]
WorkflowStatus = Literal["active", "field", "clear", "done_legal", "done_illegal"]
WorkflowTarget = Literal["active", "field", "clear"]

_SNAPSHOT_STAT_ACTIONS: dict[str, str] = {
    "field_table": "task_sent_to_field",
    "done_legal_table": "task_closed_legal",
    "done_illegal_table": "task_closed_illegal",
    "clear_table": "task_marked_clear",
}

TASK_ID_COLUMNS = (
    "photo_uuid",
    "photo_lens",
    "ogh_id",
    "oati_id",
    "earthwork_id",
    "localwork_id",
    "avr_mos_id",
)

CRM_GROUP_DISRUPTIONS = "Разрытия"
CRM_GROUP_ORDERS = "Новые ордера ОАТИ, АВР и земляные работы"
FIELD_DATA_SUBGROUP = "Полевые данные"

LINK_COLUMNS_BY_GROUP = {
    CRM_GROUP_DISRUPTIONS: (
        "oati_id",
        "earthwork_id",
        "localwork_id",
        "avr_mos_id",
    ),
    CRM_GROUP_ORDERS: ("photo_uuid", "photo_lens", "ogh_id"),
}

STATION_COLUMNS = ("sps", "kgs", "station_avr")

_TASK_SELECT_COLUMNS = (
    ("key", "type")
    + TASK_ID_COLUMNS
    + STATION_COLUMNS
    + ("field_observed", "is_field_data")
    + USER_AUDIT_COLUMNS
)


def _task_select_columns_sql() -> str:
    return ", ".join(f'"{col}"' for col in _TASK_SELECT_COLUMNS)

TASK_COLUMN_LABELS = {
    "key": "Ключ задачи",
    "type": "Тип",
    "photo_uuid": "Фото ИИ",
    "photo_lens": "Фото Объектив",
    "ogh_id": "ОГХ",
    "oati_id": "ОАТИ",
    "earthwork_id": "Земляные работы",
    "localwork_id": "Локальные ремонты",
    "avr_mos_id": "АВР",
    "sps": "СПС",
    "kgs": "КГС",
    "station_avr": "АВР",
    "field_observed": "Обследовано в поле",
    "is_field_data": "Полевые данные",
    "user_created": "Создал",
    "user_last_edit": "Изменил",
}

_DDL_STATEMENTS = (
    "CREATE SCHEMA IF NOT EXISTS crm",
    """
    CREATE TABLE IF NOT EXISTS crm.tasks (
        key UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        type TEXT NOT NULL,
        photo_uuid TEXT,
        photo_lens TEXT,
        ogh_id TEXT,
        oati_id TEXT,
        earthwork_id TEXT,
        localwork_id TEXT,
        avr_mos_id TEXT,
        sps TEXT,
        kgs TEXT,
        station_avr TEXT
    )
    """,
)

_DROP_TASK_ID_UNIQUE_INDEXES = (
    "DROP INDEX IF EXISTS crm.tasks_uq_photo_uuid",
    "DROP INDEX IF EXISTS crm.tasks_uq_photo_lens",
    "DROP INDEX IF EXISTS crm.tasks_uq_ogh_id",
    "DROP INDEX IF EXISTS crm.tasks_uq_oati_id",
    "DROP INDEX IF EXISTS crm.tasks_uq_earthwork_id",
    "DROP INDEX IF EXISTS crm.tasks_uq_localwork_id",
    "DROP INDEX IF EXISTS crm.tasks_uq_avr_mos_id",
)


def _station_migration_statements(schema: str, table: str) -> Tuple[str, ...]:
    return tuple(
        f'ALTER TABLE "{schema}"."{table}" '
        f'ADD COLUMN IF NOT EXISTS "{col}" TEXT'
        for col in STATION_COLUMNS
    ) + (
        f'ALTER TABLE "{schema}"."{table}" '
        f"ADD COLUMN IF NOT EXISTS field_observed BOOLEAN",
    ) + (
        f'ALTER TABLE "{schema}"."{table}" '
        f"ADD COLUMN IF NOT EXISTS is_field_data BOOLEAN NOT NULL DEFAULT false",
    ) + user_audit_migration_statements(schema, table)


def _snapshot_ddl_statements(
    schema: str, tasks_table: str, snapshot_table: str
) -> Tuple[str, ...]:
    index_name = f"{snapshot_table}_uq_task_key"
    return (
        "CREATE SCHEMA IF NOT EXISTS crm",
        f"""
        CREATE TABLE IF NOT EXISTS "{schema}"."{snapshot_table}" (
            key UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            task_key UUID NOT NULL REFERENCES "{schema}"."{tasks_table}"(key),
            type TEXT NOT NULL,
            photo_uuid TEXT,
            photo_lens TEXT,
            ogh_id TEXT,
            oati_id TEXT,
            earthwork_id TEXT,
            localwork_id TEXT,
            avr_mos_id TEXT,
            sps TEXT,
            kgs TEXT,
            station_avr TEXT,
            sent_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {index_name}
            ON "{schema}"."{snapshot_table}" (task_key)
        """,
    )


ILLEGAL_CLOSE_REQUIRES_FIELD_SURVEY = "Не проведено полевое обследование."


@dataclass
class PersistStats:
    inserted: int = 0
    skipped: int = 0
    invalid: int = 0


@dataclass
class TaskRecord:
    key: str
    type: str
    photo_uuid: Optional[str] = None
    photo_lens: Optional[str] = None
    ogh_id: Optional[str] = None
    oati_id: Optional[str] = None
    earthwork_id: Optional[str] = None
    localwork_id: Optional[str] = None
    avr_mos_id: Optional[str] = None
    sps: Optional[str] = None
    kgs: Optional[str] = None
    station_avr: Optional[str] = None
    field_observed: Optional[bool] = None
    is_field_data: Optional[bool] = None
    user_created: Optional[List[str]] = None
    user_last_edit: Optional[List[str]] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "type": self.type,
            "photo_uuid": self.photo_uuid,
            "photo_lens": self.photo_lens,
            "ogh_id": self.ogh_id,
            "oati_id": self.oati_id,
            "earthwork_id": self.earthwork_id,
            "localwork_id": self.localwork_id,
            "avr_mos_id": self.avr_mos_id,
            "sps": self.sps,
            "kgs": self.kgs,
            "station_avr": self.station_avr,
            "field_observed": self.field_observed,
            "is_field_data": self.is_field_data,
            "user_created": self.user_created,
            "user_last_edit": self.user_last_edit,
        }

    @classmethod
    def from_row(cls, row: Tuple) -> "TaskRecord":
        field_observed = None
        if len(row) > 12 and row[12] is not None:
            field_observed = bool(row[12])
        is_field_data = None
        if len(row) > 13 and row[13] is not None:
            is_field_data = bool(row[13])
        user_created = list(row[14]) if len(row) > 14 and row[14] is not None else None
        user_last_edit = list(row[15]) if len(row) > 15 and row[15] is not None else None
        return cls(
            key=str(row[0]),
            type=row[1] or "",
            photo_uuid=_normalize_id_value(row[2]),
            photo_lens=_normalize_id_value(row[3]),
            ogh_id=_normalize_id_value(row[4]),
            oati_id=_normalize_id_value(row[5]),
            earthwork_id=_normalize_id_value(row[6]),
            localwork_id=_normalize_id_value(row[7]),
            avr_mos_id=_normalize_id_value(row[8]),
            sps=_normalize_id_value(row[9]) if len(row) > 9 else None,
            kgs=_normalize_id_value(row[10]) if len(row) > 10 else None,
            station_avr=_normalize_id_value(row[11]) if len(row) > 11 else None,
            field_observed=field_observed,
            is_field_data=is_field_data,
            user_created=user_created,
            user_last_edit=user_last_edit,
        )


def ensure_tasks_table(conn: PgConnection) -> bool:
    schema, table = "crm", "tasks"
    try:
        with conn.cursor() as cur:
            for stmt in _DDL_STATEMENTS:
                cur.execute(stmt)
            for stmt in _station_migration_statements(schema, table):
                cur.execute(stmt)
            for stmt in _DROP_TASK_ID_UNIQUE_INDEXES:
                cur.execute(stmt)
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        logger.warning("Failed to ensure crm.tasks: %s", exc)
        return False


def _normalize_id_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def task_row_from_feature(
    group_name: str,
    subgroup_name: str,
    attributes: Dict[str, Any],
    store_cfg: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    mapping = store_cfg.get("subgroups", {}).get(subgroup_name)
    if not mapping:
        return None

    task_column = mapping.get("task_column")
    source_field = mapping.get("source_field")
    if task_column not in TASK_ID_COLUMNS or not source_field:
        return None

    business_id = _normalize_id_value(attributes.get(source_field))
    if business_id is None:
        return None

    row = {
        "type": group_name,
        "photo_uuid": None,
        "photo_lens": None,
        "ogh_id": None,
        "oati_id": None,
        "earthwork_id": None,
        "localwork_id": None,
        "avr_mos_id": None,
    }
    row[task_column] = business_id
    return row


def resolve_task_lookup(
    subgroup_name: str,
    attributes: Dict[str, Any],
    store_cfg: Dict[str, Any],
) -> Optional[Tuple[str, str]]:
    row = task_row_from_feature("", subgroup_name, attributes, store_cfg)
    if row is None:
        return None
    task_column = next(col for col in TASK_ID_COLUMNS if row[col] is not None)
    return task_column, row[task_column]


def _table_ref(store_cfg: Dict[str, Any]) -> Tuple[str, str]:
    return store_cfg.get("schema", "crm"), store_cfg.get("table", "tasks")


def _snapshot_table_ref(
    store_cfg: Dict[str, Any], config_key: str, default_table: str
) -> Tuple[str, str]:
    schema = store_cfg.get("schema", "crm")
    table = store_cfg.get(config_key, default_table)
    return schema, table


def ensure_task_snapshot_table(
    conn: PgConnection,
    store_cfg: Dict[str, Any],
    config_key: str,
    default_table: str,
) -> bool:
    if not ensure_tasks_table(conn):
        return False

    schema, tasks_table = _table_ref(store_cfg)
    snapshot_schema, snapshot_table = _snapshot_table_ref(
        store_cfg, config_key, default_table
    )
    try:
        with conn.cursor() as cur:
            for stmt in _snapshot_ddl_statements(schema, tasks_table, snapshot_table):
                cur.execute(stmt)
            for stmt in _station_migration_statements(snapshot_schema, snapshot_table):
                cur.execute(stmt)
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        logger.warning("Failed snapshot table %s.%s: %s", snapshot_schema, snapshot_table, exc)
        return False


def task_key_exists_in_snapshot(
    conn: PgConnection,
    store_cfg: Dict[str, Any],
    config_key: str,
    default_table: str,
    task_key: str,
) -> bool:
    schema, table = _snapshot_table_ref(store_cfg, config_key, default_table)
    query = f'SELECT 1 FROM "{schema}"."{table}" WHERE task_key = %s LIMIT 1'
    with conn.cursor() as cur:
        cur.execute(query, (task_key,))
        return cur.fetchone() is not None


_SNAPSHOT_TABLES = (
    ("field_table", "tasks_field"),
    ("done_legal_table", "tasks_done_legal"),
    ("done_illegal_table", "tasks_done_illegal"),
    ("clear_table", "tasks_clear"),
)


def fetch_snapshot_task_keys(
    conn: PgConnection,
    store_cfg: Dict[str, Any],
) -> Set[str]:
    keys: Set[str] = set()
    for config_key, default_table in _SNAPSHOT_TABLES:
        schema, table = _snapshot_table_ref(store_cfg, config_key, default_table)
        query = f'SELECT task_key FROM "{schema}"."{table}"'
        try:
            with conn.cursor() as cur:
                cur.execute(query)
                for row in cur.fetchall():
                    if row[0]:
                        keys.add(str(row[0]))
        except Exception:
            continue
    return keys


def fetch_active_task_summaries(
    conn: PgConnection,
    store_cfg: Dict[str, Any],
    *,
    limit: int = 2000,
) -> List[Tuple[str, str]]:
    """Активные задачи (не в snapshot-таблицах) — быстрый SQL без загрузки всей crm.tasks."""
    schema, table = _table_ref(store_cfg)
    exclusions: List[str] = []
    for config_key, default_table in _SNAPSHOT_TABLES:
        snap_schema, snap_table = _snapshot_table_ref(store_cfg, config_key, default_table)
        exclusions.append(
            f'NOT EXISTS (SELECT 1 FROM "{snap_schema}"."{snap_table}" s '
            f'WHERE s.task_key = t.key)'
        )
    where = " AND ".join(exclusions) if exclusions else "TRUE"
    query = f'''
        SELECT t.key::text, COALESCE(t.type, '') AS type
        FROM "{schema}"."{table}" t
        WHERE {where}
        ORDER BY t.key
        LIMIT %s
    '''
    with conn.cursor() as cur:
        cur.execute(query, (limit,))
        return [(str(row[0]), row[1] or "") for row in cur.fetchall()]


def fetch_task_types_by_keys(
    conn: PgConnection,
    store_cfg: Dict[str, Any],
    keys: List[str],
) -> Dict[str, str]:
    if not keys:
        return {}
    schema, table = _table_ref(store_cfg)
    query = f'SELECT key::text, COALESCE(type, \'\') FROM "{schema}"."{table}" WHERE key = ANY(%s::uuid[])'
    with conn.cursor() as cur:
        cur.execute(query, (keys,))
        return {str(row[0]): row[1] or "" for row in cur.fetchall()}


def fetch_task_keys_index(
    conn: PgConnection,
    store_cfg: Dict[str, Any],
) -> Dict[Tuple[str, str], str]:
    schema, table = _table_ref(store_cfg)
    col_list = ", ".join(f'"{col}"' for col in ("key",) + TASK_ID_COLUMNS)
    query = f'SELECT {col_list} FROM "{schema}"."{table}"'
    index: Dict[Tuple[str, str], str] = {}
    with conn.cursor() as cur:
        cur.execute(query)
        for row in cur.fetchall():
            key = str(row[0])
            for col_index, col in enumerate(TASK_ID_COLUMNS, start=1):
                value = _normalize_id_value(row[col_index])
                if value:
                    index[(col, value)] = key
    return index


def fetch_all_field_observed(
    conn: PgConnection,
    store_cfg: Dict[str, Any],
) -> Dict[str, Optional[bool]]:
    """Все field_observed из crm.tasks (key → bool|None)."""
    schema, table = _table_ref(store_cfg)
    query = f'SELECT key::text, field_observed FROM "{schema}"."{table}"'
    result: Dict[str, Optional[bool]] = {}
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            for row in cur.fetchall():
                key = str(row[0])
                result[key] = bool(row[1]) if row[1] is not None else None
    except Exception as exc:
        logger.warning("Failed to load field_observed from crm.tasks: %s", exc)
    return result


def enrich_features_field_observed(
    features: list,
    conn: PgConnection,
    store_cfg: Dict[str, Any],
    subgroup_name: str,
) -> None:
    if not features:
        return

    task_index = fetch_task_keys_index(conn, store_cfg)
    observed_map = fetch_all_field_observed(conn, store_cfg)

    for feat in features:
        if feat.layer_key == "tasks_area":
            continue
        key = feat.task_key
        if not key:
            lookup = resolve_task_lookup(subgroup_name, feat.attributes, store_cfg)
            if lookup:
                key = task_index.get(lookup)
                if key:
                    feat.task_key = key
        if not key:
            continue
        if key in observed_map and "field_observed" not in feat.attributes:
            feat.attributes["field_observed"] = observed_map[key]


def enrich_task_result_field_observed(
    task_result,
    conn: PgConnection,
    store_cfg: Dict[str, Any],
) -> None:
    """Заполнить attributes['field_observed'] и task_key для списков заказов."""
    for group in task_result.groups:
        for subgroup in group.subgroups:
            enrich_features_field_observed(
                subgroup.features, conn, store_cfg, subgroup.name
            )


def filter_sent_tasks_from_result(task_result, conn: PgConnection, store_cfg: Dict[str, Any]) -> int:
    snapshot_keys = fetch_snapshot_task_keys(conn, store_cfg)
    if not snapshot_keys:
        return 0

    task_index = fetch_task_keys_index(conn, store_cfg)
    hidden = 0

    for group in task_result.groups:
        for subgroup in group.subgroups:
            kept = []
            for feat in subgroup.features:
                task_key = feat.task_key
                if not task_key:
                    lookup = resolve_task_lookup(subgroup.name, feat.attributes, store_cfg)
                    if lookup:
                        task_key = task_index.get(lookup)
                if task_key and task_key in snapshot_keys:
                    hidden += 1
                    continue
                kept.append(feat)
            subgroup.features = kept
    return hidden


def filter_to_tasks_in_db(
    task_result,
    conn: PgConnection,
    store_cfg: Dict[str, Any],
) -> int:
    """Оставить только объекты, для которых есть строка в crm.tasks."""
    task_index = fetch_task_keys_index(conn, store_cfg)
    removed = 0
    if not task_index:
        for group in task_result.groups:
            for subgroup in group.subgroups:
                removed += len(subgroup.features)
                subgroup.features = []
        return removed

    for group in task_result.groups:
        for subgroup in group.subgroups:
            kept = []
            for feat in subgroup.features:
                lookup = resolve_task_lookup(
                    subgroup.name, feat.attributes, store_cfg
                )
                if lookup and lookup in task_index:
                    kept.append(feat)
                else:
                    removed += 1
            subgroup.features = kept
    return removed


def send_task_snapshot(
    conn: PgConnection,
    record: TaskRecord,
    store_cfg: Dict[str, Any],
    config_key: str,
    default_table: str,
    login: str,
    *,
    ensure_table: bool = True,
) -> SendTaskSnapshotResult:
    schema, table = _snapshot_table_ref(store_cfg, config_key, default_table)
    if ensure_table and not ensure_task_snapshot_table(conn, store_cfg, config_key, default_table):
        raise RuntimeError(f"Cannot prepare table {schema}.{table}")

    if task_key_exists_in_snapshot(conn, store_cfg, config_key, default_table, record.key):
        return "skipped"

    task_type = (record.type or "").strip()
    if not task_type:
        raise ValueError("type cannot be empty")

    audit = make_user_audit(login)
    columns = (
        ["task_key", "type"]
        + list(TASK_ID_COLUMNS)
        + list(STATION_COLUMNS)
        + ["is_field_data"]
        + list(USER_AUDIT_COLUMNS)
    )
    values = [record.key, task_type] + [
        _normalize_id_value(getattr(record, col)) for col in TASK_ID_COLUMNS
    ] + [
        _normalize_id_value(getattr(record, col)) for col in STATION_COLUMNS
    ] + [bool(record.is_field_data)] + [audit, audit]
    placeholders = ", ".join(["%s"] * len(columns))
    col_list = ", ".join(f'"{col}"' for col in columns)
    query = f'INSERT INTO "{schema}"."{table}" ({col_list}) VALUES ({placeholders})'

    try:
        with conn.cursor() as cur:
            cur.execute(query, values)
        if config_key in _SNAPSHOT_STAT_ACTIONS:
            log_statistic(
                conn,
                login=login,
                object_type="task",
                action=_SNAPSHOT_STAT_ACTIONS[config_key],
                object_key=record.key,
                metadata={"task_type": task_type},
            )
        conn.commit()
        return "inserted"
    except Exception:
        conn.rollback()
        raise


def send_task_to_field(
    conn: PgConnection,
    record: TaskRecord,
    store_cfg: Dict[str, Any],
    login: str,
    *,
    ensure_table: bool = True,
) -> SendTaskSnapshotResult:
    return send_task_snapshot(
        conn, record, store_cfg, "field_table", "tasks_field", login, ensure_table=ensure_table
    )


def send_task_to_done_legal(
    conn: PgConnection,
    record: TaskRecord,
    store_cfg: Dict[str, Any],
    login: str,
) -> SendTaskSnapshotResult:
    return send_task_snapshot(conn, record, store_cfg, "done_legal_table", "tasks_done_legal", login)


def send_task_to_done_illegal(
    conn: PgConnection,
    record: TaskRecord,
    store_cfg: Dict[str, Any],
    login: str,
) -> SendTaskSnapshotResult:
    if record.field_observed is False:
        raise ValueError(ILLEGAL_CLOSE_REQUIRES_FIELD_SURVEY)
    return send_task_snapshot(conn, record, store_cfg, "done_illegal_table", "tasks_done_illegal", login)


def send_task_to_clear(
    conn: PgConnection,
    record: TaskRecord,
    store_cfg: Dict[str, Any],
    login: str,
    *,
    ensure_table: bool = True,
) -> SendTaskSnapshotResult:
    return send_task_snapshot(
        conn, record, store_cfg, "clear_table", "tasks_clear", login, ensure_table=ensure_table
    )


def remove_task_from_field(
    conn: PgConnection,
    record: TaskRecord,
    store_cfg: Dict[str, Any],
    login: str,
    *,
    log_return_to_active: bool = True,
) -> SendTaskSnapshotResult:
    schema, table = _snapshot_table_ref(store_cfg, "field_table", "tasks_field")
    audit = make_user_audit(login)
    try:
        with skip_field_complete_trigger(conn):
            with conn.cursor() as cur:
                cur.execute(
                    f'DELETE FROM "{schema}"."{table}" WHERE task_key = %s::uuid RETURNING key',
                    (record.key,),
                )
                deleted = cur.fetchone()
                if deleted:
                    tasks_schema, tasks_table = _table_ref(store_cfg)
                    cur.execute(
                        f"""
                        UPDATE "{tasks_schema}"."{tasks_table}"
                        SET user_last_edit = %s::text[]
                        WHERE key = %s::uuid
                        """,
                        (audit, record.key),
                    )
                    if log_return_to_active:
                        log_statistic(
                            conn,
                            login=login,
                            object_type="task",
                            action="task_returned_to_active",
                            object_key=record.key,
                        )
        conn.commit()
        return "deleted" if deleted else "not_found"
    except Exception:
        conn.rollback()
        raise


def return_task_to_active(
    conn: PgConnection,
    record: TaskRecord,
    store_cfg: Dict[str, Any],
    login: str,
) -> SendTaskSnapshotResult:
    return remove_task_from_field(conn, record, store_cfg, login)


def remove_task_from_clear(
    conn: PgConnection,
    record: TaskRecord,
    store_cfg: Dict[str, Any],
    login: str,
) -> SendTaskSnapshotResult:
    schema, table = _snapshot_table_ref(store_cfg, "clear_table", "tasks_clear")
    audit = make_user_audit(login)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f'DELETE FROM "{schema}"."{table}" WHERE task_key = %s::uuid RETURNING key',
                (record.key,),
            )
            deleted = cur.fetchone()
            if deleted:
                tasks_schema, tasks_table = _table_ref(store_cfg)
                cur.execute(
                    f"""
                    UPDATE "{tasks_schema}"."{tasks_table}"
                    SET user_last_edit = %s::text[]
                    WHERE key = %s::uuid
                    """,
                    (audit, record.key),
                )
        conn.commit()
        return "deleted" if deleted else "not_found"
    except Exception:
        conn.rollback()
        raise


def detect_task_workflow_status(
    conn: PgConnection,
    store_cfg: Dict[str, Any],
    task_key: str,
) -> WorkflowStatus:
    for config_key, default_table, status in (
        ("field_table", "tasks_field", "field"),
        ("clear_table", "tasks_clear", "clear"),
        ("done_legal_table", "tasks_done_legal", "done_legal"),
        ("done_illegal_table", "tasks_done_illegal", "done_illegal"),
    ):
        if task_key_exists_in_snapshot(conn, store_cfg, config_key, default_table, task_key):
            return status  # type: ignore[return-value]
    return "active"


def fetch_workflow_status_map(
    conn: PgConnection,
    store_cfg: Dict[str, Any],
    task_keys: List[str],
) -> Dict[str, WorkflowStatus]:
    if not task_keys:
        return {}
    status_map: Dict[str, WorkflowStatus] = {key: "active" for key in task_keys}
    for config_key, default_table, status in (
        ("field_table", "tasks_field", "field"),
        ("clear_table", "tasks_clear", "clear"),
        ("done_legal_table", "tasks_done_legal", "done_legal"),
        ("done_illegal_table", "tasks_done_illegal", "done_illegal"),
    ):
        schema, table = _snapshot_table_ref(store_cfg, config_key, default_table)
        query = f'SELECT task_key::text FROM "{schema}"."{table}" WHERE task_key = ANY(%s::uuid[])'
        try:
            with conn.cursor() as cur:
                cur.execute(query, (task_keys,))
                for row in cur.fetchall():
                    key = str(row[0])
                    if key in status_map and status_map[key] == "active":
                        status_map[key] = status  # type: ignore[assignment]
        except Exception:
            continue
    return status_map


def set_task_workflow_status(
    conn: PgConnection,
    record: TaskRecord,
    store_cfg: Dict[str, Any],
    target: WorkflowTarget,
    login: str,
    *,
    current: WorkflowStatus | None = None,
    ensure_snapshot: bool = True,
) -> str:
    if current is None:
        current = detect_task_workflow_status(conn, store_cfg, record.key)
    if current in ("done_legal", "done_illegal"):
        raise ValueError("Закрытая задача недоступна для смены статуса")

    if target == "active":
        if current == "active":
            return "skipped"
        field_result = remove_task_from_field(conn, record, store_cfg, login)
        clear_result = remove_task_from_clear(conn, record, store_cfg, login)
        if field_result == "deleted" or clear_result == "deleted":
            return "updated"
        return "not_found"

    if target == "field":
        if current == "field":
            return "skipped"
        if current == "clear":
            remove_task_from_clear(conn, record, store_cfg, login)
        result = send_task_to_field(
            conn, record, store_cfg, login, ensure_table=ensure_snapshot
        )
        if result in ("inserted", "skipped"):
            log_statistic(
                conn,
                login=login,
                object_type="task",
                action="task_workflow_changed",
                object_key=record.key,
                metadata={"target": target, "from": current},
                skip_if_exists=False,
            )
            conn.commit()
            return "updated"
        return result

    if current == "clear":
        return "skipped"
    if current == "field":
        remove_task_from_field(
            conn, record, store_cfg, login, log_return_to_active=False
        )
    result = send_task_to_clear(
        conn, record, store_cfg, login, ensure_table=ensure_snapshot
    )
    if result in ("inserted", "skipped"):
        log_statistic(
            conn,
            login=login,
            object_type="task",
            action="task_workflow_changed",
            object_key=record.key,
            metadata={"target": target, "from": current},
            skip_if_exists=False,
        )
        conn.commit()
        return "updated"
    return result


def fetch_task(
    conn: PgConnection,
    store_cfg: Dict[str, Any],
    task_column: str,
    business_id: str,
) -> Optional[TaskRecord]:
    if task_column not in TASK_ID_COLUMNS:
        return None

    schema, table = _table_ref(store_cfg)
    columns = _task_select_columns_sql()
    query = f'SELECT {columns} FROM "{schema}"."{table}" WHERE "{task_column}" = %s LIMIT 1'
    with conn.cursor() as cur:
        cur.execute(query, (business_id,))
        row = cur.fetchone()
    return TaskRecord.from_row(row) if row else None


def _find_subgroup_for_record(
    record: TaskRecord,
    store_cfg: dict[str, Any],
) -> Optional[tuple[str, str, str]]:
    """Вернуть (subgroup_name, task_column, business_id)."""
    if record.is_field_data:
        return FIELD_DATA_SUBGROUP, "", ""

    for subgroup_name, mapping in store_cfg.get("subgroups", {}).items():
        if mapping.get("source") == "field_data":
            continue
        task_column = mapping.get("task_column")
        if task_column not in TASK_ID_COLUMNS:
            continue
        value = getattr(record, task_column, None)
        if value:
            return subgroup_name, task_column, value
    return None


def fetch_all_task_records(
    conn: PgConnection,
    store_cfg: Dict[str, Any],
) -> List[TaskRecord]:
    schema, table = _table_ref(store_cfg)
    columns = _task_select_columns_sql()
    query = f'SELECT {columns} FROM "{schema}"."{table}"'
    with conn.cursor() as cur:
        cur.execute(query)
        return [TaskRecord.from_row(row) for row in cur.fetchall()]


def fetch_tasks_by_keys(
    conn: PgConnection,
    store_cfg: Dict[str, Any],
    keys: List[str],
) -> Dict[str, TaskRecord]:
    if not keys:
        return {}
    schema, table = _table_ref(store_cfg)
    columns = _task_select_columns_sql()
    query = f'SELECT {columns} FROM "{schema}"."{table}" WHERE key = ANY(%s::uuid[])'
    result: Dict[str, TaskRecord] = {}
    with conn.cursor() as cur:
        cur.execute(query, (keys,))
        for row in cur.fetchall():
            record = TaskRecord.from_row(row)
            result[record.key] = record
    return result


def fetch_task_by_key(conn: PgConnection, store_cfg: Dict[str, Any], key: str) -> Optional[TaskRecord]:
    schema, table = _table_ref(store_cfg)
    columns = _task_select_columns_sql()
    query = f'SELECT {columns} FROM "{schema}"."{table}" WHERE key = %s LIMIT 1'
    with conn.cursor() as cur:
        cur.execute(query, (key,))
        row = cur.fetchone()
    return TaskRecord.from_row(row) if row else None


def fetch_task_for_feature(
    conn: PgConnection,
    subgroup_name: str,
    attributes: Dict[str, Any],
    store_cfg: Dict[str, Any],
) -> Optional[TaskRecord]:
    lookup = resolve_task_lookup(subgroup_name, attributes, store_cfg)
    if lookup is None:
        return None
    task_column, business_id = lookup
    return fetch_task(conn, store_cfg, task_column, business_id)


def resolve_primary_task_column(
    subgroup_name: Optional[str],
    store_cfg: Dict[str, Any],
    record: Optional[TaskRecord] = None,
) -> Optional[str]:
    if subgroup_name == FIELD_DATA_SUBGROUP:
        return None
    if record is not None and record.is_field_data:
        return None
    if subgroup_name:
        mapping = store_cfg.get("subgroups", {}).get(subgroup_name)
        if mapping:
            if mapping.get("source") == "field_data":
                return None
            task_column = mapping.get("task_column")
            if task_column in TASK_ID_COLUMNS:
                return task_column
    if record is not None:
        for col in TASK_ID_COLUMNS:
            if getattr(record, col):
                return col
    return None


def task_form_field_groups(
    group_name: Optional[str],
    subgroup_name: Optional[str],
    store_cfg: Dict[str, Any],
    record: TaskRecord,
) -> Tuple[List[str], List[str]]:
    if record.is_field_data or subgroup_name == FIELD_DATA_SUBGROUP:
        readonly: List[str] = ["type", "is_field_data"]
        link = list(LINK_COLUMNS_BY_GROUP.get(group_name or "", ()))
        return readonly, link

    primary = resolve_primary_task_column(subgroup_name, store_cfg, record)
    readonly: List[str] = ["type"]
    if primary:
        readonly.append(primary)
    link = list(LINK_COLUMNS_BY_GROUP.get(group_name or "", ()))
    return readonly, link


def update_task_record(
    conn: PgConnection,
    record: TaskRecord,
    store_cfg: Dict[str, Any],
    login: str,
) -> None:
    schema, table = _table_ref(store_cfg)
    task_type = (record.type or "").strip()
    if not task_type:
        raise ValueError("type cannot be empty")

    id_values = {col: _normalize_id_value(getattr(record, col)) for col in TASK_ID_COLUMNS}
    station_values = {col: _normalize_id_value(getattr(record, col)) for col in STATION_COLUMNS}
    audit = make_user_audit(login)

    try:
        with conn.cursor() as cur:
            all_columns = list(TASK_ID_COLUMNS) + list(STATION_COLUMNS)
            set_parts = (
                ['"type" = %s']
                + [f'"{col}" = %s' for col in all_columns]
                + ['"user_last_edit" = %s::text[]']
            )
            params: List[Any] = [task_type] + [
                id_values[col] for col in TASK_ID_COLUMNS
            ] + [station_values[col] for col in STATION_COLUMNS]
            params.append(audit)
            params.append(record.key)
            query = f'UPDATE "{schema}"."{table}" SET {", ".join(set_parts)} WHERE key = %s'
            cur.execute(query, params)
            if cur.rowcount == 0:
                raise ValueError(f"Task {record.key} not found")
            log_statistic(
                conn,
                login=login,
                object_type="task",
                action="task_updated",
                object_key=record.key,
                metadata={"task_type": task_type},
                skip_if_exists=False,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _task_exists(cur, schema: str, table: str, column: str, value: str) -> bool:
    query = f'SELECT 1 FROM "{schema}"."{table}" WHERE "{column}" = %s LIMIT 1'
    cur.execute(query, (value,))
    return cur.fetchone() is not None


def _insert_task(cur, schema: str, table: str, row: Dict[str, Any], login: str) -> None:
    audit = make_user_audit(login)
    columns = ["type"] + list(TASK_ID_COLUMNS) + list(USER_AUDIT_COLUMNS)
    values = [row["type"]] + [row[col] for col in TASK_ID_COLUMNS] + [audit, audit]
    placeholders = ", ".join(["%s"] * len(columns))
    col_list = ", ".join(f'"{col}"' for col in columns)
    query = f'INSERT INTO "{schema}"."{table}" ({col_list}) VALUES ({placeholders})'
    cur.execute(query, values)


def fetch_existing_business_ids_by_column(
    conn: PgConnection,
    store_cfg: Dict[str, Any],
) -> Dict[str, Set[str]]:
    schema, table = _table_ref(store_cfg)
    result: Dict[str, Set[str]] = {col: set() for col in TASK_ID_COLUMNS}
    col_list = ", ".join(f'"{col}"' for col in TASK_ID_COLUMNS)
    query = f'SELECT {col_list} FROM "{schema}"."{table}"'
    with conn.cursor() as cur:
        cur.execute(query)
        for row in cur.fetchall():
            for index, col in enumerate(TASK_ID_COLUMNS):
                value = _normalize_id_value(row[index])
                if value:
                    result[col].add(value)
    return result


def persist_new_tasks_in_district(
    conn: PgConnection,
    group_name: str,
    subgroup_name: str,
    layer: Any,
    store_cfg: Dict[str, Any],
    district_wkt: str,
    metric_srid: int,
    date_field: Optional[str],
    date_from: Optional["date"],
    date_to: Optional["date"],
    login: str,
) -> int:
    """INSERT ... SELECT новых задач слоя в районе (без выгрузки всех строк в Python)."""
    from app.layers.geojson import _district_spatial_filter

    mapping = store_cfg.get("subgroups", {}).get(subgroup_name)
    if not mapping:
        return 0

    task_column = mapping.get("task_column")
    source_field = mapping.get("source_field")
    if task_column not in TASK_ID_COLUMNS or not source_field:
        return 0

    schema, tasks_table = _table_ref(store_cfg)
    geom_col = layer.geometry_column
    spatial, spatial_params = _district_spatial_filter(
        layer, district_wkt, metric_srid, table_alias="t"
    )

    filters = [
        f't."{geom_col}" IS NOT NULL',
        spatial,
        f't."{source_field}" IS NOT NULL',
        f"""NOT EXISTS (
            SELECT 1 FROM "{schema}"."{tasks_table}" ct
            WHERE ct."{task_column}" = t."{source_field}"::text
        )""",
    ]
    if layer.sql_filter:
        filters.append(f"({layer.sql_filter})")

    params: List[Any] = list(spatial_params) + [group_name]
    audit = make_user_audit(login)
    if date_field and date_from and date_to:
        filters.append(f't."{date_field}"::date BETWEEN %s AND %s')
        params.extend([date_from, date_to])

    id_values = []
    for col in TASK_ID_COLUMNS:
        if col == task_column:
            id_values.append(f't."{source_field}"::text')
        else:
            id_values.append("NULL")

    insert_columns = ["type"] + list(TASK_ID_COLUMNS) + list(USER_AUDIT_COLUMNS)
    col_list = ", ".join(f'"{col}"' for col in insert_columns)
    query = f"""
        INSERT INTO "{schema}"."{tasks_table}" ({col_list})
        SELECT %s, {", ".join(id_values)}, %s::text[], %s::text[]
        FROM {layer.qualified_table} t
        WHERE {" AND ".join(filters)}
    """
    params.extend([audit, audit])

    with conn.cursor() as cur:
        cur.execute(query, params)
        inserted = cur.rowcount
    conn.commit()
    return inserted


def persist_task_result(
    conn: PgConnection,
    task_result,
    store_cfg: Dict[str, Any],
    login: str,
) -> PersistStats:
    stats = PersistStats()
    if not ensure_tasks_table(conn):
        return stats

    schema = store_cfg.get("schema", "crm")
    table = store_cfg.get("table", "tasks")

    try:
        with conn.cursor() as cur:
            for group in task_result.groups:
                for subgroup in group.subgroups:
                    for task_feat in subgroup.features:
                        row = task_row_from_feature(
                            group.name,
                            subgroup.name,
                            task_feat.attributes,
                            store_cfg,
                        )
                        if row is None:
                            stats.invalid += 1
                            continue

                        task_column = next(col for col in TASK_ID_COLUMNS if row[col] is not None)
                        business_id = row[task_column]

                        if _task_exists(cur, schema, table, task_column, business_id):
                            stats.skipped += 1
                            continue

                        _insert_task(cur, schema, table, row, login)
                        stats.inserted += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return stats
