"""CRM tasks_area list and status workflow."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.crm.collector import TaskFeature, TaskGroup, TaskResult, TaskSubgroup

AREA_LAYER_KEY = "tasks_area"
AREA_LAYER_NAME = "Площадные заказы"
AREA_GROUP_NAME = "Площадные заказы"

AREA_STATUSES = ("free", "wip", "done")

AREA_STATUS_LABELS = {
    "free": "Свободные",
    "wip": "На обследовании",
    "done": "Завершённые",
}


def fetch_tasks_area_geojson(
    conn: PgConnection,
    rayon: str | None = None,
    status: str | None = None,
    limit: int = 5000,
) -> dict[str, Any]:
    filters = ['"geom" IS NOT NULL']
    params: list[Any] = []

    if rayon:
        filters.append('"rayon" = %s')
        params.append(rayon)
    if status:
        filters.append('"status" = %s')
        params.append(status)

    where = " AND ".join(filters)
    params.append(limit)

    query = f"""
        SELECT json_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(json_agg(feature), '[]'::json)
        ) AS geojson
        FROM (
            SELECT json_build_object(
                'type', 'Feature',
                'id', key::text,
                'geometry', ST_AsGeoJSON(geom)::json,
                'properties', to_jsonb(t) - 'geom'
            ) AS feature
            FROM crm.tasks_area t
            WHERE {where}
            ORDER BY loaded_at DESC NULLS LAST
            LIMIT %s
        ) sub
    """

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        row = cur.fetchone()

    if row and row["geojson"]:
        return row["geojson"]
    return {"type": "FeatureCollection", "features": []}


def collect_tasks_area(
    conn: PgConnection,
    rayon: str,
    status: str,
) -> TaskResult:
    if status not in AREA_STATUSES:
        raise ValueError(f"Unknown area status: {status}")

    today = date.today()
    geojson = fetch_tasks_area_geojson(conn, rayon=rayon, status=status)
    features: list[TaskFeature] = []

    for item in geojson.get("features", []):
        props = dict(item.get("properties") or {})
        features.append(
            TaskFeature(
                layer_name=AREA_LAYER_NAME,
                layer_key=AREA_LAYER_KEY,
                attributes=props,
                geometry=item.get("geometry"),
                task_key=str(props.get("key", item.get("id", ""))),
            )
        )

    subgroup = TaskSubgroup(
        name=AREA_STATUS_LABELS.get(status, status),
        features=features,
    )
    group = TaskGroup(name=AREA_GROUP_NAME, subgroups=[subgroup])

    return TaskResult(
        district_name=rayon,
        filter_date_from=today - timedelta(days=3),
        filter_date_to=today,
        apply_date_filter=False,
        groups=[group],
    )


def tasks_area_result_to_dict(result: TaskResult, status: str) -> dict[str, Any]:
    from app.crm.collector import task_result_to_dict

    data = task_result_to_dict(result)
    data["task_source"] = f"area_{status}"
    return data


def send_area_to_survey(conn: PgConnection, key: str) -> str:
    return _transition_area_status(conn, key, from_status=None, to_status="wip", skip_if="wip")


def release_area_from_survey(conn: PgConnection, key: str) -> str:
    return _transition_area_status(conn, key, from_status="wip", to_status="free")


def complete_area_survey(conn: PgConnection, key: str) -> str:
    return _transition_area_status(conn, key, from_status="wip", to_status="done")


def _transition_area_status(
    conn: PgConnection,
    key: str,
    *,
    from_status: str | None,
    to_status: str,
    skip_if: str | None = None,
) -> str:
    if from_status is None:
        where = "key = %s::uuid AND COALESCE(status, '') <> %s"
        params = (key, skip_if or to_status)
    else:
        where = "key = %s::uuid AND status = %s"
        params = (key, from_status)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE crm.tasks_area
            SET status = %s
            WHERE {where}
            RETURNING key
            """,
            (to_status, *params),
        )
        row = cur.fetchone()
    conn.commit()
    if row:
        return "updated"

    with conn.cursor() as cur:
        cur.execute(
            'SELECT status FROM crm.tasks_area WHERE key = %s::uuid',
            (key,),
        )
        existing = cur.fetchone()
    if not existing:
        return "not_found"
    if skip_if and existing[0] == skip_if:
        return "skipped"
    if from_status and existing[0] == from_status:
        return "skipped"
    return "not_found"
