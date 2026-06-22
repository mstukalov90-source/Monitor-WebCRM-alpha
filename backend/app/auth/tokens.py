"""JWT session tokens stored in httpOnly cookies."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.auth.session import UserSession
from app.config import get_settings

ALGORITHM = "HS256"


def create_token(session: UserSession) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": session.uuid,
        "login": session.login,
        "role": session.role,
        "work_zones": session.work_zones,
        "iat": now,
        "exp": now + timedelta(hours=settings.auth_token_ttl_hours),
    }
    return jwt.encode(payload, settings.auth_secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> UserSession | None:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.auth_secret_key,
            algorithms=[ALGORITHM],
        )
    except jwt.PyJWTError:
        return None
    uuid = payload.get("sub")
    login = payload.get("login")
    role = payload.get("role")
    if not uuid or not login or not role:
        return None
    work_zones_raw = payload.get("work_zones") or []
    work_zones = [int(g) for g in work_zones_raw]
    return UserSession(
        uuid=str(uuid),
        login=str(login),
        role=str(role),
        work_zones=work_zones,
    )
