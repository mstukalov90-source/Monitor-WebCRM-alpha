#!/usr/bin/env python3
"""Bulk send active order-group tasks to field for a district (smoke / ops)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.crm.collector import collect_tasks  # noqa: E402
from app.crm.store import (  # noqa: E402
    CRM_GROUP_ORDERS,
    fetch_task_by_key,
    send_task_to_field,
)
from app.config import crm_task_store_config  # noqa: E402
from app.db import get_connection  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Send order-group active tasks to field")
    parser.add_argument("--rayon", required=True, help="District name, e.g. Аэропорт")
    parser.add_argument("--login", required=True, help="User login for audit trail")
    parser.add_argument(
        "--no-date-filter",
        action="store_true",
        help="Collect without date lookback filter",
    )
    args = parser.parse_args()

    store_cfg = crm_task_store_config()
    inserted = skipped = failed = 0
    failures: list[str] = []

    with get_connection() as conn:
        result, _ = collect_tasks(
            conn,
            args.rayon,
            apply_date_filter=not args.no_date_filter,
            persist=False,
            filter_sent=True,
        )

        for group in result.groups:
            if group.name != CRM_GROUP_ORDERS:
                continue
            for subgroup in group.subgroups:
                for feat in subgroup.features:
                    task_key = feat.task_key or feat.attributes.get("_task_key")
                    if not task_key:
                        failed += 1
                        failures.append(f"{subgroup.name}: no task_key on feature")
                        continue

                    record = fetch_task_by_key(conn, store_cfg, str(task_key))
                    if record is None:
                        failed += 1
                        failures.append(f"{task_key}: task not found in crm.tasks")
                        continue

                    try:
                        status = send_task_to_field(
                            conn,
                            record,
                            store_cfg,
                            args.login,
                            rayon=args.rayon,
                        )
                    except ValueError as exc:
                        failed += 1
                        failures.append(f"{task_key}: {exc}")
                        continue

                    if status == "inserted":
                        inserted += 1
                    else:
                        skipped += 1

    print(f"Rayon: {args.rayon}")
    print(f"Group: {CRM_GROUP_ORDERS}")
    print(f"Inserted: {inserted}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {failed}")
    if failures:
        print("Failures:")
        for line in failures[:50]:
            print(f"  - {line}")
        if len(failures) > 50:
            print(f"  ... and {len(failures) - 50} more")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
