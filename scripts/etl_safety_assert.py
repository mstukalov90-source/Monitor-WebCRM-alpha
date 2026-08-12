#!/usr/bin/env python3
"""Read-only ETL safety assert for Kosolapov protect task keys on prod.

Usage:
  ./scripts/etl_safety_assert.py --mode pre
  ./scripts/etl_safety_assert.py --mode post --baseline tmp/.../baseline_pre_etl.json

Talks to prod via: ssh root@HOST 'docker exec -i monitor-db psql ...'
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTECT = ROOT / "tmp/kosolapov_etl_safety_20260812/protect_81.json"
DEFAULT_OUT_DIR = ROOT / "tmp/kosolapov_etl_safety_20260812/notes"
DEFAULT_HOST = "172.21.198.219"

SPLIT_TABLES = [
    "data_mos.items_2855_points",
    "data_mos.items_2855_lines",
    "data_mos.items_2855_polygons",
    "data_mos.items_62501_points",
    "data_mos.items_62501_lines",
    "data_mos.items_62501_polygons",
    "data_mos.items_62441_points",
    "data_mos.items_62441_lines",
    "data_mos.items_62441_polygons",
    "data_mos.items_62461_points",
    "data_mos.items_62461_lines",
    "data_mos.items_62461_polygons",
]

PARENT_TABLES = [
    "data_mos.items_2855",
    "data_mos.items_62501",
    "data_mos.items_62441",
    "data_mos.items_62461",
]

GEOM_HASH = "md5(ST_AsEWKB(ST_SetSRID(ST_MakeValid(geom), 4326)))"


def psql(host: str, sql: str, *, local: bool = False) -> str:
    if local:
        cmd = [
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
            "-F",
            "\t",
        ]
    else:
        # Keep remote argv as one shell string so -F '\t' survives SSH.
        remote = (
            "docker exec -i monitor-db psql -U monitor -d monitor "
            "-v ON_ERROR_STOP=1 -t -A -F $'\\t'"
        )
        cmd = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=30",
            f"root@{host}",
            remote,
        ]
    proc = subprocess.run(cmd, input=sql, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"psql failed ({proc.returncode}):\n{proc.stderr or proc.stdout}"
        )
    return proc.stdout


def load_protect(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    keys = data["task_keys"]
    if len(keys) != 81:
        raise SystemExit(f"expected 81 task_keys, got {len(keys)}")
    return data


def keys_sql_array(keys: list[str]) -> str:
    return "ARRAY[" + ",".join(f"'{k}'::uuid" for k in keys) + "]"


def split_union() -> str:
    parts = []
    for tbl in SPLIT_TABLES:
        parts.append(
            f"SELECT task_key, id, source_id, global_id, {GEOM_HASH} AS geom_hash, "
            f"'{tbl}'::text AS src FROM {tbl} WHERE task_key IS NOT NULL"
        )
    return "\nUNION ALL\n".join(parts)


def parent_for_split(split_table: str) -> str:
    # data_mos.items_2855_points -> data_mos.items_2855
    name = split_table.split(".", 1)[1]
    for suffix in ("_points", "_lines", "_polygons"):
        if name.endswith(suffix):
            return "data_mos." + name[: -len(suffix)]
    raise ValueError(split_table)


def run_assert(
    host: str, protect: dict[str, Any], *, local: bool = False
) -> dict[str, Any]:
    keys: list[str] = protect["task_keys"]
    remapped: list[str] = protect.get("remapped_prod_keys", [])
    expected = protect.get("expected", {})
    arr = keys_sql_array(keys)
    remapped_arr = keys_sql_array(remapped) if remapped else "ARRAY[]::uuid[]"

    def q(sql: str) -> str:
        return psql(host, sql, local=local)

    checks: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}

    # --- Block A ---
    sql_a = f"""
WITH protect AS (
  SELECT unnest({arr}) AS task_key
),
tasks AS (
  SELECT ct.key, ct.field_observed, COALESCE(ct.is_field_data, false) AS is_field_data,
         ct.oati_id, ct.earthwork_id, ct.localwork_id, ct.avr_mos_id
  FROM crm.tasks ct
  JOIN protect p ON p.task_key = ct.key
)
SELECT
  (SELECT COUNT(*) FROM protect) AS protect_n,
  (SELECT COUNT(*) FROM tasks) AS found_n,
  (SELECT COUNT(*) FROM tasks WHERE field_observed IS TRUE) AS observed_n,
  (SELECT COUNT(*) FROM crm.tasks_clear WHERE task_key IN (SELECT task_key FROM protect)) AS clear_n,
  (SELECT COUNT(DISTINCT tasks_key) FROM mggt_field.reports
     WHERE tasks_key IN (SELECT task_key FROM protect)) AS report_keys_n,
  (SELECT COUNT(*) FROM mggt_field.reports
     WHERE tasks_key IN (SELECT task_key FROM protect)) AS report_rows_n;
"""
    row = q(sql_a).strip().split("\t")
    (
        protect_n,
        found_n,
        observed_n,
        clear_n,
        report_keys_n,
        report_rows_n,
    ) = (int(x) for x in row)
    metrics.update(
        {
            "protect_n": protect_n,
            "found_n": found_n,
            "observed_n": observed_n,
            "clear_n": clear_n,
            "report_keys_n": report_keys_n,
            "report_rows_n": report_rows_n,
        }
    )
    exp_clear = int(expected.get("tasks_clear", 55))
    exp_reports = int(expected.get("reports", 81))
    checks.append(
        {
            "id": "A1_all_keys_exist",
            "ok": found_n == 81,
            "detail": f"found={found_n}/81",
        }
    )
    checks.append(
        {
            "id": "A2_field_observed",
            "ok": observed_n == 81,
            "detail": f"observed={observed_n}/81",
        }
    )
    checks.append(
        {
            "id": "A3_tasks_clear",
            "ok": clear_n == exp_clear,
            "detail": f"clear={clear_n} expected={exp_clear}",
        }
    )
    checks.append(
        {
            "id": "A4_reports",
            "ok": report_keys_n == exp_reports,
            "detail": f"report_keys={report_keys_n} rows={report_rows_n} expected={exp_reports}",
        }
    )

    # Missing keys
    missing = q(
        f"""
WITH protect AS (SELECT unnest({arr}) AS task_key)
SELECT p.task_key::text FROM protect p
LEFT JOIN crm.tasks ct ON ct.key = p.task_key
WHERE ct.key IS NULL
ORDER BY 1;
""",
    ).strip()
    missing_list = [x for x in missing.splitlines() if x.strip()]
    checks.append(
        {
            "id": "A1b_missing_keys",
            "ok": len(missing_list) == 0,
            "detail": missing_list[:20],
        }
    )

    # ETL tasks without link
    no_link_sql = f"""
WITH protect AS (SELECT unnest({arr}) AS task_key),
tasks AS (
  SELECT ct.key, COALESCE(ct.is_field_data, false) AS is_field_data
  FROM crm.tasks ct JOIN protect p ON p.task_key = ct.key
),
linked AS (
  SELECT DISTINCT task_key FROM (
    {split_union()}
  ) s WHERE task_key IN (SELECT task_key FROM protect)
)
SELECT t.key::text
FROM tasks t
LEFT JOIN linked l ON l.task_key = t.key
WHERE t.is_field_data IS NOT TRUE AND l.task_key IS NULL
ORDER BY 1;
"""
    no_link = [x for x in q(no_link_sql).strip().splitlines() if x.strip()]
    checks.append(
        {
            "id": "A5_etl_tasks_have_link",
            "ok": len(no_link) == 0,
            "detail": {"unlinked_etl_tasks": no_link[:30], "count": len(no_link)},
        }
    )

    # Parent tasked for protect links
    untasked_sql = f"""
WITH links AS (
  SELECT task_key, source_id, src FROM (
    {split_union()}
  ) s WHERE task_key IN (SELECT unnest({arr}))
),
parents AS (
"""
    parent_parts = []
    for split in SPLIT_TABLES:
        parent = parent_for_split(split)
        parent_parts.append(
            f"""
  SELECT l.task_key, l.source_id, '{parent}'::text AS parent_table, p.tasked
  FROM links l
  JOIN {parent} p ON p.id = l.source_id
  WHERE l.src = '{split}'
"""
        )
    untasked_sql += "\nUNION ALL\n".join(parent_parts)
    untasked_sql += """
)
SELECT parent_table || ':' || source_id::text || ':' || task_key::text
FROM parents
WHERE tasked IS NOT TRUE
ORDER BY 1;
"""
    untasked = [x for x in q(untasked_sql).strip().splitlines() if x.strip()]
    checks.append(
        {
            "id": "A6_parents_tasked",
            "ok": len(untasked) == 0,
            "detail": {"untasked": untasked[:30], "count": len(untasked)},
        }
    )

    # Restore match simulation (candidates for same global_id+geom_hash in same table)
    restore_sql = f"""
WITH links AS (
  SELECT task_key, id, global_id, geom_hash, src FROM (
    {split_union()}
  ) s WHERE task_key IN (SELECT unnest({arr}))
),
cand AS (
"""
    cand_parts = []
    for split in SPLIT_TABLES:
        cand_parts.append(
            f"""
  SELECT l.task_key, l.src,
         (SELECT COUNT(*) FROM {split} r
          WHERE r.global_id IS NOT DISTINCT FROM l.global_id
            AND {GEOM_HASH.replace('geom', 'r.geom')} = l.geom_hash) AS candidates
  FROM links l
  WHERE l.src = '{split}'
"""
        )
    restore_sql += "\nUNION ALL\n".join(cand_parts)
    restore_sql += """
)
SELECT
  COUNT(*) FILTER (WHERE candidates = 0) AS zero_n,
  COUNT(*) FILTER (WHERE candidates > 1) AS multi_n,
  COUNT(*) FILTER (WHERE candidates = 1) AS one_n,
  COUNT(*) AS total_links
FROM cand;
"""
    # Fix geom hash for r.geom - I used a hacky replace. Let me fix the SQL generation.
    # Actually GEOM_HASH uses bare `geom` - for alias r need md5(... r.geom ...)
    restore_sql = f"""
WITH links AS (
  SELECT task_key, id, global_id, geom_hash, src FROM (
    {split_union()}
  ) s WHERE task_key IN (SELECT unnest({arr}))
),
cand AS (
"""
    cand_parts = []
    for split in SPLIT_TABLES:
        gh = "md5(ST_AsEWKB(ST_SetSRID(ST_MakeValid(r.geom), 4326)))"
        cand_parts.append(
            f"""
  SELECT l.task_key, l.src,
         (SELECT COUNT(*) FROM {split} r
          WHERE r.global_id IS NOT DISTINCT FROM l.global_id
            AND {gh} = l.geom_hash) AS candidates
  FROM links l
  WHERE l.src = '{split}'
"""
        )
    restore_sql += "\nUNION ALL\n".join(cand_parts)
    restore_sql += """
)
SELECT
  COALESCE(COUNT(*) FILTER (WHERE candidates = 0),0),
  COALESCE(COUNT(*) FILTER (WHERE candidates > 1),0),
  COALESCE(COUNT(*) FILTER (WHERE candidates = 1),0),
  COUNT(*)
FROM cand;
"""
    z, m, o, tot = (int(x) for x in q(restore_sql).strip().split("\t"))
    metrics["restore"] = {
        "zero": z,
        "multi": m,
        "one": o,
        "total_links": tot,
    }
    checks.append(
        {
            "id": "A7_restore_match",
            "ok": z == 0 and tot > 0,
            "detail": metrics["restore"],
            "warn": m > 0,
        }
    )

    # Remapped keys linked
    if remapped:
        remap_sql = f"""
SELECT ct.key::text,
       COALESCE(
         (SELECT COUNT(*) FROM ({split_union()}) s WHERE s.task_key = ct.key), 0
       ) AS link_n
FROM crm.tasks ct
WHERE ct.key = ANY({remapped_arr});
"""
        remap_rows = []
        for line in q(remap_sql).strip().splitlines():
            if not line.strip():
                continue
            k, n = line.split("\t")
            remap_rows.append({"key": k, "link_n": int(n)})
        metrics["remapped"] = remap_rows
        checks.append(
            {
                "id": "A8_remapped_linked",
                "ok": all(r["link_n"] >= 1 for r in remap_rows)
                and len(remap_rows) == len(remapped),
                "detail": remap_rows,
            }
        )

    # --- Block B global ---
    linked_sql = (
        "SELECT COUNT(*) FROM (\n"
        + "\nUNION ALL\n".join(
            f"SELECT task_key FROM {t} WHERE task_key IS NOT NULL" for t in SPLIT_TABLES
        )
        + "\n) s;"
    )
    linked_items = int(q(linked_sql).strip())
    metrics["linked_items"] = linked_items

    gap_parts = [
        f"SELECT COUNT(*) FROM {t} WHERE geom IS NOT NULL AND task_key IS NULL"
        for t in SPLIT_TABLES
    ]
    gap_sql = "SELECT (\n" + "\n+\n".join(f"({p})" for p in gap_parts) + "\n);"
    gap_n = int(q(gap_sql).strip())
    metrics["gap_geom_no_task_key"] = gap_n

    orphan_task_sql = """
SELECT COUNT(*) FROM (
    SELECT ct.key
    FROM crm.tasks ct
    WHERE (ct.oati_id IS NOT NULL OR ct.earthwork_id IS NOT NULL
           OR ct.localwork_id IS NOT NULL OR ct.avr_mos_id IS NOT NULL)
      AND ct.is_field_data IS NOT TRUE
      AND ct.is_office_task IS NOT TRUE
      AND (
          ct.oati_id ~ '^(point|line|polygon):'
          OR ct.earthwork_id ~ '^(point|line|polygon):'
          OR ct.localwork_id ~ '^(point|line|polygon):'
          OR ct.avr_mos_id ~ '^(point|line|polygon):'
      )
      AND NOT EXISTS (
""" + "\nUNION ALL\n".join(
        f"SELECT 1 FROM {t} x WHERE x.task_key = ct.key" for t in SPLIT_TABLES
    ) + """
      )
) orphan_tasks;
"""
    orphan_tasks = int(q(orphan_task_sql).strip())
    metrics["orphan_tasks"] = orphan_tasks

    orphan_key_sql = (
        "SELECT COUNT(*) FROM (\n"
        + "\nUNION ALL\n".join(
            f"SELECT task_key FROM {t} WHERE task_key IS NOT NULL" for t in SPLIT_TABLES
        )
        + """
) t
LEFT JOIN crm.tasks ct ON ct.key = t.task_key
WHERE ct.key IS NULL;
"""
    )
    orphan_task_keys = int(q(orphan_key_sql).strip())
    metrics["orphan_task_keys"] = orphan_task_keys

    per_svc = {}
    for parent in PARENT_TABLES:
        base = parent.split(".", 1)[1]
        n = 0
        for suf in ("_points", "_lines", "_polygons"):
            n += int(
                q(
                    f"SELECT COUNT(*) FROM data_mos.{base}{suf} WHERE task_key IS NOT NULL;",
                ).strip()
            )
        tasked = int(
            q(f"SELECT COUNT(*) FROM {parent} WHERE tasked IS TRUE;").strip()
        )
        per_svc[base] = {"linked": n, "tasked_parents": tasked}
    metrics["per_service"] = per_svc

    observed_all = int(
        q("SELECT COUNT(*) FROM crm.tasks WHERE field_observed IS TRUE;").strip()
    )
    metrics["field_observed_all"] = observed_all

    # Global checks: no hard fail thresholds except orphan_task_keys should be 0
    checks.append(
        {
            "id": "B1_orphan_task_keys",
            "ok": orphan_task_keys == 0,
            "detail": f"orphan_task_keys={orphan_task_keys}",
        }
    )
    checks.append(
        {
            "id": "B2_global_snapshot",
            "ok": True,
            "detail": {
                "linked_items": linked_items,
                "gap": gap_n,
                "orphan_tasks": orphan_tasks,
                "field_observed_all": observed_all,
                "per_service": per_svc,
            },
        }
    )

    failed = [c for c in checks if not c["ok"]]
    warns = [c for c in checks if c.get("warn")]
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "host": host,
        "reason": protect.get("reason"),
        "ok": len(failed) == 0,
        "failed": [c["id"] for c in failed],
        "warnings": [c["id"] for c in warns],
        "checks": checks,
        "metrics": metrics,
    }


def compare(pre: dict[str, Any], post: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    if not post.get("ok"):
        issues.append("post assert not ok: " + ",".join(post.get("failed", [])))
    pm, qm = pre.get("metrics", {}), post.get("metrics", {})
    for key in (
        "found_n",
        "observed_n",
        "clear_n",
        "report_keys_n",
    ):
        if pm.get(key) != qm.get(key):
            issues.append(f"{key}: {pm.get(key)} -> {qm.get(key)}")
    if qm.get("linked_items", 0) < pm.get("linked_items", 0):
        issues.append(
            f"linked_items dropped: {pm.get('linked_items')} -> {qm.get('linked_items')}"
        )
    if qm.get("orphan_tasks", 0) > pm.get("orphan_tasks", 0) + 5:
        issues.append(
            f"orphan_tasks grew: {pm.get('orphan_tasks')} -> {qm.get('orphan_tasks')}"
        )
    if qm.get("gap_geom_no_task_key", 0) > pm.get("gap_geom_no_task_key", 0) + 50:
        issues.append(
            f"gap grew a lot: {pm.get('gap_geom_no_task_key')} -> {qm.get('gap_geom_no_task_key')}"
        )
    return {"ok": len(issues) == 0, "issues": issues}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--local", action="store_true", help="Use local docker exec (on .219)")
    ap.add_argument("--protect", type=Path, default=DEFAULT_PROTECT)
    ap.add_argument("--mode", choices=("pre", "post", "assert"), default="assert")
    ap.add_argument("--baseline", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args()

    protect = load_protect(args.protect)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    result = run_assert(args.host, protect, local=args.local)
    if args.local:
        result["host"] = "local-docker"

    if args.mode == "pre":
        out = args.out_dir / "baseline_pre_etl.json"
    elif args.mode == "post":
        out = args.out_dir / "baseline_post_etl.json"
    else:
        out = args.out_dir / "baseline_assert.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out}")
    print(f"ok={result['ok']} failed={result['failed']} warnings={result['warnings']}")

    if args.mode == "post":
        base_path = args.baseline or (args.out_dir / "baseline_pre_etl.json")
        if not base_path.exists():
            print(f"missing baseline {base_path}", file=sys.stderr)
            return 2
        pre = json.loads(base_path.read_text())
        cmp = compare(pre, result)
        cmp_path = args.out_dir / "compare_pre_post.json"
        cmp_path.write_text(json.dumps(cmp, indent=2) + "\n")
        print(f"compare ok={cmp['ok']} issues={cmp['issues']}")
        if not cmp["ok"]:
            return 1

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
