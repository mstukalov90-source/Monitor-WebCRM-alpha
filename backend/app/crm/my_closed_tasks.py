"""Office user's closed-task snapshots (done_legal / done_illegal / clear)."""

from __future__ import annotations

import logging
from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.crm.store import (
    _find_subgroup_for_record,
    _snapshot_table_ref,
    ensure_rayon_column,
    fetch_tasks_by_keys,
)

logger = logging.getLogger(__name__)

CLOSED_SNAPSHOTS = (
    ("done_legal_table", "tasks_done_legal", "done_legal"),
    ("done_illegal_table", "tasks_done_illegal", "done_illegal"),
    ("clear_table", "tasks_clear", "clear"),
)


def fetch_can_return_map(
    conn: PgConnection,
    store_cfg: dict[str, Any],
    task_keys: list[str],
) -> dict[str, bool]:
    """True if the task sits in a crm.tasks_area polygon with analise not finished."""
    del store_cfg
    result: dict[str, bool] = {key: False for key in task_keys}
    if not task_keys:
        return result

    from app.crm.tasks_area import _task_geom_union_sql

    geom_union = _task_geom_union_sql()
    query = f"""
        SELECT DISTINCT ON (g.task_key)
               g.task_key::text AS task_key,
               COALESCE(a.analise, FALSE) = FALSE AS can_return
        FROM ({geom_union}) g
        INNER JOIN crm.tasks_area a
          ON a.geom IS NOT NULL
         AND g.geom IS NOT NULL
         AND ST_Contains(a.geom, ST_Centroid(g.geom))
        WHERE g.task_key = ANY(%s::uuid[])
        ORDER BY g.task_key, COALESCE(a.area, 1e99) ASC, a.key ASC
    """
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (task_keys,))
            for row in cur.fetchall():
                key = str(row["task_key"])
                if key in result:
                    result[key] = bool(row["can_return"])
    except Exception:
        logger.exception("Failed to resolve containing area orders for closed tasks")
        try:
            conn.rollback()
        except Exception:
            pass
    return result


def containing_order_allows_return(
    conn: PgConnection,
    store_cfg: dict[str, Any],
    task_key: str,
) -> bool:
    return fetch_can_return_map(conn, store_cfg, [task_key]).get(task_key, False)


def _login_owns_snapshot_sql() -> str:
    return """
        (
            (user_last_edit IS NOT NULL AND NULLIF(TRIM(user_last_edit[1]), '') = %s)
            OR (user_created IS NOT NULL AND NULLIF(TRIM(user_created[1]), '') = %s)
        )
    """


def _fetch_closed_snapshot_rows(
    conn: PgConnection,
    store_cfg: dict[str, Any],
    login: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    owner_sql = _login_owns_snapshot_sql()
    seen: set[str] = set()
    for config_key, default_table, source in CLOSED_SNAPSHOTS:
        schema, table = _snapshot_table_ref(store_cfg, config_key, default_table)
        try:
            ensure_rayon_column(conn, schema, table)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f'''
                    SELECT task_key::text AS task_key, type, rayon
                    FROM "{schema}"."{table}"
                    WHERE {owner_sql}
                    ORDER BY sent_at DESC NULLS LAST
                    ''',
                    (login, login),
                )
                for row in cur.fetchall():
                    key = str(row["task_key"] or "")
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    rows.append(
                        {
                            "task_key": key,
                            "task_source": source,
                            "rayon": (row.get("rayon") or "") or "",
                            "type": (row.get("type") or "") or "",
                        }
                    )
        except Exception:
            logger.exception("Failed to list closed snapshot %s.%s", schema, table)
            try:
                conn.rollback()
            except Exception:
                pass
    return rows


def fetch_my_closed_tasks(
    conn: PgConnection,
    store_cfg: dict[str, Any],
    login: str,
) -> list[dict[str, Any]]:
    login = (login or "").strip()
    if not login:
        return []

    snapshot_rows = _fetch_closed_snapshot_rows(conn, store_cfg, login)
    if not snapshot_rows:
        return []

    keys = [row["task_key"] for row in snapshot_rows]
    records = fetch_tasks_by_keys(conn, store_cfg, keys)
    can_return = fetch_can_return_map(conn, store_cfg, keys)

    items: list[dict[str, Any]] = []
    for row in snapshot_rows:
        record = records.get(row["task_key"])
        if record is not None:
            resolved = _find_subgroup_for_record(record, store_cfg)
            task_name = resolved[0] if resolved else (record.type or row["type"] or "Задача")
        else:
            task_name = row["type"] or "Задача"
        items.append(
            {
                "task_key": row["task_key"],
                "rayon": str(row["rayon"] or "").strip(),
                "task_name": task_name,
                "task_source": row["task_source"],
                "can_return_to_active": bool(can_return.get(row["task_key"], False)),
            }
        )

    items.sort(key=lambda item: (item["rayon"].lower(), item["task_name"].lower()))
    return items
