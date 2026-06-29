"""Personnel management routes (manager/admin)."""

from __future__ import annotations

from typing import Literal

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.deps import get_current_user, require_admin, require_manager_or_admin
from app.auth.session import UserSession, can_manage_personnel
from app.crm.personnel import (
    PersonnelError,
    assign_task_executor,
    bulk_assign_task_executor,
    bulk_change_task_workflow_status,
    create_personnel_user,
    list_active_tasks_for_management,
    list_area_tasks_for_assignment,
    list_clear_tasks_for_management,
    list_field_tasks_for_assignment,
    lookup_field_snapshot_by_task_key,
    list_personnel_districts,
    list_personnel_users,
    update_user_work_zones,
)
from app.crm.schemas import (
    AssignableTaskOut,
    BulkAssignRequest,
    BulkAssignResultOut,
    BulkStatusRequest,
    BulkStatusResultOut,
    DistrictOptionOut,
    FieldSnapshotLookupOut,
    FieldStatisticsSummaryOut,
    OfficeStatisticsBreakdownOut,
    PersonnelStatisticsOut,
    PersonnelUserOut,
    PersonnelUserCreate,
    PersonnelUserUpdate,
    TaskExecutorUpdate,
    TaskNumberUpdate,
)
from app.crm.statistics import fetch_field_statistics_summary, fetch_office_statistics_breakdown
from app.crm.tasks_area import update_area_task_number
from app.db import get_connection

router = APIRouter(prefix="/api/personnel", tags=["personnel"])


@router.get("/statistics", response_model=PersonnelStatisticsOut)
def get_personnel_statistics(
    date_from: date = Query(..., description="Start date (inclusive)"),
    date_to: date = Query(..., description="End date (inclusive)"),
    user_role: str | None = Query(None, description="Filter by field or office"),
    object_type: str | None = Query(None, description="Filter by task or order"),
    user_login: str | None = Query(None, description="Filter by user login"),
    user: UserSession = Depends(get_current_user),
) -> PersonnelStatisticsOut:
    if date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_from must be on or before date_to",
        )
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
        effective_login = user_login.strip() if user_login else None
        effective_role = user_role
        scope: Literal["all", "self"] = "all"
    else:
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
        effective_login = user.login
        effective_role = "field" if user.role == "field" else "office"
        scope = "self"

    with get_connection() as conn:
        field_summary: list[dict] = []
        office_breakdown: list[dict] = []
        if effective_role in (None, "field"):
            field_summary = fetch_field_statistics_summary(
                conn,
                date_from=date_from,
                date_to=date_to,
                object_type=object_type if org_view else None,
                user_login=effective_login,
            )
        if effective_role in (None, "office"):
            office_breakdown = fetch_office_statistics_breakdown(
                conn,
                date_from=date_from,
                date_to=date_to,
                object_type=object_type if org_view else None,
                user_login=effective_login,
            )

    return PersonnelStatisticsOut(
        field_summary=[FieldStatisticsSummaryOut(**row) for row in field_summary],
        office_breakdown=[OfficeStatisticsBreakdownOut(**row) for row in office_breakdown],
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        scope=scope,
    )


@router.get("/users", response_model=list[PersonnelUserOut])
def get_personnel_users(
    _user: UserSession = Depends(require_manager_or_admin),
) -> list[PersonnelUserOut]:
    with get_connection() as conn:
        users = list_personnel_users(conn)
    return [PersonnelUserOut(**u) for u in users]


@router.post("/users", response_model=PersonnelUserOut, status_code=status.HTTP_201_CREATED)
def post_personnel_user(
    body: PersonnelUserCreate,
    _user: UserSession = Depends(require_admin),
) -> PersonnelUserOut:
    try:
        with get_connection() as conn:
            created = create_personnel_user(
                conn,
                body.login,
                body.password,
                body.role,
                body.work_zones,
            )
    except PersonnelError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PersonnelUserOut(**created)


@router.patch("/users/{user_uuid}", response_model=PersonnelUserOut)
def patch_personnel_user(
    user_uuid: str,
    body: PersonnelUserUpdate,
    _user: UserSession = Depends(require_manager_or_admin),
) -> PersonnelUserOut:
    try:
        with get_connection() as conn:
            updated = update_user_work_zones(conn, user_uuid, body.work_zones)
    except PersonnelError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    return PersonnelUserOut(**updated)


@router.get("/districts", response_model=list[DistrictOptionOut])
def get_personnel_districts(
    _user: UserSession = Depends(require_manager_or_admin),
) -> list[DistrictOptionOut]:
    with get_connection() as conn:
        districts = list_personnel_districts(conn)
    return [DistrictOptionOut(**d) for d in districts]


@router.get("/tasks/active", response_model=list[AssignableTaskOut])
def get_active_tasks_for_management(
    rayon: str = Query(""),
    _user: UserSession = Depends(require_manager_or_admin),
) -> list[AssignableTaskOut]:
    with get_connection() as conn:
        tasks = list_active_tasks_for_management(conn, rayon=rayon or None)
    return [AssignableTaskOut(**t) for t in tasks]


@router.get("/tasks/clear", response_model=list[AssignableTaskOut])
def get_clear_tasks_for_management(
    rayon: str = Query(""),
    _user: UserSession = Depends(require_manager_or_admin),
) -> list[AssignableTaskOut]:
    with get_connection() as conn:
        tasks = list_clear_tasks_for_management(conn, rayon=rayon or None)
    return [AssignableTaskOut(**t) for t in tasks]


@router.get("/tasks/field", response_model=list[AssignableTaskOut])
def get_field_tasks_for_assignment(
    rayon: str = Query(""),
    executor: str = Query(""),
    unassigned_only: bool = Query(False),
    _user: UserSession = Depends(require_manager_or_admin),
) -> list[AssignableTaskOut]:
    with get_connection() as conn:
        tasks = list_field_tasks_for_assignment(
            conn,
            rayon=rayon or None,
            executor=executor or None,
            unassigned_only=unassigned_only,
        )
    return [AssignableTaskOut(**t) for t in tasks]


@router.get("/tasks/area", response_model=list[AssignableTaskOut])
def get_area_tasks_for_assignment(
    rayon: str = Query(""),
    status: str = Query(""),
    executor: str = Query(""),
    unassigned_only: bool = Query(False),
    _user: UserSession = Depends(require_manager_or_admin),
) -> list[AssignableTaskOut]:
    with get_connection() as conn:
        tasks = list_area_tasks_for_assignment(
            conn,
            rayon=rayon or None,
            status=status or None,
            executor=executor or None,
            unassigned_only=unassigned_only,
        )
    return [AssignableTaskOut(**t) for t in tasks]


@router.get("/tasks/field/lookup", response_model=FieldSnapshotLookupOut)
def get_field_snapshot_lookup(
    task_key: str = Query(...),
    _user: UserSession = Depends(require_manager_or_admin),
) -> FieldSnapshotLookupOut:
    with get_connection() as conn:
        row = lookup_field_snapshot_by_task_key(conn, task_key)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача в поле не найдена")
    return FieldSnapshotLookupOut(**row)


@router.patch("/tasks/field/{key}", response_model=dict[str, str])
def patch_field_task_executor(
    key: str,
    body: TaskExecutorUpdate,
    user: UserSession = Depends(require_manager_or_admin),
) -> dict[str, str]:
    try:
        with get_connection() as conn:
            result = assign_task_executor(conn, "field", key, body.executor, user.login)
    except PersonnelError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
    return {"status": result}


@router.patch("/tasks/area/{key}", response_model=dict[str, str])
def patch_area_task_executor(
    key: str,
    body: TaskExecutorUpdate,
    user: UserSession = Depends(require_manager_or_admin),
) -> dict[str, str]:
    try:
        with get_connection() as conn:
            result = assign_task_executor(conn, "area", key, body.executor, user.login)
    except PersonnelError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
    return {"status": result}


@router.patch("/tasks/area/{key}/task-number", response_model=dict[str, str])
def patch_area_task_number(
    key: str,
    body: TaskNumberUpdate,
    user: UserSession = Depends(require_admin),
) -> dict[str, str]:
    with get_connection() as conn:
        result = update_area_task_number(conn, key, body.task_number, user.login)
    if result == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
    return {"status": result}


@router.post("/tasks/bulk-assign", response_model=BulkAssignResultOut)
def post_bulk_assign(
    body: BulkAssignRequest,
    user: UserSession = Depends(require_manager_or_admin),
) -> BulkAssignResultOut:
    if body.table not in ("field", "area"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="table must be field or area",
        )
    table: Literal["field", "area"] = body.table  # type: ignore[assignment]
    try:
        with get_connection() as conn:
            result = bulk_assign_task_executor(conn, table, body.keys, body.executor, user.login)
    except PersonnelError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return BulkAssignResultOut(**result)


@router.post("/tasks/bulk-status", response_model=BulkStatusResultOut)
def post_bulk_status(
    body: BulkStatusRequest,
    user: UserSession = Depends(require_manager_or_admin),
) -> BulkStatusResultOut:
    if body.target_status not in ("active", "field", "clear"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target_status must be active, field, or clear",
        )
    with get_connection() as conn:
        result = bulk_change_task_workflow_status(
            conn,
            body.task_keys,
            body.target_status,  # type: ignore[arg-type]
            user.login,
        )
    return BulkStatusResultOut(**result)
