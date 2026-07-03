"""Order tracks routes (manager/admin)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.auth.deps import check_rayon, require_manager_or_admin
from app.auth.session import UserSession
from app.crm.schemas import OrderTrackOut, OrderTracksResultOut
from app.crm.tracks_loader import fetch_order_tracks
from app.db import get_connection

router = APIRouter(prefix="/api", tags=["order-tracks"])


@router.get("/order-tracks", response_model=OrderTracksResultOut)
def get_order_tracks(
    rayon: str = Query(..., description="District name"),
    user: UserSession = Depends(require_manager_or_admin),
) -> OrderTracksResultOut:
    check_rayon(user, rayon)
    with get_connection() as conn:
        tracks, errors = fetch_order_tracks(conn, rayon)
    return OrderTracksResultOut(
        district_name=rayon,
        tracks=[OrderTrackOut(**t) for t in tracks],
        errors=errors,
    )
