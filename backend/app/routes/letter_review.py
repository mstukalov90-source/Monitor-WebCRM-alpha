"""Manager review of generated OATI letters."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.deps import require_manager_or_admin
from app.auth.session import UserSession
from app.crm.schemas import OatiLetterReviewOut, OatiLetterReviewUpdate
from app.db import get_connection
from app.letters.oati import LetterError
from app.letters.review import (
    DEFAULT_LETTER_LIST_LIMIT,
    hide_letter,
    list_letters_for_review,
    set_letter_review,
)

router = APIRouter(
    prefix="/api",
    tags=["letter-review"],
    dependencies=[Depends(require_manager_or_admin)],
)


def _http(exc: LetterError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/letters", response_model=list[OatiLetterReviewOut])
def get_letters_for_review(
    limit: int = Query(DEFAULT_LETTER_LIST_LIMIT),
    _user: UserSession = Depends(require_manager_or_admin),
) -> list[OatiLetterReviewOut]:
    try:
        with get_connection() as conn:
            rows = list_letters_for_review(conn, limit=limit)
    except LetterError as exc:
        raise _http(exc) from exc
    return [OatiLetterReviewOut(**row) for row in rows]


@router.patch("/letters/{fid}/review", response_model=OatiLetterReviewOut)
def patch_letter_review(
    fid: int,
    body: OatiLetterReviewUpdate,
    user: UserSession = Depends(require_manager_or_admin),
) -> OatiLetterReviewOut:
    status = body.status
    if status is not None:
        status = status.strip() or None
    if status not in (None, "approved", "rejected"):
        raise HTTPException(status_code=422, detail="status must be approved, rejected, or null")
    try:
        with get_connection() as conn:
            row = set_letter_review(conn, fid, status=status, login=user.login)
    except LetterError as exc:
        raise _http(exc) from exc
    return OatiLetterReviewOut(**row)


@router.post("/letters/{fid}/hide")
def post_hide_letter(
    fid: int,
    user: UserSession = Depends(require_manager_or_admin),
) -> dict[str, str]:
    try:
        with get_connection() as conn:
            hide_letter(conn, fid, login=user.login)
    except LetterError as exc:
        raise _http(exc) from exc
    return {"status": "hidden"}
