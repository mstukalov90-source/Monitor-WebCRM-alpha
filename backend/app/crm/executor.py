"""Executor column for task assignment to CRM users."""

from __future__ import annotations

from psycopg2.extensions import connection as PgConnection

EXECUTOR_TABLES = ("tasks_field", "tasks_area")
_executor_ready: set[str] = set()


def executor_migration_statements(schema: str, table: str) -> tuple[str, ...]:
    index_name = f"idx_{schema}_{table}_executor"
    return (
        f'ALTER TABLE "{schema}"."{table}" '
        f'ADD COLUMN IF NOT EXISTS "executor" TEXT',
        f'CREATE INDEX IF NOT EXISTS {index_name} '
        f'ON "{schema}"."{table}" ("executor")',
    )


def ensure_executor_column(conn: PgConnection, schema: str, table: str) -> bool:
    key = f"{schema}.{table}"
    if key in _executor_ready:
        return True
    try:
        with conn.cursor() as cur:
            for stmt in executor_migration_statements(schema, table):
                cur.execute(stmt)
        conn.commit()
        _executor_ready.add(key)
        return True
    except Exception:
        conn.rollback()
        return False


def ensure_all_executor_columns(conn: PgConnection, schema: str = "crm") -> bool:
    ok = True
    for table in EXECUTOR_TABLES:
        if not ensure_executor_column(conn, schema, table):
            ok = False
    return ok
