"""User audit metadata for CRM task tables."""

from __future__ import annotations

from datetime import datetime, timezone

USER_AUDIT_COLUMNS = ("user_created", "user_last_edit")


def make_user_audit(login: str) -> list[str]:
    login = (login or "").strip()
    stamp = datetime.now(timezone.utc).isoformat()
    return [login, stamp]


def user_audit_migration_statements(schema: str, table: str) -> tuple[str, ...]:
    return tuple(
        f'ALTER TABLE "{schema}"."{table}" '
        f'ADD COLUMN IF NOT EXISTS "{col}" TEXT[]'
        for col in USER_AUDIT_COLUMNS
    )
