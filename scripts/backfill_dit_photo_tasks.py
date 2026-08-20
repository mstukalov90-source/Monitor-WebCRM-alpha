#!/usr/bin/env python3
"""One-shot insert of DIT AI photo tasks into crm.tasks.

Future rows are owned by ETL. WebCRM only JOINs existing crm.tasks (etl_sync).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import crm_task_store_config  # noqa: E402
from app.crm.etl_photo_loader import DIT_PHOTO_SUBGROUP  # noqa: E402
from app.crm.store import (  # noqa: E402
    CRM_GROUP_DISRUPTIONS,
    backfill_source_layer_tasks,
    ensure_tasks_table,
)
from app.db import get_connection  # noqa: E402
from app.layers.registry import get_registry  # noqa: E402

DIT_LAYER_NAME = "Фотографии после обработки ИИ (ДИТ)"


def _dit_layer():
    layer = get_registry().by_display_name.get(DIT_LAYER_NAME)
    if layer is None:
        raise SystemExit(f"Layer not found: {DIT_LAYER_NAME}")
    return layer


def count_source_and_existing(conn) -> tuple[int, int]:
    layer = _dit_layer()
    store_cfg = crm_task_store_config()
    schema, table = store_cfg.get("schema", "crm"), store_cfg.get("table", "tasks")
    source_field = layer.primary_key or "result_id"
    geom_col = layer.geometry_column
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT count(*)
            FROM {layer.qualified_table} t
            WHERE t."{geom_col}" IS NOT NULL
              AND t."{source_field}" IS NOT NULL
              AND TRIM(t."{source_field}"::text) <> ''
            """
        )
        source_count = int(cur.fetchone()[0])
        cur.execute(
            f"""
            SELECT count(*)
            FROM "{schema}"."{table}"
            WHERE dit_result_id IS NOT NULL
            """
        )
        existing = int(cur.fetchone()[0])
    return source_count, existing


def run_apply(conn, login: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SET LOCAL statement_timeout = '5min'")
    store_cfg = crm_task_store_config()
    return backfill_source_layer_tasks(
        conn,
        CRM_GROUP_DISRUPTIONS,
        DIT_PHOTO_SUBGROUP,
        _dit_layer(),
        store_cfg,
        login,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--report", action="store_true", help="Count source rows vs existing tasks")
    group.add_argument("--apply", action="store_true", help="Insert missing DIT tasks once")
    parser.add_argument("--login", default="dit-backfill", help="Audit login for user_created")
    args = parser.parse_args()

    with get_connection() as conn:
        if args.apply and not ensure_tasks_table(conn):
            raise SystemExit("Failed to ensure crm.tasks (dit_result_id column/index)")
        try:
            source_count, existing = count_source_and_existing(conn)
        except Exception as exc:
            raise SystemExit(
                f"Cannot read dit_detect.ai_results / crm.tasks: {exc}"
            ) from exc
        print(f"dit_detect.ai_results with geom: {source_count}")
        print(f"crm.tasks with dit_result_id: {existing}")
        if args.report:
            return 0
        inserted = run_apply(conn, args.login)
        print(f"inserted: {inserted}")
        _, after = count_source_and_existing(conn)
        print(f"crm.tasks with dit_result_id after: {after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
