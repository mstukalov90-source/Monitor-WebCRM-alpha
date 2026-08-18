"""Save public Excel uploads into a shared directory for another server app."""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings

ALLOWED_EXTENSIONS = frozenset({".xlsx", ".xls"})
XLSX_MAGIC = b"PK"
XLS_MAGIC = b"\xd0\xcf\x11\xe0"
_UNSAFE_STEM = re.compile(r"[^\w\-()+]", flags=re.UNICODE)


class ExcelUploadError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class SavedExcel:
    filename: str
    size: int
    saved_at: datetime
    path: Path


def resolved_excel_upload_dir(settings: Settings) -> Path:
    raw = (settings.excel_upload_dir or "").strip() or "./data/excel_inbox"
    path = Path(raw)
    if not path.is_absolute():
        backend_dir = Path(__file__).resolve().parent.parent.parent
        path = (backend_dir / path).resolve()
    return path


def sanitize_original_name(filename: str | None) -> tuple[str, str]:
    """Return (safe_stem, suffix) like ('zayavki', '.xlsx')."""
    raw = Path((filename or "").replace("\\", "/")).name.strip()
    if not raw or raw in {".", ".."}:
        raise ExcelUploadError("Не указано имя файла")

    suffix = Path(raw).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ExcelUploadError("Допустимы только файлы .xlsx и .xls")

    stem = Path(raw).stem
    stem = re.sub(r"\s+", "_", stem)
    stem = _UNSAFE_STEM.sub("_", stem)
    stem = stem.strip("._") or "upload"
    return stem, suffix


def _check_magic(content: bytes, suffix: str) -> None:
    if suffix == ".xlsx":
        if not content.startswith(XLSX_MAGIC):
            raise ExcelUploadError("Файл не похож на Excel (.xlsx)")
        return
    if not content.startswith(XLS_MAGIC):
        raise ExcelUploadError("Файл не похож на Excel (.xls)")


def _unique_dest(dest_dir: Path, filename: str) -> Path:
    dest = dest_dir / filename
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    n = 2
    while True:
        candidate = dest_dir / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def _atomic_write(dest: Path, content: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp_", suffix=dest.suffix, dir=dest.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, dest)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def save_excel_upload(
    content: bytes,
    original_filename: str | None,
    dest_dir: Path,
    max_bytes: int,
    now: datetime | None = None,
) -> SavedExcel:
    if not content:
        raise ExcelUploadError("Файл пустой")
    if len(content) > max_bytes:
        raise ExcelUploadError("Файл слишком большой (максимум 10 МБ)")

    stem, suffix = sanitize_original_name(original_filename)
    _check_magic(content, suffix)

    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    else:
        stamp = stamp.astimezone(timezone.utc)

    filename = f"{stamp:%Y%m%d_%H%M%S}_{stem}{suffix}"
    dest = _unique_dest(dest_dir, filename)
    _atomic_write(dest, content)
    return SavedExcel(
        filename=dest.name,
        size=len(content),
        saved_at=stamp,
        path=dest,
    )
