"""CLI for FieldControl ZIP restore (SSH / local docker)."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Sequence

from app.field_zip_restore.clients import ProdClient
from app.field_zip_restore.parse import discover_zips, parse_zip
from app.field_zip_restore.plan import RestorePlan, apply_plan, build_plan, extract_zip_bytes, snapshot_keys

DEFAULT_HOST = "172.21.198.219"
DEFAULT_USERNAME = "ZhuchenkoAA"
DEFAULT_PHOTO_DIR = "/opt/monitor/mggtfield_photo"


def print_plan(plan: RestorePlan) -> None:
    archive = plan.archive
    title = archive.order_number or archive.raw_task_key
    print(f"\n=== {archive.path.name}  {title}  kind={archive.kind} ===")
    print(f"  uuid={archive.order_uuid} rayon={archive.rayon or '—'} exported={archive.exported_at}")
    if archive.kind == "field_order":
        print(
            f"  submissions={len(archive.submissions)} as_clear={archive.as_clear} "
            f"field_key={plan.field_key} tasks_key={plan.tasks_key}"
        )
    else:
        print(
            f"  track_points={len(archive.track.points) if archive.track else 0} "
            f"unique={archive.unique_track_points} duration={archive.track.duration_sec if archive.track else 0}s "
            f"db_status={plan.area_status or '—'}"
        )
    if plan.skip_reason:
        print(f"  SKIP: {plan.skip_reason}")
    for warning in plan.warnings:
        print(f"  WARN: {warning}")
    for action in plan.actions:
        print(f"  - {action}")
    if plan.photos:
        print(f"  photos to copy: {len(plan.photos)}")
    if plan.sql_statements:
        print(f"  SQL statements: {len(plan.sql_statements)}")


def apply_plan_cli(plan: RestorePlan, client: ProdClient, photo_dir: str) -> None:
    for photo in plan.photos:
        raw = extract_zip_bytes(plan.archive, photo.zip_path)
        digest = hashlib.sha256(raw).hexdigest()[:12]
        print(f"    photo {photo.file_name} slot={photo.slot} sha={digest} bytes={len(raw)}")
    apply_plan(plan, client, photo_dir)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore FieldControl ZIP archives to prod")
    parser.add_argument("zips", nargs="*", type=Path, help="ZIP files")
    parser.add_argument("--dir", type=Path, default=None, help="Directory of ZIP files")
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--photo-dir", default=DEFAULT_PHOTO_DIR)
    parser.add_argument("--apply", action="store_true", help="Write to prod (default: dry-run)")
    parser.add_argument("--local", action="store_true", help="Use local docker exec instead of SSH")
    parser.add_argument("--offline", action="store_true", help="Parse only, do not query the database")
    args = parser.parse_args(argv)

    zip_paths = discover_zips(args.dir, args.zips)
    if not zip_paths:
        print("No ZIP files found")
        return 2

    archives = [parse_zip(path) for path in zip_paths]
    client: ProdClient | None = None if args.offline else ProdClient(args.host, local=args.local)

    keys = [item.order_uuid for item in archives]
    if client is not None:
        print("=== snapshot before ===")
        print(snapshot_keys(client, keys))

    plans = [build_plan(archive, args.username, client) for archive in archives]
    for plan in plans:
        print_plan(plan)

    writable = [plan for plan in plans if plan.will_write]
    print(f"\n{len(plans)} archives, {len(writable)} will write, username={args.username}")
    if not args.apply:
        print("Dry-run only. Re-run with --apply to write.")
        return 0

    if client is None:
        print("--apply requires a database connection (omit --offline)")
        return 2

    failures = 0
    for plan in plans:
        if not plan.will_write:
            continue
        print(f"\nAPPLY {plan.archive.path.name} ...")
        try:
            apply_plan_cli(plan, client, args.photo_dir)
            print(f"  OK {plan.archive.path.name}")
        except Exception as exc:  # noqa: BLE001 — isolate per-ZIP failure
            failures += 1
            print(f"  FAIL {plan.archive.path.name}: {exc}")

    print("\n=== snapshot after ===")
    extra = [plan.tasks_key for plan in plans if plan.tasks_key]
    print(snapshot_keys(client, list(dict.fromkeys([*keys, *extra]))))
    return 1 if failures else 0
