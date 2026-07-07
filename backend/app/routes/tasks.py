"""CRM task routes."""

from __future__ import annotations

import logging
from functools import partial

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from psycopg2 import OperationalError

from app.auth.deps import (
    check_area_status,
    check_rayon,
    check_task_source,
    check_task_source_any,
    get_current_user,
    require_can_collect,
    require_manager_or_admin,
    require_office_or_admin,
)
from app.auth.session import UserSession, allowed_area_statuses, districts_unrestricted
from app.auth.service import fetch_allowed_rayons
from app.config import crm_task_store_config, crm_tasks_config
from app.crm.collector import (
    build_collect_plan,
    collect_layer_tasks,
    collect_layer_to_dict,
    collect_plan_to_dict,
    collect_tasks,
    task_result_to_dict,
)
from app.crm.snapshot_loader import collect_snapshot_tasks, snapshot_result_to_dict
from app.crm.schemas import (
    CollectLayerRequest,
    CollectTasksRequest,
    CreateOfficeTaskRequest,
    FieldPhotosResultOut,
    SendToFieldRequest,
    SnapshotResultOut,
    TaskFormFieldsOut,
    TaskRecordOut,
    TaskRecordUpdate,
)
from app.crm.store import (
    TASK_COLUMN_LABELS,
    TaskRecord,
    fetch_task_by_key,
    fetch_task_for_feature,
    send_task_to_done_illegal,
    send_task_to_done_legal,
    send_task_to_field,
    send_task_to_clear,
    return_task_to_active,
    remove_task_from_field,
    task_key_exists_in_snapshot,
    task_form_field_groups,
    update_task_record,
)
from app.crm.link_resolver import (
    resolve_link_layer_infos,
    resolve_linked_features,
)
from app.crm.office_tasks import create_office_task
from app.photos.field_photo import _field_image_url, fetch_field_photos
from app.crm.tasks_area import (
    AREA_STATUSES,
    collect_tasks_area,
    collect_tasks_area_all,
    fetch_tasks_area_geojson,
    send_area_to_survey,
    release_area_from_survey,
    complete_area_survey,
    complete_area_analise,
    pause_area_analise,
    start_area_analise,
    analise_lock_holder,
    tasks_area_result_to_dict,
)
from app.db import get_connection
from app.layers.geojson import list_districts, lookup_feature
from app.layers.registry import get_registry

router = APIRouter(
    prefix="/api",
    tags=["crm"],
    dependencies=[Depends(get_current_user)],
)


def _record_to_out(record: TaskRecord) -> TaskRecordOut:
    return TaskRecordOut(**record.as_dict())


def _field_executor_login(user: UserSession) -> str | None:
    if user.role == "field":
        return user.login
    return None


def _area_rayons_filter(conn, user: UserSession) -> list[str] | None:
    if districts_unrestricted(user):
        return None
    return fetch_allowed_rayons(conn, user)


def _require_field_task_manager(user: UserSession, conn, store_cfg, task_key: str) -> None:
    if not task_key_exists_in_snapshot(conn, store_cfg, "field_table", "tasks_field", task_key):
        return
    if user.role not in ("admin", "manager"):
        raise HTTPException(
            status_code=403,
            detail="Изменение статуса задачи «В поле» доступно только manager и admin",
        )


def _send_snapshot(
    key: str,
    handler,
    login: str,
    *,
    user: UserSession | None = None,
    remove_from_field_after: bool = False,
) -> SnapshotResultOut:
    store_cfg = crm_task_store_config()
    with get_connection() as conn:
        record = fetch_task_by_key(conn, store_cfg, key)
        if record is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if user is not None:
            _require_field_task_manager(user, conn, store_cfg, key)
        try:
            status = handler(conn, record, store_cfg, login)
            if remove_from_field_after and status in ("inserted", "skipped"):
                remove_task_from_field(conn, record, store_cfg, login)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SnapshotResultOut(status=status)


@router.get("/districts")
def get_districts(user: UserSession = Depends(get_current_user)) -> dict:
    cfg = crm_tasks_config()
    district_cfg = cfg.get("district_filter", {})
    boundaries_layer = district_cfg.get("boundaries_layer", "Границы районов")
    registry = get_registry()
    hood = registry.by_display_name.get(boundaries_layer)
    if hood is None:
        schema, table, field = "odh_export", "hood", district_cfg.get("field", "rayon")
    else:
        schema, table = hood.schema, hood.table_name
        field = district_cfg.get("field", "rayon")

    allowed_gids: list[int] | None = None
    if not districts_unrestricted(user):
        if not user.work_zones:
            return {"districts": []}
        allowed_gids = user.work_zones

    with get_connection() as conn:
        rayons = list_districts(
            conn,
            schema,
            table,
            field,
            exclude_okrug_shor=["НАО", "ТАО"],
            allowed_gids=allowed_gids,
        )
    return {"districts": rayons}


@router.get("/tasks/collect/plan", dependencies=[Depends(require_can_collect)])
def get_collect_plan(
    rayon: str = Query(...),
    apply_date_filter: bool = Query(True),
    user: UserSession = Depends(get_current_user),
) -> dict:
    check_task_source(user, "active")
    check_rayon(user, rayon)
    result, layers = build_collect_plan(rayon, apply_date_filter)
    return collect_plan_to_dict(result, layers)


@router.post("/tasks/collect/layer", dependencies=[Depends(require_can_collect)])
def post_collect_layer(
    body: CollectLayerRequest,
    user: UserSession = Depends(get_current_user),
) -> dict:
    check_task_source(user, "active")
    check_rayon(user, body.rayon)
    try:
        with get_connection() as conn:
            features, errors = collect_layer_tasks(
                conn,
                body.rayon,
                body.apply_date_filter,
                body.group_name,
                body.subgroup_name,
                body.layer_key,
            )
    except OperationalError as exc:
        message = str(exc).lower()
        if "timeout" in message or "canceling statement" in message:
            raise HTTPException(
                status_code=503,
                detail=f"Таймаут при загрузке слоя «{body.layer_key}»",
            ) from exc
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return collect_layer_to_dict(
        body.group_name,
        body.subgroup_name,
        body.layer_key,
        features,
        errors,
    )


@router.post("/tasks/collect/persist", dependencies=[Depends(require_can_collect)])
def post_collect_persist(
    body: CollectTasksRequest,
    user: UserSession = Depends(get_current_user),
) -> dict:
    raise HTTPException(
        status_code=410,
        detail="Создание задач перенесено в ETL; используйте «Обновить активные».",
    )


@router.post("/tasks/collect", dependencies=[Depends(require_can_collect)])
def post_collect_tasks(
    body: CollectTasksRequest,
    user: UserSession = Depends(get_current_user),
) -> dict:
    check_task_source(user, "active")
    check_rayon(user, body.rayon)
    try:
        with get_connection() as conn:
            result, _ = collect_tasks(
                conn,
                body.rayon,
                body.apply_date_filter,
                persist=False,
                filter_sent=True,
            )
    except OperationalError as exc:
        message = str(exc).lower()
        if "timeout" in message or "canceling statement" in message:
            raise HTTPException(
                status_code=503,
                detail="База данных не отвечает вовремя. Проверьте VPS или повторите позже.",
            ) from exc
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    data = task_result_to_dict(result)
    data["task_source"] = "active"
    return data


@router.get("/tasks/lookup/by-feature")
def lookup_task_by_feature(
    subgroup_name: str = Query(...),
    attributes: str = Query(..., description="JSON object of feature attributes"),
    layer_key: str = Query(""),
) -> TaskRecordOut:
    import json

    store_cfg = crm_task_store_config()
    try:
        attrs = json.loads(attributes)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid attributes JSON") from exc

    with get_connection() as conn:
        record = fetch_task_for_feature(
            conn, subgroup_name, attrs, store_cfg, layer_key=layer_key or None
        )
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found in crm.tasks")
    return _record_to_out(record)


@router.get("/tasks/active")
def get_active_tasks(
    rayon: str = Query(...),
    apply_date_filter: bool = Query(True),
    user: UserSession = Depends(get_current_user),
) -> dict:
    check_task_source(user, "active")
    check_rayon(user, rayon)
    with get_connection() as conn:
        result, _ = collect_tasks(
            conn,
            rayon,
            apply_date_filter,
            persist=False,
            filter_sent=True,
        )
    data = task_result_to_dict(result)
    data["task_source"] = "active"
    return data


@router.get("/tasks/snapshot")
def get_snapshot_tasks(
    rayon: str = Query(...),
    source: str = Query(..., description="field | done_legal | done_illegal | clear"),
    user: UserSession = Depends(get_current_user),
) -> dict:
    if source not in ("field", "done_legal", "done_illegal", "clear"):
        raise HTTPException(
            status_code=400,
            detail="source must be field, done_legal, done_illegal, or clear",
        )
    check_task_source(user, source)
    check_rayon(user, rayon)
    with get_connection() as conn:
        result = collect_snapshot_tasks(
            conn,
            rayon,
            source,
            field_executor_login=_field_executor_login(user),
        )
    return snapshot_result_to_dict(result, source)


@router.get("/tasks/area")
def get_tasks_area_list(
    rayon: str = Query(...),
    status: str = Query("", description="Optional: free | wip | done"),
    user: UserSession = Depends(get_current_user),
) -> dict:
    check_rayon(user, rayon)
    if status:
        if status not in AREA_STATUSES:
            raise HTTPException(status_code=400, detail="status must be free, wip, or done")
        check_area_status(user, status)
        with get_connection() as conn:
            result = collect_tasks_area(
                conn,
                rayon,
                status,
                field_executor_login=_field_executor_login(user),
            )
        return tasks_area_result_to_dict(result, "area")

    statuses = allowed_area_statuses(user.role)
    if not statuses:
        raise HTTPException(
            status_code=403,
            detail="Статус площадного заказа недоступен для вашей роли",
        )
    with get_connection() as conn:
        result = collect_tasks_area_all(
            conn,
            rayon,
            statuses,
            field_executor_login=_field_executor_login(user),
        )
    return tasks_area_result_to_dict(result, "area")


@router.get("/tasks/{key}")
def get_task(key: str) -> TaskRecordOut:
    store_cfg = crm_task_store_config()
    with get_connection() as conn:
        record = fetch_task_by_key(conn, store_cfg, key)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _record_to_out(record)


@router.get("/tasks/{key}/form-fields")
def get_task_form_fields(
    key: str,
    group_name: str = Query(""),
    subgroup_name: str = Query(""),
) -> TaskFormFieldsOut:
    store_cfg = crm_task_store_config()
    with get_connection() as conn:
        record = fetch_task_by_key(conn, store_cfg, key)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    readonly, link = task_form_field_groups(group_name, subgroup_name, store_cfg, record)
    return TaskFormFieldsOut(
        readonly_fields=readonly,
        link_fields=link,
        labels=TASK_COLUMN_LABELS,
    )


@router.get("/tasks/{key}/field-photos")
def get_task_field_photos(key: str) -> FieldPhotosResultOut:
    store_cfg = crm_task_store_config()
    with get_connection() as conn:
        record = fetch_task_by_key(conn, store_cfg, key)
        if record is None:
            raise HTTPException(status_code=404, detail="Task not found")
        result = fetch_field_photos(conn, key)
    data = result.to_dict(_field_image_url)
    return FieldPhotosResultOut(**data)


@router.get("/tasks/{key}/linked-features")
def get_linked_features(
    key: str,
    group_name: str = Query(...),
) -> dict:
    store_cfg = crm_task_store_config()
    registry = get_registry()
    with get_connection() as conn:
        record = fetch_task_by_key(conn, store_cfg, key)
        if record is None:
            raise HTTPException(status_code=404, detail="Task not found")
        linked, missing = resolve_linked_features(
            conn, record, group_name, store_cfg, registry
        )
    return {"linked_features": linked, "missing_links": missing}


@router.post("/tasks/office")
def post_create_office_task(
    body: CreateOfficeTaskRequest,
    user: UserSession = Depends(require_office_or_admin),
) -> TaskRecordOut:
    with get_connection() as conn:
        try:
            record = create_office_task(
                conn,
                user.login,
                body.geometry,
                body.area_task_key,
                body.link_prefill,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _record_to_out(record)


@router.patch("/tasks/{key}")
def patch_task(
    key: str,
    body: TaskRecordUpdate,
    user: UserSession = Depends(get_current_user),
) -> TaskRecordOut:
    store_cfg = crm_task_store_config()
    with get_connection() as conn:
        record = fetch_task_by_key(conn, store_cfg, key)
        if record is None:
            raise HTTPException(status_code=404, detail="Task not found")
        updates = body.model_dump(exclude_unset=True)
        for field_name, value in updates.items():
            setattr(record, field_name, value)
        update_task_record(conn, record, store_cfg, user.login)
    return _record_to_out(record)


@router.post("/tasks/{key}/send-to-field")
def post_send_to_field(
    key: str,
    body: SendToFieldRequest,
    user: UserSession = Depends(get_current_user),
) -> SnapshotResultOut:
    check_task_source(user, "active")
    check_rayon(user, body.rayon)
    store_cfg = crm_task_store_config()
    with get_connection() as conn:
        record = fetch_task_by_key(conn, store_cfg, key)
        if record is None:
            raise HTTPException(status_code=404, detail="Task not found")
        try:
            status = send_task_to_field(
                conn,
                record,
                store_cfg,
                user.login,
                office_comment=body.office_comment,
                rayon=body.rayon,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SnapshotResultOut(status=status)


@router.post("/tasks/{key}/close-legal")
def post_close_legal(
    key: str,
    user: UserSession = Depends(get_current_user),
) -> SnapshotResultOut:
    check_task_source_any(user, ["active", "field"])
    return _send_snapshot(
        key,
        send_task_to_done_legal,
        user.login,
        user=user,
        remove_from_field_after=True,
    )


@router.post("/tasks/{key}/close-illegal")
def post_close_illegal(
    key: str,
    user: UserSession = Depends(get_current_user),
) -> SnapshotResultOut:
    check_task_source_any(user, ["active", "field"])
    return _send_snapshot(
        key,
        send_task_to_done_illegal,
        user.login,
        user=user,
        remove_from_field_after=True,
    )


@router.post("/tasks/{key}/disruption-absent")
def post_disruption_absent(
    key: str,
    user: UserSession = Depends(get_current_user),
) -> SnapshotResultOut:
    check_task_source_any(user, ["active", "field"])
    return _send_snapshot(
        key,
        send_task_to_clear,
        user.login,
        user=user,
        remove_from_field_after=True,
    )


@router.post("/tasks/{key}/return-to-active")
def post_return_to_active(
    key: str,
    user: UserSession = Depends(require_manager_or_admin),
) -> SnapshotResultOut:
    check_task_source_any(user, ["field"])
    return _send_snapshot(key, return_task_to_active, user.login, user=user)


@router.get("/features/lookup")
def get_feature_lookup(
    layer_key: str = Query(...),
    source_field: str = Query(...),
    business_id: str = Query(...),
) -> dict:
    registry = get_registry()
    layer = registry.by_key.get(layer_key)
    if layer is None:
        raise HTTPException(status_code=404, detail="Layer not found")

    with get_connection() as conn:
        feature = lookup_feature(conn, layer, source_field, business_id)
    if feature is None:
        raise HTTPException(status_code=404, detail="Feature not found")
    return feature


@router.post("/crm/tasks-area/{key}/send-to-survey")
def post_area_send_to_survey(
    key: str,
    user: UserSession = Depends(get_current_user),
) -> dict:
    with get_connection() as conn:
        result_status = send_area_to_survey(conn, key, user.login)
    if result_status == "not_found":
        raise HTTPException(status_code=404, detail="Area order not found")
    return {"status": result_status}


@router.post("/crm/tasks-area/{key}/release-from-survey")
def post_area_release_from_survey(
    key: str,
    user: UserSession = Depends(get_current_user),
) -> dict:
    with get_connection() as conn:
        result_status = release_area_from_survey(conn, key, user.login)
    if result_status == "not_found":
        raise HTTPException(status_code=404, detail="Area order not found or not on survey")
    return {"status": result_status}


@router.post("/crm/tasks-area/{key}/complete-survey")
def post_area_complete_survey(
    key: str,
    user: UserSession = Depends(get_current_user),
) -> dict:
    with get_connection() as conn:
        result_status = complete_area_survey(conn, key, user.login)
    if result_status == "not_found":
        raise HTTPException(status_code=404, detail="Area order not found or not on survey")
    return {"status": result_status}


@router.post("/crm/tasks-area/{key}/start-analise")
def post_area_start_analise(
    key: str,
    user: UserSession = Depends(require_office_or_admin),
) -> dict:
    with get_connection() as conn:
        result_status = start_area_analise(conn, key, user.login)
        if result_status == "conflict":
            holder = analise_lock_holder(conn, key) or "другой пользователь"
            raise HTTPException(
                status_code=409,
                detail=f"Заказ в работе у пользователя {holder}",
            )
    if result_status == "not_found":
        raise HTTPException(status_code=404, detail="Area order not found")
    return {"status": result_status}


@router.post("/crm/tasks-area/{key}/pause-analise")
def post_area_pause_analise(
    key: str,
    user: UserSession = Depends(require_office_or_admin),
) -> dict:
    with get_connection() as conn:
        result_status = pause_area_analise(conn, key, user.login)
    if result_status == "not_found":
        raise HTTPException(status_code=404, detail="Area order not found or not in progress")
    return {"status": result_status}


@router.post("/crm/tasks-area/{key}/complete-analise")
def post_area_complete_analise(
    key: str,
    user: UserSession = Depends(require_office_or_admin),
) -> dict:
    with get_connection() as conn:
        result_status = complete_area_analise(conn, key, user.login)
    if result_status == "not_found":
        raise HTTPException(status_code=404, detail="Area order not found")
    return {"status": result_status}


@router.get("/crm/tasks-area")
def get_tasks_area(
    rayon: str = Query("", description="Filter by district name"),
    status: str = Query("", description="Optional status filter"),
    user: UserSession = Depends(get_current_user),
) -> dict:
    rayons_filter: list[str] | None = None
    if rayon:
        check_rayon(user, rayon)
    else:
        with get_connection() as conn:
            rayons_filter = _area_rayons_filter(conn, user)
        if rayons_filter is not None and not rayons_filter:
            return {"type": "FeatureCollection", "features": []}

    statuses: list[str] | None = None
    if status:
        if status not in AREA_STATUSES:
            raise HTTPException(status_code=400, detail="status must be free, wip, or done")
        check_area_status(user, status)
    else:
        statuses = allowed_area_statuses(user.role)
        if not statuses:
            raise HTTPException(
                status_code=403,
                detail="Статус площадного заказа недоступен для вашей роли",
            )
    with get_connection() as conn:
        return fetch_tasks_area_geojson(
            conn,
            rayon=rayon or None,
            status=status or None,
            statuses=statuses,
            rayons=rayons_filter if not rayon else None,
            field_executor_login=_field_executor_login(user),
        )


@router.get("/crm/link-layers")
def get_link_layers(columns: str = Query(..., description="Comma-separated task columns")) -> dict:
    """Return layer keys and source fields for link pick on map."""
    store_cfg = crm_task_store_config()
    registry = get_registry()
    column_list = [c.strip() for c in columns.split(",") if c.strip()]
    layers_info = resolve_link_layer_infos(store_cfg, registry, column_list)
    return {"layers": layers_info}
