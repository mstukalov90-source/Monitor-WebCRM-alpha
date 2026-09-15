"""Admin-only GeoPackage import into crm.tasks_area."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.auth.deps import require_admin
from app.auth.session import UserSession
from app.config import get_settings
from app.crm.gpkg_area_import import (
    GpkgAreaImportError,
    import_gpkg_bytes,
    result_to_dict,
    validate_filename,
)
from app.db import get_connection

router = APIRouter(prefix="/api/admin/tasks-area", tags=["gpkg-area"])


class GpkgAreaItemOut(BaseModel):
    key: str
    status: str | None = None
    task_number: str | None = None
    area: float | None = None
    rayon: str | None = None
    okrug_shor: str | None = None


class GpkgAreaImportOut(BaseModel):
    inserted: int
    skipped: int
    layer: str
    srid: int
    items: list[GpkgAreaItemOut] = Field(default_factory=list)


def _raise_import_error(exc: GpkgAreaImportError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/gpkg", response_model=GpkgAreaImportOut, status_code=status.HTTP_201_CREATED)
async def upload_tasks_area_gpkg(
    file: UploadFile = File(...),
    _user: UserSession = Depends(require_admin),
) -> dict[str, Any]:
    settings = get_settings()
    try:
        validate_filename(file.filename)
    except GpkgAreaImportError as exc:
        _raise_import_error(exc)

    content = await file.read()
    if len(content) > settings.gpkg_area_max_bytes:
        raise HTTPException(
            status_code=400,
            detail="Файл слишком большой (максимум 50 МБ)",
        )

    try:
        with get_connection() as conn:
            result = import_gpkg_bytes(
                conn,
                content,
                max_features=settings.gpkg_area_max_features,
            )
    except GpkgAreaImportError as exc:
        _raise_import_error(exc)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось загрузить GeoPackage: {exc}",
        ) from exc
    return result_to_dict(result)
