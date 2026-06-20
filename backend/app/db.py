"""PostgreSQL connection pool."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

import psycopg2
from psycopg2 import pool
from psycopg2.extensions import connection as PgConnection

from app.config import get_settings

_pool: pool.ThreadedConnectionPool | None = None


def init_pool() -> None:
    global _pool
    if _pool is not None:
        return
    s = get_settings()
    _pool = pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=10,
        host=s.db_host,
        port=s.db_port,
        dbname=s.db_name,
        user=s.db_user,
        password=s.db_password,
        connect_timeout=5,
        options="-c statement_timeout=30000",
    )


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


@contextmanager
def get_connection() -> Generator[PgConnection, None, None]:
    if _pool is None:
        init_pool()
    assert _pool is not None
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)
