"""Authentication routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.auth.service import authenticate, session_with_db_name
from app.auth.session import (
    UserSession,
    allowed_task_sources,
    can_collect,
    can_create_users,
    can_generate_letters,
    can_manage_field_task_status,
    can_manage_personnel,
    can_postpone_tasks,
    can_view_server_monitor,
    default_task_source,
)
from app.auth.tokens import create_token
from app.config import get_settings
from app.db import get_connection

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    login: str
    password: str


class AuthUserOut(BaseModel):
    login: str
    name: str
    role: str
    work_zones: list[int]
    allowed_task_sources: list[str]
    default_task_source: str
    can_collect: bool
    can_manage_personnel: bool
    can_generate_letters: bool
    can_manage_field_task_status: bool
    can_postpone_tasks: bool
    can_create_users: bool
    can_view_server_monitor: bool


class AuthLoginOut(AuthUserOut):
    """Login response: same user flags plus JWT for Bearer clients (QGIS)."""

    token: str


@router.post("/login", response_model=AuthLoginOut)
def login(body: LoginRequest, response: Response) -> AuthLoginOut:
    with get_connection() as conn:
        session = authenticate(conn, body.login, body.password)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        )

    settings = get_settings()
    token = create_token(session)
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.auth_token_ttl_hours * 3600,
        path="/",
    )
    user = _user_out(session)
    return AuthLoginOut(**user.model_dump(), token=token)


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    settings = get_settings()
    response.delete_cookie(key=settings.auth_cookie_name, path="/")
    return {"status": "ok"}


@router.get("/me", response_model=AuthUserOut)
def me(user: UserSession = Depends(get_current_user)) -> AuthUserOut:
    with get_connection() as conn:
        user = session_with_db_name(conn, user)
    return _user_out(user)


def _user_out(session: UserSession) -> AuthUserOut:
    return AuthUserOut(
        login=session.login,
        name=session.name or session.login,
        role=session.role,
        work_zones=session.work_zones,
        allowed_task_sources=allowed_task_sources(session.role),
        default_task_source=default_task_source(session.role),
        can_collect=can_collect(session.role),
        can_manage_personnel=can_manage_personnel(session.role),
        can_generate_letters=can_generate_letters(session.role),
        can_manage_field_task_status=can_manage_field_task_status(session.role),
        can_postpone_tasks=can_postpone_tasks(session.role),
        can_create_users=can_create_users(session.role),
        can_view_server_monitor=can_view_server_monitor(session.role),
    )
