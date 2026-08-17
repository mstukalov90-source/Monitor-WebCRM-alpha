"""PostgreSQL connection pool."""

from __future__ import annotations

from contextlib import contextmanager
from threading import Lock
from typing import Generator

import psycopg2
from psycopg2 import pool
from psycopg2.extensions import connection as PgConnection

from app.config import get_settings

POOL_MAXCONN = 10

_pool: pool.ThreadedConnectionPool | None = None
_in_use = 0
_in_use_lock = Lock()


def init_pool() -> None:
    global _pool
    if _pool is not None:
        return
    s = get_settings()
    _pool = pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=POOL_MAXCONN,
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


def pool_usage() -> dict[str, int]:
    with _in_use_lock:
        in_use = _in_use
    return {"in_use": in_use, "max": POOL_MAXCONN}


@contextmanager
def get_connection() -> Generator[PgConnection, None, None]:
    global _in_use
    if _pool is None:
        init_pool()
    assert _pool is not None
    conn = _pool.getconn()
    with _in_use_lock:
        _in_use += 1
    try:
        yield conn
    finally:
        with _in_use_lock:
            _in_use -= 1
        _pool.putconn(conn)
