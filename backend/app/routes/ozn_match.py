"""OZN vs Monitoring area-order spatial matching (manager/admin)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.deps import check_rayon, require_manager_or_admin
from app.auth.service import fetch_allowed_rayons
from app.auth.session import UserSession, districts_unrestricted
from app.crm.ozn_match import (
    OznMatchError,
    empty_ozn_match_result,
    fetch_ozn_matches,
)
from app.crm.schemas import OznMatchResultOut
from app.db import get_connection
from app.layers.geojson import normalize_rayon_name

router = APIRouter(prefix="/api", tags=["ozn-match"])


@router.get("/ozn-match", response_model=OznMatchResultOut)
def get_ozn_match(
    rayon: str | None = Query(None, description="District name (optional)"),
    user: UserSession = Depends(require_manager_or_admin),
) -> OznMatchResultOut:
    rayon_norm = normalize_rayon_name(rayon) if rayon else ""
    if rayon_norm:
        check_rayon(user, rayon_norm)

    with get_connection() as conn:
        allowed_rayons: list[str] | None = None
        if not rayon_norm and not districts_unrestricted(user):
            if not user.work_zones:
                return OznMatchResultOut(**empty_ozn_match_result())
            allowed_rayons = fetch_allowed_rayons(conn, user)
            if not allowed_rayons:
                return OznMatchResultOut(**empty_ozn_match_result())
        try:
            data = fetch_ozn_matches(
                conn,
                rayon=rayon_norm or None,
                allowed_rayons=allowed_rayons,
            )
        except OznMatchError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            ) from exc
    return OznMatchResultOut(**data)
