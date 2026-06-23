"""Authentication routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.auth.service import authenticate
from app.auth.session import (
    UserSession,
    allowed_task_sources,
    can_collect,
    can_create_users,
    can_manage_personnel,
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
    role: str
    work_zones: list[int]
    allowed_task_sources: list[str]
    default_task_source: str
    can_collect: bool
    can_manage_personnel: bool
    can_create_users: bool


@router.post("/login", response_model=AuthUserOut)
def login(body: LoginRequest, response: Response) -> AuthUserOut:
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
    return _user_out(session)


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    settings = get_settings()
    response.delete_cookie(key=settings.auth_cookie_name, path="/")
    return {"status": "ok"}


@router.get("/me", response_model=AuthUserOut)
def me(user: UserSession = Depends(get_current_user)) -> AuthUserOut:
    return _user_out(user)


def _user_out(session: UserSession) -> AuthUserOut:
    return AuthUserOut(
        login=session.login,
        role=session.role,
        work_zones=session.work_zones,
        allowed_task_sources=allowed_task_sources(session.role),
        default_task_source=default_task_source(session.role),
        can_collect=can_collect(session.role),
        can_manage_personnel=can_manage_personnel(session.role),
        can_create_users=can_create_users(session.role),
    )
