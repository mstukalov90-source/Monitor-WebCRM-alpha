"""Authentication and district access checks."""

from __future__ import annotations

from psycopg2.extensions import connection as PgConnection

from app.auth.session import (
    HOOD_SCHEMA,
    HOOD_TABLE,
    UserSession,
    districts_unrestricted,
)


def authenticate(
    conn: PgConnection,
    login: str,
    password: str,
) -> UserSession | None:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT uuid::text, login, role, work_zones
                FROM crm.users
                WHERE login = %s AND password = crypt(%s, password)
                """,
                (login.strip(), password),
            )
            row = cur.fetchone()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return None
    if not row:
        return None
    work_zones = [int(g) for g in (row[3] or [])]
    return UserSession(
        uuid=str(row[0]),
        login=str(row[1]),
        role=str(row[2]),
        work_zones=work_zones,
    )


def fetch_allowed_rayons(conn: PgConnection, session: UserSession) -> list[str]:
    if districts_unrestricted(session) or not session.work_zones:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT rayon
                FROM "{HOOD_SCHEMA}"."{HOOD_TABLE}"
                WHERE gid = ANY(%s)
                ORDER BY rayon
                """,
                (session.work_zones,),
            )
            return [str(row[0]).strip() for row in cur.fetchall() if row[0]]
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return []


def is_rayon_allowed(
    conn: PgConnection,
    session: UserSession,
    rayon: str,
) -> bool:
    if districts_unrestricted(session):
        return True
    allowed = fetch_allowed_rayons(conn, session)
    if not allowed and session.work_zones:
        return False
    return rayon.strip() in set(allowed)
