"""PostgreSQL connection pool."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from threading import Lock
from typing import Generator

import psycopg2
from psycopg2 import pool
from psycopg2.extensions import connection as PgConnection

from app.config import get_settings

logger = logging.getLogger(__name__)

POOL_MAXCONN = 10
MGGT_POOL_MAXCONN = 4

_pool: pool.ThreadedConnectionPool | None = None
_in_use = 0
_in_use_lock = Lock()

_mggt_pool: pool.ThreadedConnectionPool | None = None
_mggt_in_use = 0
_mggt_lock = Lock()


class MggtUnavailable(Exception):
    """MGGT database is not configured or cannot be reached."""


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
    init_mggt_pool()


def mggt_configured() -> bool:
    return bool(get_settings().mggt_db_host.strip())


def init_mggt_pool() -> str | None:
    """Create the MGGT pool if configured. Returns an error message on failure."""
    global _mggt_pool
    if _mggt_pool is not None:
        return None
    if not mggt_configured():
        return "MGGT database is not configured"
    s = get_settings()
    try:
        _mggt_pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=MGGT_POOL_MAXCONN,
            host=s.mggt_db_host,
            port=s.mggt_db_port,
            dbname=s.mggt_db_name,
            user=s.mggt_db_user,
            password=s.mggt_db_password,
            connect_timeout=5,
            options="-c statement_timeout=60000",
        )
    except Exception as exc:
        logger.warning("MGGT database pool init failed: %s", exc)
        _mggt_pool = None
        return str(exc)
    return None


def close_pool() -> None:
    global _pool, _mggt_pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
    if _mggt_pool is not None:
        _mggt_pool.closeall()
        _mggt_pool = None


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


@contextmanager
def get_mggt_connection() -> Generator[PgConnection, None, None]:
    global _mggt_in_use
    error = init_mggt_pool()
    if _mggt_pool is None:
        raise MggtUnavailable(error or "MGGT database is not configured")
    conn = _mggt_pool.getconn()
    with _mggt_lock:
        _mggt_in_use += 1
    try:
        yield conn
    finally:
        with _mggt_lock:
            _mggt_in_use -= 1
        _mggt_pool.putconn(conn)
