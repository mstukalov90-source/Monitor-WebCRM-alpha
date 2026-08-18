"""Preview / apply orchestration for admin ZIP close."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.field_zip_restore.clients import PgClient
from app.field_zip_restore.parse import parse_zip
from app.field_zip_restore.plan import RestorePlan, apply_plan, build_plan, warn_missing_photos
from app.field_zip_restore.staging import (
    drop_preview,
    get_preview,
    save_preview,
)


class ZipCloseError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def ensure_field_user(conn: PgConnection, login: str) -> str:
    name = (login or "").strip()
    if not name:
        raise ZipCloseError("Не выбран пользователь, который закрывает ZIP")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT login
            FROM crm.users
            WHERE login = %s AND role = 'field'
            """,
            (name,),
        )
        row = cur.fetchone()
    if not row:
        raise ZipCloseError("Пользователь с ролью field не найден")
    return str(row["login"])


def read_zip_uploads(
    files: list[tuple[str, bytes]],
    *,
    max_files: int,
    max_bytes: int,
) -> list[tuple[str, bytes]]:
    if not files:
        raise ZipCloseError("Загрузите хотя бы один ZIP")
    if len(files) > max_files:
        raise ZipCloseError(f"Слишком много файлов (максимум {max_files})")
    payloads: list[tuple[str, bytes]] = []
    total = 0
    for name, content in files:
        filename = name or "archive.zip"
        suffix = Path(filename).suffix.lower()
        if suffix != ".zip":
            raise ZipCloseError(f"{filename}: нужен файл .zip")
        if not content:
            raise ZipCloseError(f"{filename}: файл пустой")
        if not content.startswith(b"PK"):
            raise ZipCloseError(f"{filename}: файл не похож на ZIP")
        total += len(content)
        if total > max_bytes:
            raise ZipCloseError(
                f"Суммарный размер ZIP слишком большой (максимум {max_bytes // (1024 * 1024)} МБ)"
            )
        payloads.append((filename, content))
    return payloads


def plan_to_item(plan: RestorePlan, *, applied: bool | None = None, apply_error: str | None = None) -> dict[str, Any]:
    archive = plan.archive
    db_status = plan.area_status
    if archive.kind == "field_order":
        if plan.field_key:
            db_status = "tasks_field"
        elif plan.skip_reason and "already restored" in (plan.skip_reason or ""):
            db_status = "already_closed"
    item: dict[str, Any] = {
        "filename": plan.original_name or archive.path.name,
        "kind": archive.kind,
        "order_number": archive.order_number,
        "order_uuid": archive.order_uuid,
        "rayon": archive.rayon,
        "outcome": plan.outcome,
        "will_write": plan.will_write,
        "close_kind": plan.close_kind,
        "photo_count": len(plan.photos),
        "db_status": db_status,
        "actions": list(plan.actions),
        "warnings": list(plan.warnings),
        "skip_reason": plan.skip_reason,
        "error": None,
    }
    if applied is not None:
        item["applied"] = applied
        item["apply_error"] = apply_error
    return item


def error_item(filename: str, message: str) -> dict[str, Any]:
    return {
        "filename": filename,
        "kind": "unknown",
        "order_number": None,
        "order_uuid": None,
        "rayon": None,
        "outcome": "error",
        "will_write": False,
        "close_kind": None,
        "photo_count": 0,
        "db_status": None,
        "actions": [],
        "warnings": [],
        "skip_reason": None,
        "error": message,
    }


def _plan_for_file(path: Path, original_name: str, username: str, client: PgClient) -> RestorePlan:
    archive = parse_zip(path)
    plan = build_plan(archive, username, client)
    plan.original_name = original_name
    warn_missing_photos(plan)
    return plan


def preview_files(
    conn: PgConnection,
    *,
    username: str,
    admin_login: str,
    files: list[tuple[str, bytes]],
    staging_root: Path,
) -> dict[str, Any]:
    login = ensure_field_user(conn, username)
    if not files:
        raise ZipCloseError("Загрузите хотя бы один ZIP")
    staged = save_preview(
        username=login,
        admin_login=admin_login,
        files=files,
        staging_root=staging_root,
    )
    client = PgClient(conn)
    items: list[dict[str, Any]] = []
    try:
        for staged_file in staged.files:
            try:
                plan = _plan_for_file(staged_file.path, staged_file.original_name, login, client)
                items.append(plan_to_item(plan))
            except Exception as exc:  # noqa: BLE001 — surface parse errors per file
                items.append(error_item(staged_file.original_name, str(exc)))
    except Exception:
        drop_preview(staged.preview_id)
        raise
    return {
        "preview_id": staged.preview_id,
        "username": login,
        "can_apply": any(item["will_write"] for item in items),
        "items": items,
    }


def apply_preview(
    conn: PgConnection,
    *,
    preview_id: str,
    username: str,
    admin_login: str,
    photo_dir: Path,
) -> dict[str, Any]:
    login = ensure_field_user(conn, username)
    staged = get_preview(preview_id)
    if staged is None:
        raise ZipCloseError("Проверка устарела или не найдена. Загрузите ZIP снова.")
    if staged.username != login:
        raise ZipCloseError("Пользователь не совпадает с проверкой")
    if staged.admin_login != admin_login:
        raise ZipCloseError("Эту проверку создал другой администратор")

    client = PgClient(conn)
    items: list[dict[str, Any]] = []
    try:
        for staged_file in staged.files:
            try:
                plan = _plan_for_file(staged_file.path, staged_file.original_name, login, client)
            except Exception as exc:  # noqa: BLE001
                items.append(error_item(staged_file.original_name, str(exc)))
                continue
            if not plan.will_write:
                row = plan_to_item(plan, applied=False, apply_error=None)
                items.append(row)
                continue
            try:
                apply_plan(plan, client, str(photo_dir))
                items.append(plan_to_item(plan, applied=True, apply_error=None))
            except Exception as exc:  # noqa: BLE001 — isolate per ZIP
                items.append(plan_to_item(plan, applied=False, apply_error=str(exc)))
    finally:
        drop_preview(preview_id)

    return {
        "username": login,
        "applied_count": sum(1 for item in items if item.get("applied")),
        "items": items,
    }
