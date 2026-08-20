"""Excel report constructor routes (statistics export and personal templates)."""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.auth.deps import get_current_user
from app.auth.session import UserSession, can_manage_personnel
from app.crm.reports.catalog import (
    ReportExportRequest,
    ReportTemplateCreate,
    ReportTemplateUpdate,
    catalog_payload,
    validate_report_spec,
)
from app.crm.reports.errors import ReportError
from app.crm.reports.excel import build_workbook_bytes, content_disposition
from app.crm.reports.query import QueryScope, apply_export_timeout, fetch_report_sheets
from app.crm.reports.templates import (
    create_template,
    delete_template,
    list_templates,
    update_template,
)
from app.db import get_connection

router = APIRouter(prefix="/api/personnel/statistics/reports", tags=["statistics-reports"])


def _http_error(exc: ReportError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _parse_iso_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be YYYY-MM-DD",
        ) from exc


def resolve_export_scope(
    user: UserSession,
    *,
    user_login: str | None,
    user_role: str | None,
    object_type: str | None,
) -> tuple[str | None, str | None, Literal["all", "self"]]:
    if object_type is not None and object_type not in ("task", "order"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="object_type must be task or order",
        )
    org_view = can_manage_personnel(user.role)
    if org_view:
        if user_role is not None and user_role not in ("field", "office"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_role must be field or office",
            )
        return (
            user_login.strip() if user_login else None,
            user_role,
            "all",
        )
    if user.role not in ("field", "office"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Статистика недоступна для вашей роли",
        )
    if user_login and user_login.strip() != user.login:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ только к своей статистике",
        )
    return (
        user.login,
        "field" if user.role == "field" else "office",
        "self",
    )


@router.get("/catalog")
def get_report_catalog(
    _user: UserSession = Depends(get_current_user),
) -> dict[str, Any]:
    return catalog_payload()


@router.get("/templates")
def get_report_templates(
    user: UserSession = Depends(get_current_user),
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return list_templates(conn, user.login)


@router.post("/templates", status_code=status.HTTP_201_CREATED)
def post_report_template(
    body: ReportTemplateCreate,
    user: UserSession = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        spec = validate_report_spec(body.spec)
        with get_connection() as conn:
            return create_template(conn, user.login, body.name, spec)
    except ReportError as exc:
        raise _http_error(exc) from exc


@router.patch("/templates/{template_id}")
def patch_report_template(
    template_id: str,
    body: ReportTemplateUpdate,
    user: UserSession = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            updated = update_template(
                conn,
                user.login,
                template_id,
                name=body.name,
                spec=body.spec,
            )
    except ReportError as exc:
        raise _http_error(exc) from exc
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Шаблон не найден")
    return updated


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report_template(
    template_id: str,
    user: UserSession = Depends(get_current_user),
) -> None:
    with get_connection() as conn:
        deleted = delete_template(conn, user.login, template_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Шаблон не найден")


@router.post("/export")
def export_statistics_report(
    body: ReportExportRequest,
    user: UserSession = Depends(get_current_user),
) -> StreamingResponse:
    date_from = _parse_iso_date(body.date_from, "date_from")
    date_to = _parse_iso_date(body.date_to, "date_to")
    if date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_from must be on or before date_to",
        )
    effective_login, effective_role, _scope = resolve_export_scope(
        user,
        user_login=body.user_login,
        user_role=body.user_role,
        object_type=body.object_type,
    )
    try:
        spec = validate_report_spec(body.spec)
    except ReportError as exc:
        raise _http_error(exc) from exc

    rayons = tuple(item.strip() for item in body.rayons if item and item.strip())
    query_scope = QueryScope(
        date_from=date_from,
        date_to=date_to,
        user_login=effective_login,
        user_role=effective_role,
        object_type=body.object_type,
        rayons=rayons,
    )
    try:
        with get_connection() as conn:
            try:
                apply_export_timeout(conn)
                sheets = fetch_report_sheets(conn, spec, query_scope)
            finally:
                conn.rollback()
        content = build_workbook_bytes(spec.name, sheets)
    except ReportError as exc:
        raise _http_error(exc) from exc

    filename_header = content_disposition(spec.name, body.date_from, body.date_to)
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": filename_header},
    )
