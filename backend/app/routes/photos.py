"""AI photo viewing routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response

from app.config import get_settings
from app.db import get_connection
from app.photos.ai_photo import (
    PhotoFetchError,
    fetch_photo_bytes,
    media_type_for_path,
    photo_file_path,
    photo_remote_configured,
    read_local_photo,
    resolve_ai_photo,
)
from app.photos.sftp_fetch import (
    SftpPhotoError,
    ensure_photo_cached,
    photo_available_locally,
    resolved_cache_dir,
    sftp_configured,
)
from app.auth.deps import get_current_user

router = APIRouter(
    prefix="/api/photos",
    tags=["photos"],
    dependencies=[Depends(get_current_user)],
)


def _image_url(uuid: str) -> str:
    return f"/api/photos/ai/{uuid}/image"


def _photo_is_available(settings, image_name: str) -> bool:
    storage_dir = Path(settings.photo_storage_dir)
    cache_dir = resolved_cache_dir(settings) if settings.photo_local_cache_dir else None
    if photo_available_locally(image_name, storage_dir, cache_dir):
        return True
    if sftp_configured(settings):
        return True
    return photo_remote_configured(
        settings.photo_proxy_base_url,
        settings.photo_static_base_url,
    )


@router.get("/ai/{uuid}/meta")
def get_ai_photo_meta(uuid: str) -> dict:
    settings = get_settings()
    with get_connection() as conn:
        meta = resolve_ai_photo(conn, uuid)
    if meta is None:
        raise HTTPException(status_code=404, detail="Photo not found in photo_meta")

    if not _photo_is_available(settings, meta.image_name):
        raise HTTPException(status_code=404, detail="Photo file not found on server")

    return meta.to_dict(_image_url(meta.uuid))


@router.get("/ai/{uuid}/image")
def get_ai_photo_image(uuid: str) -> Response:
    settings = get_settings()
    with get_connection() as conn:
        meta = resolve_ai_photo(conn, uuid)
    if meta is None:
        raise HTTPException(status_code=404, detail="Photo not found in photo_meta")

    base_dir = Path(settings.photo_storage_dir)
    cache_dir = resolved_cache_dir(settings)

    local_path = photo_file_path(meta.image_name, base_dir)
    if local_path is None:
        local_path = photo_file_path(meta.image_name, cache_dir)

    if local_path is None and sftp_configured(settings):
        try:
            local_path = ensure_photo_cached(meta.image_name, settings)
        except SftpPhotoError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    if local_path is not None:
        return FileResponse(
            path=local_path,
            media_type=media_type_for_path(local_path),
            headers={"Cache-Control": "private, max-age=3600"},
        )

    try:
        content, media_type = fetch_photo_bytes(
            meta,
            storage_dir=base_dir,
            proxy_base_url=settings.photo_proxy_base_url,
            static_base_url=settings.photo_static_base_url,
        )
    except PhotoFetchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )
