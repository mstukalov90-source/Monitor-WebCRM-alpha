"""Field quality score routes (manager/admin)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.deps import require_manager_or_admin
from app.auth.session import UserSession
from app.crm.field_score import (
    FieldScoreError,
    build_field_score_context,
    upsert_field_score,
)
from app.crm.schemas import (
    FieldScoreContextOut,
    FieldScoreSavedOut,
    FieldScoreUpsertRequest,
)
from app.db import get_connection

router = APIRouter(prefix="/api/field-score", tags=["field-score"])


@router.get("/{order_key}", response_model=FieldScoreContextOut)
def get_field_score_context(
    order_key: str,
    _user: UserSession = Depends(require_manager_or_admin),
) -> FieldScoreContextOut:
    try:
        with get_connection() as conn:
            data = build_field_score_context(conn, order_key)
    except FieldScoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return FieldScoreContextOut(**data)


@router.put("/{order_key}", response_model=FieldScoreSavedOut)
def put_field_score(
    order_key: str,
    body: FieldScoreUpsertRequest,
    user: UserSession = Depends(require_manager_or_admin),
) -> FieldScoreSavedOut:
    try:
        with get_connection() as conn:
            data = upsert_field_score(
                conn,
                order_key=order_key,
                scored_by=user.login,
                task_scores=body.task_scores,
                order_score=body.order_score,
            )
    except FieldScoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return FieldScoreSavedOut(**data)
