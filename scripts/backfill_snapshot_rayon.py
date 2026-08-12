#!/usr/bin/env python3
"""Normalize rayon values in snapshot tables and align to odh_export.hood canonical names.

Usage:
  python scripts/backfill_snapshot_rayon.py --report
  python scripts/backfill_snapshot_rayon.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import crm_task_store_config  # noqa: E402
from app.db import get_connection  # noqa: E402
from app.layers.geojson import (  # noqa: E402
    list_districts,
    normalize_rayon_name,
    sql_normalize_rayon_expr,
)

SNAPSHOT_TABLES = (
    "tasks_field",
    "tasks_clear",
    "tasks_done_legal",
    "tasks_done_illegal",
    "tasks_delay",
)

AREA_TABLE = "tasks_area"


def _rayon_norm_sql(field: str = "rayon") -> str:
    return sql_normalize_rayon_expr(f'"{field}"')


def report_distinct_rayons(conn, schema: str, table: str) -> list[tuple[str, int]]:
    query = f"""
        SELECT rayon, count(*) AS cnt
        FROM "{schema}"."{table}"
        WHERE rayon IS NOT NULL AND trim(rayon) <> ''
        GROUP BY 1
        ORDER BY cnt DESC, rayon
    """
    with conn.cursor() as cur:
        cur.execute(query)
        return [(str(row[0]), int(row[1])) for row in cur.fetchall()]


def count_dirty_rayons(conn, schema: str, table: str) -> int:
    norm = _rayon_norm_sql()
    query = f"""
        SELECT count(*)
        FROM "{schema}"."{table}"
        WHERE rayon IS NOT NULL
          AND rayon IS DISTINCT FROM {norm}
    """
    with conn.cursor() as cur:
        cur.execute(query)
        row = cur.fetchone()
    return int(row[0]) if row else 0


def normalize_table_rayons(conn, schema: str, table: str) -> int:
    norm = _rayon_norm_sql()
    query = f"""
        UPDATE "{schema}"."{table}"
        SET rayon = {norm}
        WHERE rayon IS NOT NULL
          AND rayon IS DISTINCT FROM {norm}
    """
    with conn.cursor() as cur:
        cur.execute(query)
        updated = cur.rowcount
    conn.commit()
    return updated


def align_table_to_hood(conn, schema: str, table: str, hood_canonical: dict[str, str]) -> int:
    if not hood_canonical:
        return 0
    norm = _rayon_norm_sql()
    updated = 0
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT key::text, rayon
            FROM "{schema}"."{table}"
            WHERE rayon IS NOT NULL AND trim(rayon) <> ''
            """
        )
        rows = cur.fetchall()
        for key, rayon in rows:
            key_norm = normalize_rayon_name(str(rayon))
            canonical = hood_canonical.get(key_norm)
            if canonical and canonical != str(rayon):
                cur.execute(
                    f'UPDATE "{schema}"."{table}" SET rayon = %s WHERE key = %s::uuid',
                    (canonical, key),
                )
                updated += cur.rowcount
    conn.commit()
    return updated


def find_orphan_rayons(conn, schema: str, table: str, hood_norms: set[str]) -> list[str]:
    norm = _rayon_norm_sql()
    query = f"""
        SELECT DISTINCT {norm} AS rayon_norm
        FROM "{schema}"."{table}"
        WHERE rayon IS NOT NULL AND trim(rayon) <> ''
    """
    with conn.cursor() as cur:
        cur.execute(query)
        values = [str(row[0]) for row in cur.fetchall() if row[0]]
    return sorted(v for v in values if v not in hood_norms)


def hood_canonical_map(conn) -> dict[str, str]:
    districts = list_districts(conn)
    return {name: name for name in districts}


def run_report(conn, schema: str) -> None:
    hood = hood_canonical_map(conn)
    hood_norms = set(hood.keys())

    print("=== Chertanovo: tasks_field vs hood ===")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 'field' AS src, rayon, count(*)
            FROM crm.tasks_field
            WHERE rayon ILIKE '%Чертаново%'
            GROUP BY 2
            UNION ALL
            SELECT 'hood', rayon, 1
            FROM odh_export.hood
            WHERE rayon ILIKE '%Чертаново%'
            ORDER BY 1, 2
            """
        )
        for src, rayon, cnt in cur.fetchall():
            print(f"  {src}: {repr(rayon)} ({cnt})")

    for table in (*SNAPSHOT_TABLES, AREA_TABLE):
        dirty = count_dirty_rayons(conn, schema, table)
        orphans = find_orphan_rayons(conn, schema, table, hood_norms)
        print(f"\n=== {schema}.{table} ===")
        print(f"  rows needing whitespace normalize: {dirty}")
        print(f"  orphan rayon norms (no hood match): {len(orphans)}")
        if orphans:
            for name in orphans[:20]:
                print(f"    - {name}")
            if len(orphans) > 20:
                print(f"    ... and {len(orphans) - 20} more")
        if table == "tasks_field":
            print("  distinct rayon values:")
            for rayon, cnt in report_distinct_rayons(conn, schema, table)[:15]:
                marker = " *" if normalize_rayon_name(rayon) != rayon else ""
                print(f"    {repr(rayon)}: {cnt}{marker}")


def run_apply(conn, schema: str) -> None:
    hood = hood_canonical_map(conn)
    total_norm = 0
    total_align = 0
    for table in (*SNAPSHOT_TABLES, AREA_TABLE):
        norm_updated = normalize_table_rayons(conn, schema, table)
        align_updated = align_table_to_hood(conn, schema, table, hood)
        total_norm += norm_updated
        total_align += align_updated
        print(f"{schema}.{table}: normalized {norm_updated}, aligned to hood {align_updated}")

    hood_norms = set(hood.keys())
    orphans: list[str] = []
    for table in (*SNAPSHOT_TABLES, AREA_TABLE):
        orphans.extend(find_orphan_rayons(conn, schema, table, hood_norms))
    unique_orphans = sorted(set(orphans))
    print(f"\nTotal whitespace normalized: {total_norm}")
    print(f"Total aligned to hood: {total_align}")
    if unique_orphans:
        print(f"Remaining orphan rayon norms ({len(unique_orphans)}):")
        for name in unique_orphans:
            print(f"  - {name}")
    else:
        print("No orphan rayon values remain.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--report", action="store_true", help="Diagnostic report only")
    group.add_argument("--apply", action="store_true", help="Normalize and align rayon values")
    args = parser.parse_args()

    store_cfg = crm_task_store_config()
    schema = store_cfg.get("schema", "crm")

    with get_connection() as conn:
        if args.report:
            run_report(conn, schema)
        else:
            run_apply(conn, schema)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
