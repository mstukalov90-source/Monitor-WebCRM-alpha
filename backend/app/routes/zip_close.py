"""Admin-only close of field/area orders from FieldControl ZIP archives."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.auth.deps import require_admin
from app.auth.session import UserSession
from app.config import Settings, get_settings
from app.db import get_connection
from app.field_zip_restore.service import ZipCloseError, apply_preview, preview_files, read_zip_uploads
from app.photos.field_photo import field_photo_storage_dir

router = APIRouter(prefix="/api/admin/zip-close", tags=["zip-close"])


class ZipCloseApplyIn(BaseModel):
    preview_id: str = Field(..., min_length=8)
    username: str = Field(..., min_length=1)


def resolved_zip_close_staging_dir(settings: Settings) -> Path:
    raw = (settings.zip_close_staging_dir or "").strip() or "./data/zip_close_staging"
    path = Path(raw)
    if not path.is_absolute():
        backend_dir = Path(__file__).resolve().parent.parent.parent
        path = (backend_dir / path).resolve()
    return path


def _raise_zip_error(exc: ZipCloseError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


async def _read_zip_uploads(
    files: list[UploadFile],
    *,
    max_files: int,
    max_bytes: int,
) -> list[tuple[str, bytes]]:
    raw: list[tuple[str, bytes]] = []
    for upload in files:
        name = upload.filename or "archive.zip"
        content = await upload.read()
        raw.append((name, content))
    try:
        return read_zip_uploads(raw, max_files=max_files, max_bytes=max_bytes)
    except ZipCloseError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/preview")
async def preview_zip_close(
    username: str = Form(...),
    files: list[UploadFile] = File(...),
    user: UserSession = Depends(require_admin),
) -> dict:
    settings = get_settings()
    payloads = await _read_zip_uploads(
        files,
        max_files=settings.zip_close_max_files,
        max_bytes=settings.zip_close_max_bytes,
    )
    try:
        with get_connection() as conn:
            return preview_files(
                conn,
                username=username,
                admin_login=user.login,
                files=payloads,
                staging_root=resolved_zip_close_staging_dir(settings),
            )
    except ZipCloseError as exc:
        _raise_zip_error(exc)


@router.post("/apply")
def apply_zip_close(
    body: ZipCloseApplyIn,
    user: UserSession = Depends(require_admin),
) -> dict:
    settings = get_settings()
    try:
        with get_connection() as conn:
            return apply_preview(
                conn,
                preview_id=body.preview_id.strip(),
                username=body.username,
                admin_login=user.login,
                photo_dir=field_photo_storage_dir(settings),
            )
    except ZipCloseError as exc:
        _raise_zip_error(exc)
