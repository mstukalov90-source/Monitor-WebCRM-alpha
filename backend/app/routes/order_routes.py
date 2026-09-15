"""Order route routes (field / manager / admin) — OSRM survey routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.responses import Response

from app.auth.deps import check_rayon, require_order_route_access
from app.auth.session import UserSession
from app.crm.order_route import (
    OrderRouteError,
    build_order_route,
    fetch_route_geojson_export,
    fetch_saved_route,
)
from app.crm.schemas import OrderRouteBuildRequest, OrderRouteContextOut
from app.db import get_connection
from app.routing.gpx_export import route_to_gpx
from app.routing.osrm_profiles import FILE_LETTER, route_content_disposition

router = APIRouter(prefix="/api/crm/tasks-area", tags=["order-routes"])


def _ensure_order_rayon_allowed(user: UserSession, key: str) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT rayon FROM crm.tasks_area WHERE key = %s::uuid LIMIT 1",
                (key,),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    rayon = row[0]
    if rayon:
        check_rayon(user, str(rayon))


@router.post("/{key}/build-route", response_model=OrderRouteContextOut)
def post_build_route(
    key: str,
    body: OrderRouteBuildRequest | None = None,
    user: UserSession = Depends(require_order_route_access),
) -> OrderRouteContextOut:
    _ensure_order_rayon_allowed(user, key)
    start = None
    profile = "foot"
    if body:
        if body.start_lng is not None and body.start_lat is not None:
            start = (body.start_lng, body.start_lat)
        profile = body.profile
    try:
        with get_connection() as conn:
            data = build_order_route(
                conn,
                key,
                start_lng_lat=start,
                actor_login=user.login,
                profile=profile,
            )
    except OrderRouteError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return OrderRouteContextOut(**data)


@router.get("/{key}/route", response_model=OrderRouteContextOut)
def get_route(
    key: str,
    user: UserSession = Depends(require_order_route_access),
) -> OrderRouteContextOut:
    _ensure_order_rayon_allowed(user, key)
    with get_connection() as conn:
        data = fetch_saved_route(conn, key)
    if data is None:
        raise HTTPException(status_code=404, detail="Маршрут ещё не построен")
    return OrderRouteContextOut(**data)


@router.get("/{key}/route.gpx")
def get_route_gpx(
    key: str,
    user: UserSession = Depends(require_order_route_access),
) -> Response:
    _ensure_order_rayon_allowed(user, key)
    with get_connection() as conn:
        data = fetch_saved_route(conn, key)
    if data is None:
        raise HTTPException(status_code=404, detail="Маршрут ещё не построен")

    order_info = data.get("order") or {}
    profile = str(data.get("profile") or "foot")
    task_number = order_info.get("task_number")
    letter = FILE_LETTER.get(profile, "П")
    name = f"{task_number or key[:8]}_{letter}"
    gpx_xml = route_to_gpx(data.get("route_geometry"), name=name)

    return Response(
        content=gpx_xml,
        media_type="application/gpx+xml",
        headers={
            "Content-Disposition": route_content_disposition(
                task_number, key, profile, "gpx"
            ),
        },
    )


@router.get("/{key}/route.geojson")
def get_route_geojson(
    key: str,
    user: UserSession = Depends(require_order_route_access),
) -> Response:
    _ensure_order_rayon_allowed(user, key)
    with get_connection() as conn:
        fc = fetch_route_geojson_export(conn, key)
    if fc is None:
        raise HTTPException(status_code=404, detail="Маршрут ещё не построен")
    profile = "foot"
    task_number = None
    for feat in fc.get("features") or []:
        props = feat.get("properties") or {}
        if props.get("layer") == "route":
            profile = str(props.get("profile") or "foot")
            task_number = props.get("task_number")
            break
    return Response(
        content=json.dumps(fc, ensure_ascii=False).encode("utf-8"),
        media_type="application/geo+json",
        headers={
            "Content-Disposition": route_content_disposition(
                task_number, key, profile, "geojson"
            ),
        },
    )
