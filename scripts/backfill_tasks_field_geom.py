#!/usr/bin/env python3
"""Backfill tasks_field.geom from items_* by task_key."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import crm_task_store_config  # noqa: E402
from app.db import get_connection  # noqa: E402
from app.layers.geojson import fetch_geometry_by_task_key  # noqa: E402


def main() -> int:
    store_cfg = crm_task_store_config()
    updated = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT task_key::text
                FROM crm.tasks_field
                WHERE geom IS NULL
                """
            )
            keys = [row[0] for row in cur.fetchall()]
        for task_key in keys:
            geom = fetch_geometry_by_task_key(conn, task_key, store_cfg)
            if not geom:
                continue
            import json

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE crm.tasks_field
                    SET geom = ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)
                    WHERE task_key = %s::uuid AND geom IS NULL
                    """,
                    (json.dumps(geom), task_key),
                )
                updated += cur.rowcount
            conn.commit()
    print(f"Updated geom for {updated} tasks_field rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
