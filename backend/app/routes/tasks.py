"""CRM task routes."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from psycopg2 import OperationalError

from app.config import crm_task_store_config, crm_tasks_config
from app.crm.collector import (
    build_collect_plan,
    collect_layer_tasks,
    collect_layer_to_dict,
    collect_plan_to_dict,
    collect_tasks,
    persist_district_tasks,
    task_result_to_dict,
)
from app.crm.snapshot_loader import collect_snapshot_tasks, snapshot_result_to_dict
from app.crm.schemas import (
    CollectLayerRequest,
    CollectTasksRequest,
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
    task_form_field_groups,
    update_task_record,
)
from app.crm.link_resolver import resolve_link_layer_infos, resolve_linked_features
from app.crm.tasks_area import (
    AREA_STATUSES,
    collect_tasks_area,
    fetch_tasks_area_geojson,
    send_area_to_survey,
    release_area_from_survey,
    complete_area_survey,
    tasks_area_result_to_dict,
)
from app.db import get_connection
from app.layers.geojson import list_districts, lookup_feature
from app.layers.registry import get_registry

router = APIRouter(prefix="/api", tags=["crm"])


def _background_persist_tasks(rayon: str, apply_date_filter: bool) -> None:
    try:
        with get_connection() as conn:
            persist_district_tasks(conn, rayon, apply_date_filter)
    except Exception:
        pass


def _record_to_out(record: TaskRecord) -> TaskRecordOut:
    return TaskRecordOut(**record.as_dict())


@router.get("/districts")
def get_districts() -> dict:
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

    with get_connection() as conn:
        rayons = list_districts(
            conn,
            schema,
            table,
            field,
            exclude_okrug_shor=["НАО", "ТАО"],
        )
    return {"districts": rayons}


@router.get("/tasks/collect/plan")
def get_collect_plan(
    rayon: str = Query(...),
    apply_date_filter: bool = Query(True),
) -> dict:
    result, layers = build_collect_plan(rayon, apply_date_filter)
    return collect_plan_to_dict(result, layers)


@router.post("/tasks/collect/layer")
def post_collect_layer(body: CollectLayerRequest) -> dict:
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


@router.post("/tasks/collect/persist")
def post_collect_persist(
    body: CollectTasksRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    background_tasks.add_task(_background_persist_tasks, body.rayon, body.apply_date_filter)
    return {"status": "pending"}


@router.post("/tasks/collect")
def post_collect_tasks(
    body: CollectTasksRequest,
    background_tasks: BackgroundTasks,
) -> dict:
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
    data["persist_stats"] = {
        "inserted": 0,
        "skipped": 0,
        "invalid": 0,
        "pending": True,
    }
    background_tasks.add_task(_background_persist_tasks, body.rayon, body.apply_date_filter)
    return data


@router.get("/tasks/lookup/by-feature")
def lookup_task_by_feature(
    subgroup_name: str = Query(...),
    attributes: str = Query(..., description="JSON object of feature attributes"),
) -> TaskRecordOut:
    import json

    store_cfg = crm_task_store_config()
    try:
        attrs = json.loads(attributes)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid attributes JSON") from exc

    with get_connection() as conn:
        record = fetch_task_for_feature(conn, subgroup_name, attrs, store_cfg)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found in crm.tasks")
    return _record_to_out(record)


@router.get("/tasks/active")
def get_active_tasks(
    rayon: str = Query(...),
    apply_date_filter: bool = Query(True),
) -> dict:
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
) -> dict:
    if source not in ("field", "done_legal", "done_illegal", "clear"):
        raise HTTPException(
            status_code=400,
            detail="source must be field, done_legal, done_illegal, or clear",
        )
    with get_connection() as conn:
        result = collect_snapshot_tasks(conn, rayon, source)
    return snapshot_result_to_dict(result, source)


@router.get("/tasks/area")
def get_tasks_area_list(
    rayon: str = Query(...),
    status: str = Query(..., description="free | wip | done"),
) -> dict:
    if status not in AREA_STATUSES:
        raise HTTPException(status_code=400, detail="status must be free, wip, or done")
    with get_connection() as conn:
        result = collect_tasks_area(conn, rayon, status)
    return tasks_area_result_to_dict(result, status)


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


@router.patch("/tasks/{key}")
def patch_task(key: str, body: TaskRecordUpdate) -> TaskRecordOut:
    store_cfg = crm_task_store_config()
    with get_connection() as conn:
        record = fetch_task_by_key(conn, store_cfg, key)
        if record is None:
            raise HTTPException(status_code=404, detail="Task not found")
        updates = body.model_dump(exclude_unset=True)
        for field_name, value in updates.items():
            setattr(record, field_name, value)
        update_task_record(conn, record, store_cfg)
    return _record_to_out(record)


@router.post("/tasks/{key}/send-to-field")
def post_send_to_field(key: str) -> SnapshotResultOut:
    return _send_snapshot(key, send_task_to_field)


@router.post("/tasks/{key}/close-legal")
def post_close_legal(key: str) -> SnapshotResultOut:
    return _send_snapshot(key, send_task_to_done_legal)


@router.post("/tasks/{key}/close-illegal")
def post_close_illegal(key: str) -> SnapshotResultOut:
    return _send_snapshot(key, send_task_to_done_illegal)


@router.post("/tasks/{key}/disruption-absent")
def post_disruption_absent(key: str) -> SnapshotResultOut:
    return _send_snapshot(key, send_task_to_clear)


def _send_snapshot(key: str, handler) -> SnapshotResultOut:
    store_cfg = crm_task_store_config()
    with get_connection() as conn:
        record = fetch_task_by_key(conn, store_cfg, key)
        if record is None:
            raise HTTPException(status_code=404, detail="Task not found")
        status = handler(conn, record, store_cfg)
    return SnapshotResultOut(status=status)


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
def post_area_send_to_survey(key: str) -> dict:
    with get_connection() as conn:
        result_status = send_area_to_survey(conn, key)
    if result_status == "not_found":
        raise HTTPException(status_code=404, detail="Area order not found")
    return {"status": result_status}


@router.post("/crm/tasks-area/{key}/release-from-survey")
def post_area_release_from_survey(key: str) -> dict:
    with get_connection() as conn:
        result_status = release_area_from_survey(conn, key)
    if result_status == "not_found":
        raise HTTPException(status_code=404, detail="Area order not found or not on survey")
    return {"status": result_status}


@router.post("/crm/tasks-area/{key}/complete-survey")
def post_area_complete_survey(key: str) -> dict:
    with get_connection() as conn:
        result_status = complete_area_survey(conn, key)
    if result_status == "not_found":
        raise HTTPException(status_code=404, detail="Area order not found or not on survey")
    return {"status": result_status}


@router.get("/crm/tasks-area")
def get_tasks_area(
    rayon: str = Query("", description="Filter by district name"),
    status: str = Query("", description="Optional status filter"),
) -> dict:
    with get_connection() as conn:
        return fetch_tasks_area_geojson(
            conn,
            rayon=rayon or None,
            status=status or None,
        )


@router.get("/crm/link-layers")
def get_link_layers(columns: str = Query(..., description="Comma-separated task columns")) -> dict:
    """Return layer keys and source fields for link pick on map."""
    store_cfg = crm_task_store_config()
    registry = get_registry()
    column_list = [c.strip() for c in columns.split(",") if c.strip()]
    layers_info = resolve_link_layer_infos(store_cfg, registry, column_list)
    return {"layers": layers_info}
