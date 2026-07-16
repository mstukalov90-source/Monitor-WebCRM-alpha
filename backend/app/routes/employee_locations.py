"""Employee real-time location routes (manager/admin)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.auth.deps import check_rayon, require_manager_or_admin
from app.auth.session import UserSession
from app.crm.employee_locations_loader import (
    fetch_all_employee_locations,
    fetch_employee_locations,
)
from app.crm.schemas import EmployeeLocationOut, EmployeeLocationsResultOut
from app.db import get_connection

router = APIRouter(prefix="/api", tags=["employee-locations"])


@router.get("/employee-locations", response_model=EmployeeLocationsResultOut)
def get_employee_locations(
    rayon: str | None = Query(None, description="District name (optional)"),
    user: UserSession = Depends(require_manager_or_admin),
) -> EmployeeLocationsResultOut:
    with get_connection() as conn:
        if rayon is None:
            locations, errors = fetch_all_employee_locations(conn)
            district_name = "Все районы"
        else:
            check_rayon(user, rayon)
            locations, errors = fetch_employee_locations(conn, rayon)
            district_name = rayon
    return EmployeeLocationsResultOut(
        district_name=district_name,
        locations=[EmployeeLocationOut(**loc) for loc in locations],
        errors=errors,
    )
