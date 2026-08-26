"""OATI letter generation API routes."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.auth.deps import require_can_generate_letters
from app.auth.session import UserSession
from app.crm.schemas import (
    OatiLetterDraftOut,
    OatiLetterGenerateOut,
    OatiLetterGenerateRequest,
)
from app.db import get_connection
from app.letters.map_image import DEFAULT_MAP_SCALE
from app.letters.oati import (
    LetterError,
    assert_letter_belongs_to_report,
    build_letter_draft,
    generate_letter_docx,
    load_letter_docx,
    render_letter_map_preview,
)

router = APIRouter(
    prefix="/api/tasks",
    tags=["letters"],
    dependencies=[Depends(require_can_generate_letters)],
)


@router.get("/{key}/field-reports/{report_id}/letter-draft")
def get_oati_letter_draft(
    key: str,
    report_id: int,
    _user: UserSession = Depends(require_can_generate_letters),
) -> OatiLetterDraftOut:
    try:
        with get_connection() as conn:
            draft = build_letter_draft(conn, key, report_id)
    except LetterError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return OatiLetterDraftOut(**draft.to_dict())


@router.get("/{key}/field-reports/{report_id}/map-preview")
def get_oati_map_preview(
    key: str,
    report_id: int,
    scale: int = Query(DEFAULT_MAP_SCALE),
    _user: UserSession = Depends(require_can_generate_letters),
) -> Response:
    try:
        with get_connection() as conn:
            png = render_letter_map_preview(conn, key, report_id, scale=scale)
    except LetterError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return Response(content=png, media_type="image/png")


@router.post("/{key}/field-reports/{report_id}/letters", response_model=OatiLetterGenerateOut)
def post_oati_letter(
    key: str,
    report_id: int,
    body: OatiLetterGenerateRequest,
    user: UserSession = Depends(require_can_generate_letters),
) -> OatiLetterGenerateOut:
    """Generate DOCX, cache it, return JSON with download URL (native browser download)."""
    try:
        with get_connection() as conn:
            fid, _content, filename = generate_letter_docx(
                conn,
                task_key=key,
                report_id=report_id,
                created_by=user.login,
                customer=body.customer or "",
                executor=body.executor or "",
                address=body.address or "",
                engineering=body.engineering or "",
                description=body.description or "",
                violation=body.violation or "",
                violation_names=list(body.violation_names or []),
                photo_ids=list(body.photo_ids or []),
                map_scale=body.map_scale,
                sps=body.sps or "",
                kgs=body.kgs or "",
            )
    except LetterError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    download_url = (
        f"/api/tasks/{quote(key, safe='')}/field-reports/{int(report_id)}"
        f"/letters/{int(fid)}/download"
    )
    return OatiLetterGenerateOut(fid=fid, filename=filename, download_url=download_url)


@router.get("/{key}/field-reports/{report_id}/letters/{fid}/download")
def download_oati_letter(
    key: str,
    report_id: int,
    fid: int,
    _user: UserSession = Depends(require_can_generate_letters),
) -> Response:
    """Stream cached DOCX; Cyrillic name via Content-Disposition (Chrome-safe)."""
    try:
        with get_connection() as conn:
            assert_letter_belongs_to_report(
                conn, fid=fid, task_key=key, report_id=report_id
            )
        content, filename = load_letter_docx(fid)
    except LetterError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    ascii_name = f"OATI_letter_{fid}.docx"
    disposition = (
        f"attachment; filename=\"{ascii_name}\"; "
        f"filename*=UTF-8''{quote(filename)}"
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": disposition,
            "Cache-Control": "no-store",
        },
    )
