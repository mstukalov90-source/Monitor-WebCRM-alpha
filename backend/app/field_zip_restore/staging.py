"""In-memory + disk staging for ZIP-close preview tokens."""

from __future__ import annotations

import re
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

PREVIEW_TTL = timedelta(minutes=30)
_UNSAFE = re.compile(r"[^\w.\-()+]", flags=re.UNICODE)

_lock = threading.Lock()
_previews: dict[str, "StagedPreview"] = {}


@dataclass
class StagedFile:
    original_name: str
    path: Path


@dataclass
class StagedPreview:
    preview_id: str
    username: str
    admin_login: str
    created_at: datetime
    zip_dir: Path
    files: list[StagedFile] = field(default_factory=list)

    def expired(self, now: datetime | None = None) -> bool:
        stamp = now or datetime.now(timezone.utc)
        return stamp - self.created_at > PREVIEW_TTL


def sanitize_zip_name(filename: str | None) -> str:
    raw = Path((filename or "").replace("\\", "/")).name.strip()
    if not raw or raw in {".", ".."}:
        return "archive.zip"
    stem = Path(raw).stem
    stem = re.sub(r"\s+", "_", stem)
    stem = _UNSAFE.sub("_", stem).strip("._") or "archive"
    return f"{stem}.zip"


def _drop_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def purge_expired(now: datetime | None = None) -> None:
    stamp = now or datetime.now(timezone.utc)
    with _lock:
        stale = [key for key, item in _previews.items() if item.expired(stamp)]
        for key in stale:
            item = _previews.pop(key)
            _drop_dir(item.zip_dir)


def save_preview(
    *,
    username: str,
    admin_login: str,
    files: list[tuple[str, bytes]],
    staging_root: Path,
) -> StagedPreview:
    purge_expired()
    preview_id = str(uuid.uuid4())
    zip_dir = staging_root / preview_id
    zip_dir.mkdir(parents=True, exist_ok=True)
    staged_files: list[StagedFile] = []
    try:
        for index, (original, payload) in enumerate(files):
            name = f"{index:03d}_{sanitize_zip_name(original)}"
            dest = zip_dir / name
            dest.write_bytes(payload)
            staged_files.append(StagedFile(original_name=Path(original).name or name, path=dest))
    except Exception:
        _drop_dir(zip_dir)
        raise
    preview = StagedPreview(
        preview_id=preview_id,
        username=username,
        admin_login=admin_login,
        created_at=datetime.now(timezone.utc),
        zip_dir=zip_dir,
        files=staged_files,
    )
    with _lock:
        _previews[preview_id] = preview
    return preview


def get_preview(preview_id: str) -> StagedPreview | None:
    purge_expired()
    with _lock:
        item = _previews.get(preview_id)
        if item is None or item.expired():
            return None
        return item


def drop_preview(preview_id: str) -> None:
    with _lock:
        item = _previews.pop(preview_id, None)
    if item is not None:
        _drop_dir(item.zip_dir)


def reset_previews_for_tests() -> None:
    with _lock:
        items = list(_previews.values())
        _previews.clear()
    for item in items:
        _drop_dir(item.zip_dir)
