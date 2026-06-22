"""FastAPI dependencies for authentication and authorization."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from app.auth.service import is_rayon_allowed
from app.auth.session import (
    UserSession,
    allowed_area_statuses,
    allowed_task_sources,
    can_collect,
    is_hood_layer,
)
from app.auth.tokens import decode_token
from app.config import get_settings
from app.db import get_connection
from app.layers.registry import LayerDef


def get_current_user(request: Request) -> UserSession:
    settings = get_settings()
    token = request.cookies.get(settings.auth_cookie_name)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется вход в систему",
        )
    session = decode_token(token)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия истекла или недействительна",
        )
    return session


def require_can_collect(user: UserSession = Depends(get_current_user)) -> UserSession:
    if not can_collect(user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Сбор задач из слоёв недоступен для вашей роли",
        )
    return user


def check_rayon(user: UserSession, rayon: str) -> None:
    with get_connection() as conn:
        if not is_rayon_allowed(conn, user, rayon):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Район недоступен для вашей учётной записи",
            )


def check_task_source(user: UserSession, source: str) -> None:
    if source not in allowed_task_sources(user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Источник задач недоступен для вашей роли",
        )


def check_task_source_any(user: UserSession, sources: list[str]) -> None:
    allowed = allowed_task_sources(user.role)
    if not any(s in allowed for s in sources):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Источник задач недоступен для вашей роли",
        )


def check_area_status(user: UserSession, status_value: str) -> None:
    if status_value not in allowed_area_statuses(user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Статус площадного заказа недоступен для вашей роли",
        )


def apply_hood_filter_to_layer(layer: LayerDef, user: UserSession) -> LayerDef:
    from dataclasses import replace

    from app.auth.session import hood_gid_sql_filter

    if not is_hood_layer(layer.schema, layer.table_name, layer.display_name):
        return layer
    filt = hood_gid_sql_filter(user)
    if not filt:
        return layer
    existing = layer.sql_filter or ""
    if existing:
        new_filter = f"({existing}) AND ({filt})"
    else:
        new_filter = filt
    return replace(layer, sql_filter=new_filter)
