"""Personal Excel report templates."""

from __future__ import annotations

from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import Json, RealDictCursor

from app.crm.reports.catalog import ReportSpec, validate_report_spec
from app.crm.reports.errors import ReportError

_TABLE_READY = False

ENSURE_SQL = """
CREATE TABLE IF NOT EXISTS crm.report_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_login TEXT NOT NULL REFERENCES crm.users(login) ON DELETE CASCADE,
    name TEXT NOT NULL,
    spec JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_login, name)
)
"""


def ensure_report_templates_table(conn: PgConnection) -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    with conn.cursor() as cur:
        cur.execute(ENSURE_SQL)
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_crm_report_templates_user
                ON crm.report_templates (user_login)
            """
        )
    conn.commit()
    _TABLE_READY = True


def list_templates(conn: PgConnection, user_login: str) -> list[dict[str, Any]]:
    ensure_report_templates_table(conn)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id::text, name, spec, created_at, updated_at
            FROM crm.report_templates
            WHERE user_login = %s
            ORDER BY updated_at DESC, name
            """,
            (user_login,),
        )
        rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        _iso(row, "created_at")
        _iso(row, "updated_at")
    return rows


def create_template(
    conn: PgConnection,
    user_login: str,
    name: str,
    spec: ReportSpec,
) -> dict[str, Any]:
    ensure_report_templates_table(conn)
    clean_name = _clean_name(name)
    clean_spec = validate_report_spec(spec)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO crm.report_templates (user_login, name, spec)
                VALUES (%s, %s, %s)
                RETURNING id::text, name, spec, created_at, updated_at
                """,
                (user_login, clean_name, Json(clean_spec.model_dump())),
            )
            row = dict(cur.fetchone() or {})
        conn.commit()
    except Exception as exc:
        conn.rollback()
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise ReportError("Шаблон с таким названием уже есть") from exc
        raise
    _iso(row, "created_at")
    _iso(row, "updated_at")
    return row


def update_template(
    conn: PgConnection,
    user_login: str,
    template_id: str,
    *,
    name: str | None,
    spec: ReportSpec | None,
) -> dict[str, Any] | None:
    ensure_report_templates_table(conn)
    current = get_template(conn, user_login, template_id)
    if current is None:
        return None
    clean_name = _clean_name(name) if name is not None else current["name"]
    clean_spec = validate_report_spec(spec) if spec is not None else ReportSpec.model_validate(
        current["spec"]
    )
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE crm.report_templates
                SET name = %s,
                    spec = %s,
                    updated_at = NOW()
                WHERE id = %s::uuid AND user_login = %s
                RETURNING id::text, name, spec, created_at, updated_at
                """,
                (clean_name, Json(clean_spec.model_dump()), template_id, user_login),
            )
            row = cur.fetchone()
        conn.commit()
    except Exception as exc:
        conn.rollback()
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise ReportError("Шаблон с таким названием уже есть") from exc
        raise
    if row is None:
        return None
    data = dict(row)
    _iso(data, "created_at")
    _iso(data, "updated_at")
    return data


def delete_template(conn: PgConnection, user_login: str, template_id: str) -> bool:
    ensure_report_templates_table(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM crm.report_templates
            WHERE id = %s::uuid AND user_login = %s
            """,
            (template_id, user_login),
        )
        deleted = cur.rowcount
    conn.commit()
    return deleted > 0


def get_template(
    conn: PgConnection,
    user_login: str,
    template_id: str,
) -> dict[str, Any] | None:
    ensure_report_templates_table(conn)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id::text, name, spec, created_at, updated_at
            FROM crm.report_templates
            WHERE id = %s::uuid AND user_login = %s
            """,
            (template_id, user_login),
        )
        row = cur.fetchone()
    if row is None:
        return None
    data = dict(row)
    _iso(data, "created_at")
    _iso(data, "updated_at")
    return data


def _clean_name(name: str) -> str:
    cleaned = " ".join((name or "").split())
    if not cleaned:
        raise ReportError("Укажите название шаблона")
    if len(cleaned) > 120:
        raise ReportError("Название шаблона слишком длинное")
    return cleaned


def _iso(row: dict[str, Any], key: str) -> None:
    value = row.get(key)
    if hasattr(value, "isoformat"):
        row[key] = value.isoformat()
