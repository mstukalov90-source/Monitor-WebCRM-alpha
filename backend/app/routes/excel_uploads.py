"""Public Excel upload for another application on the same server."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import get_settings
from app.excel_upload.store import ExcelUploadError, resolved_excel_upload_dir, save_excel_upload

router = APIRouter(prefix="/api", tags=["excel-uploads"])


class ExcelUploadOut(BaseModel):
    filename: str
    size: int
    saved_at: str


@router.post("/excel-uploads", response_model=ExcelUploadOut)
async def upload_excel(file: UploadFile = File(...)) -> ExcelUploadOut:
    settings = get_settings()
    content = await file.read()
    try:
        saved = save_excel_upload(
            content,
            file.filename,
            resolved_excel_upload_dir(settings),
            settings.excel_upload_max_bytes,
        )
    except ExcelUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ExcelUploadOut(
        filename=saved.filename,
        size=saved.size,
        saved_at=saved.saved_at.isoformat(),
    )
