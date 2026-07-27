"""OATI letter generation API routes."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.auth.deps import require_manager_or_admin
from app.auth.session import UserSession
from app.crm.schemas import OatiLetterDraftOut, OatiLetterGenerateRequest
from app.db import get_connection
from app.letters.map_image import DEFAULT_MAP_SCALE
from app.letters.oati import (
    LetterError,
    build_letter_draft,
    generate_letter_docx,
    render_letter_map_preview,
)

router = APIRouter(
    prefix="/api/tasks",
    tags=["letters"],
    dependencies=[Depends(require_manager_or_admin)],
)


@router.get("/{key}/field-reports/{report_id}/letter-draft")
def get_oati_letter_draft(
    key: str,
    report_id: int,
    _user: UserSession = Depends(require_manager_or_admin),
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
    _user: UserSession = Depends(require_manager_or_admin),
) -> Response:
    try:
        with get_connection() as conn:
            png = render_letter_map_preview(conn, key, report_id, scale=scale)
    except LetterError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return Response(content=png, media_type="image/png")


@router.post("/{key}/field-reports/{report_id}/letters")
def post_oati_letter(
    key: str,
    report_id: int,
    body: OatiLetterGenerateRequest,
    user: UserSession = Depends(require_manager_or_admin),
) -> Response:
    try:
        with get_connection() as conn:
            fid, content, filename = generate_letter_docx(
                conn,
                task_key=key,
                report_id=report_id,
                created_by=user.login,
                executor=body.executor or "",
                address=body.address or "",
                engineering=body.engineering or "",
                description=body.description or "",
                violation=body.violation or "",
                photo_ids=list(body.photo_ids or []),
                map_scale=body.map_scale,
            )
    except LetterError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    # RFC 5987 filename* for Cyrillic.
    disposition = (
        f"attachment; filename=\"OATI_letter_{fid}.docx\"; "
        f"filename*=UTF-8''{quote(filename)}"
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": disposition,
            "X-Oati-Letter-Fid": str(fid),
        },
    )
