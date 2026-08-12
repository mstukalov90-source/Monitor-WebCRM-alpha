#!/usr/bin/env python3
"""Point repair for protect-set task_key / tasked on prod (only if preflight A is red).

Usage:
  ./scripts/etl_safety_repair.py --dry-run
  ./scripts/etl_safety_repair.py --apply
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTECT = ROOT / "tmp/kosolapov_etl_safety_20260812/protect_81.json"
DEFAULT_HOST = "172.21.198.219"

SPLIT_BY_COL = {
    "oati_id": [
        ("data_mos.items_2855_points", "point"),
        ("data_mos.items_2855_lines", "line"),
        ("data_mos.items_2855_polygons", "polygon"),
    ],
    "earthwork_id": [
        ("data_mos.items_62501_points", "point"),
        ("data_mos.items_62501_lines", "line"),
        ("data_mos.items_62501_polygons", "polygon"),
    ],
    "localwork_id": [
        ("data_mos.items_62441_points", "point"),
        ("data_mos.items_62441_lines", "line"),
        ("data_mos.items_62441_polygons", "polygon"),
    ],
    "avr_mos_id": [
        ("data_mos.items_62461_points", "point"),
        ("data_mos.items_62461_lines", "line"),
        ("data_mos.items_62461_polygons", "polygon"),
    ],
}


def psql(host: str, sql: str) -> str:
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=30",
        f"root@{host}",
        "docker",
        "exec",
        "-i",
        "monitor-db",
        "psql",
        "-U",
        "monitor",
        "-d",
        "monitor",
        "-v",
        "ON_ERROR_STOP=1",
        "-t",
        "-A",
    ]
    proc = subprocess.run(cmd, input=sql, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return proc.stdout


def keys_sql_array(keys: list[str]) -> str:
    return "ARRAY[" + ",".join(f"'{k}'::uuid" for k in keys) + "]"


def build_repair_sql(keys: list[str], apply: bool) -> str:
    arr = keys_sql_array(keys)
    stmts: list[str] = ["BEGIN;"]
    for col, layers in SPLIT_BY_COL.items():
        for table, geom_type in layers:
            # Link rows whose business id matches protect task and task_key is null/wrong
            stmts.append(
                f"""
-- link {table} via {col}
WITH protect_tasks AS (
  SELECT key, "{col}" AS business_id
  FROM crm.tasks
  WHERE key = ANY({arr})
    AND "{col}" IS NOT NULL
    AND COALESCE(is_field_data, false) IS NOT TRUE
)
UPDATE {table} t
SET task_key = pt.key
FROM protect_tasks pt
WHERE t.task_key IS DISTINCT FROM pt.key
  AND t.geom IS NOT NULL
  AND CONCAT('{geom_type}:', t.id::text) = pt.business_id
  AND NOT EXISTS (
    SELECT 1 FROM {table} occupied
    WHERE occupied.task_key = pt.key AND occupied.id <> t.id
  );
"""
            )
            parent = table.rsplit("_", 1)[0]
            # tasked=true for parents of protect links
            stmts.append(
                f"""
UPDATE {parent} p
SET tasked = true
WHERE p.id IN (
  SELECT t.source_id FROM {table} t
  WHERE t.task_key = ANY({arr}) AND t.source_id IS NOT NULL
)
AND p.tasked IS NOT TRUE;
"""
            )
    if apply:
        stmts.append("COMMIT;")
    else:
        stmts.append("ROLLBACK;")
    return "\n".join(stmts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--protect", type=Path, default=DEFAULT_PROTECT)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true", default=True)
    args = ap.parse_args()
    if args.apply:
        args.dry_run = False

    protect = json.loads(args.protect.read_text())
    keys = protect["task_keys"]
    sql = build_repair_sql(keys, apply=not args.dry_run)
    out = ROOT / "tmp/kosolapov_etl_safety_20260812/notes/repair.sql"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sql)
    print(f"wrote {out} apply={not args.dry_run}")
    result = psql(args.host, sql)
    print(result)
    print("DONE" if args.apply else "DRY-RUN rolled back")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
