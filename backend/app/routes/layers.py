"""Layer and GeoJSON routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.deps import apply_hood_filter_to_layer, get_current_user
from app.auth.session import UserSession
from app.config import get_settings
from app.db import get_connection
from app.layers.geojson import fetch_geojson
from app.layers.registry import get_registry

router = APIRouter(
    prefix="/api",
    tags=["layers"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/config/layers")
def get_layers_config() -> dict:
    registry = get_registry()
    return {"groups": registry.to_config_tree()}


@router.get("/geojson/{layer_key}")
def get_geojson(
    layer_key: str,
    bbox: str = Query(..., description="minLon,minLat,maxLon,maxLat"),
    limit: Optional[int] = None,
    user: UserSession = Depends(get_current_user),
) -> dict:
    registry = get_registry()
    layer = registry.by_key.get(layer_key)
    if layer is None:
        raise HTTPException(status_code=404, detail=f"Layer {layer_key} not found")

    layer = apply_hood_filter_to_layer(layer, user)
    settings = get_settings()
    effective_limit = limit or settings.geojson_default_limit

    try:
        with get_connection() as conn:
            return fetch_geojson(conn, layer, bbox, effective_limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
