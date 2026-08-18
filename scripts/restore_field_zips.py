#!/usr/bin/env python3
"""Replay FieldControl order ZIPs onto prod, matching FieldSyncService.

Default is dry-run (parse + compare with PostgreSQL on .219). Pass --apply to
copy photos to /opt/monitor/mggtfield_photo and execute the CRM writes.

Usage:
  python3 scripts/restore_field_zips.py --dir tmp/lost_tasks --username ZhuchenkoAA
  python3 scripts/restore_field_zips.py --dir tmp/lost_tasks --username ZhuchenkoAA --apply
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.field_zip_restore.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
