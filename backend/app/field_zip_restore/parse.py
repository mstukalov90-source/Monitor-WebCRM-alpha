"""Parse FieldControl order ZIP archives (manifest, draws, track, photos)."""

from __future__ import annotations

import json
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo

MOSCOW = ZoneInfo("Europe/Moscow")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
CAPTURE_RE = re.compile(r"capture_(\d{8})_(\d{6})")
PHOTO_NS = uuid.UUID("9c3a0b1e-4d2f-5a67-8b90-123456789abc")

EVENT_LABELS = {
    "DISRUPTION": "Разрытие",
    "NO_DISRUPTION": "Разрытие отсутствует",
}
PRIMARY_PHOTO_SLOTS = ("EVENT", "BANNER", "COMMUNICATION", "EXCLUSION_ZONE", "CONFIRMATION")
SKIP_AREA_KEYS = frozenset({"2408263b-7664-426e-96ad-e9b7cedc16ac"})
AREA_CLOSE_STATUSES = frozenset({"wip_field"})
JUNK_TRACK_MAX_SEC = 5
JUNK_TRACK_MAX_UNIQUE_POINTS = 2


@dataclass(frozen=True)
class ZipPhoto:
    slot: str
    zip_path: str
    device_path: str | None = None


@dataclass(frozen=True)
class DrawSubmission:
    id: str
    kind: str
    event_type: str | None
    created_at_ms: int | None
    lat: float
    lon: float
    comment: str | None
    photos: tuple[ZipPhoto, ...]
    linked_feature_key: str | None = None


@dataclass(frozen=True)
class FeatureEdit:
    registry_key: str
    observation_status: str | None
    linked_task_key: str | None
    company: str | None
    attributes: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class TrackSession:
    task_key: str
    started_at_ms: int
    duration_sec: int
    points: tuple[tuple[float, float], ...]  # (lon, lat) for GeoJSON


@dataclass
class FieldZipArchive:
    path: Path
    kind: str  # field_order | area
    raw_task_key: str
    order_uuid: str
    order_number: str | None
    rayon: str | None
    exported_at: datetime | None
    submissions: tuple[DrawSubmission, ...]
    features: tuple[FeatureEdit, ...]
    track: TrackSession | None
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def as_clear(self) -> bool:
        return should_complete_as_clear(self.submissions)

    @property
    def unique_track_points(self) -> int:
        if self.track is None:
            return 0
        return len({(round(lon, 6), round(lat, 6)) for lon, lat in self.track.points})


def normalize_order_key(raw: str | None) -> str | None:
    """Strip area:/feature- prefixes and return a lowercase UUID, or None."""
    if not raw:
        return None
    value = raw.strip()
    if value.lower().startswith("area:"):
        value = value[5:]
    if value.lower().startswith("feature-"):
        value = value[len("feature-") :]
    hash_index = value.find("#")
    if hash_index >= 0:
        value = value[:hash_index]
    value = value.lower()
    return value if UUID_RE.match(value) else None


def should_complete_as_clear(submissions: Sequence[DrawSubmission]) -> bool:
    """Match TasksFieldPointSyncCoordinator.shouldCompleteAsClear."""
    if not submissions:
        return False
    return all(item.event_type != "DISRUPTION" for item in submissions)


def event_comment(submission: DrawSubmission) -> str:
    if submission.event_type == "NO_DISRUPTION":
        parts = [EVENT_LABELS["NO_DISRUPTION"]]
        text = (submission.comment or "").strip()
        if text:
            parts.append(text)
        return " · ".join(parts)
    label = EVENT_LABELS.get(submission.event_type or "", submission.event_type or "")
    text = (submission.comment or "").strip()
    return text or label


def company_from_features(features: Sequence[FeatureEdit]) -> str | None:
    for edit in features:
        if edit.company:
            return edit.company
        for key, value in edit.attributes:
            if key.strip().lower() in {"исполнитель", "executor"} and value.strip():
                return value.strip()
    return None


def primary_photo(photos: Sequence[ZipPhoto]) -> ZipPhoto | None:
    by_slot = {}
    for photo in photos:
        by_slot.setdefault(photo.slot, photo)
    for slot in PRIMARY_PHOTO_SLOTS:
        if slot in by_slot:
            return by_slot[slot]
    return photos[0] if photos else None


def photo_uuid_for(archive_stem: str, zip_path: str) -> str:
    identity = f"field-restore|{archive_stem}|{zip_path}"
    return str(uuid.uuid5(PHOTO_NS, identity))


def parse_exported_at(raw: Any) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def ms_to_datetime(ms: int | None) -> datetime | None:
    if ms is None or ms <= 0:
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def taken_at_from_name(zip_path: str, fallback: datetime | None) -> datetime | None:
    name = Path(zip_path).name
    match = CAPTURE_RE.search(name)
    if not match:
        return fallback
    try:
        local = datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return fallback
    return local.replace(tzinfo=MOSCOW).astimezone(timezone.utc)


def format_duration(sec: int) -> str:
    hours, rem = divmod(max(0, int(sec)), 3600)
    mins, _ = divmod(rem, 60)
    if hours <= 0:
        return f"{mins} мин"
    if mins == 0:
        return f"{hours} ч"
    return f"{hours} ч {mins} мин"


def _zip_json(zf: zipfile.ZipFile, name: str, default: Any) -> Any:
    try:
        raw = zf.read(name)
    except KeyError:
        return default
    return json.loads(raw.decode("utf-8"))


def _attr_pairs(raw: Any) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    if not isinstance(raw, list):
        return ()
    for item in raw:
        if isinstance(item, list) and len(item) >= 2:
            pairs.append((str(item[0]), str(item[1])))
    return tuple(pairs)


def _parse_photos(raw: Any) -> tuple[ZipPhoto, ...]:
    photos: list[ZipPhoto] = []
    if not isinstance(raw, list):
        return ()
    for item in raw:
        if not isinstance(item, dict):
            continue
        zip_path = str(item.get("zipPath") or "").replace("\\", "/")
        if not zip_path:
            continue
        slot = str(item.get("slot") or item.get("kind") or "EVENT").upper()
        photos.append(
            ZipPhoto(
                slot=slot,
                zip_path=zip_path,
                device_path=str(item.get("devicePath") or "") or None,
            )
        )
    return tuple(photos)


def _parse_submission(raw: dict[str, Any]) -> DrawSubmission | None:
    sid = str(raw.get("id") or "").strip()
    points = raw.get("points") or []
    if not sid or not points:
        return None
    first = points[0]
    try:
        lat = float(first["lat"])
        lon = float(first["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    created = raw.get("createdAt")
    created_ms = int(created) if isinstance(created, (int, float)) else None
    event_type = raw.get("eventType")
    return DrawSubmission(
        id=sid,
        kind=str(raw.get("kind") or "EVENT_POINT"),
        event_type=str(event_type) if event_type else None,
        created_at_ms=created_ms,
        lat=lat,
        lon=lon,
        comment=str(raw["comment"]) if raw.get("comment") else None,
        photos=_parse_photos(raw.get("photos")),
        linked_feature_key=str(raw["linkedFeatureKey"]) if raw.get("linkedFeatureKey") else None,
    )


def _parse_feature(raw: dict[str, Any]) -> FeatureEdit:
    attrs = _attr_pairs(raw.get("attributes"))
    company = None
    for key, value in attrs:
        if key.strip().lower() in {"исполнитель", "executor"} and value.strip():
            company = value.strip()
            break
    status = raw.get("observationStatus")
    linked = raw.get("linkedTaskKey")
    return FeatureEdit(
        registry_key=str(raw.get("registryKey") or ""),
        observation_status=str(status) if status else None,
        linked_task_key=str(linked) if linked else None,
        company=company,
        attributes=attrs,
    )


def _parse_track(raw: dict[str, Any]) -> TrackSession | None:
    points_raw = raw.get("points") or []
    coords: list[tuple[float, float]] = []
    for point in points_raw:
        try:
            coords.append((float(point["lon"]), float(point["lat"])))
        except (KeyError, TypeError, ValueError):
            continue
    if len(coords) < 2:
        return None
    return TrackSession(
        task_key=str(raw.get("taskKey") or ""),
        started_at_ms=int(raw.get("startedAtMs") or 0),
        duration_sec=int(raw.get("durationSec") or 0),
        points=tuple(coords),
    )


def parse_zip(path: Path) -> FieldZipArchive:
    with zipfile.ZipFile(path) as zf:
        manifest = _zip_json(zf, "manifest.json", {})
        draws_raw = _zip_json(zf, "draw_submissions.json", [])
        features_raw = _zip_json(zf, "feature_edits.json", [])
        track_raw = _zip_json(zf, "track/session.json", None)

    if not isinstance(manifest, dict) or not manifest:
        raise ValueError(f"{path.name}: нет manifest.json FieldControl")

    submissions = tuple(
        item
        for item in (_parse_submission(raw) for raw in draws_raw or [])
        if item is not None
    )
    features = tuple(_parse_feature(raw) for raw in features_raw or [] if isinstance(raw, dict))
    track = _parse_track(track_raw) if isinstance(track_raw, dict) else None

    raw_task_key = str(manifest.get("taskKey") or "").strip()
    order_uuid = normalize_order_key(raw_task_key)
    if not order_uuid:
        raise ValueError(f"{path.name}: cannot parse taskKey={raw_task_key!r}")

    kind = "area" if raw_task_key.lower().startswith("area:") or (track and not submissions) else "field_order"
    if submissions:
        kind = "field_order"

    return FieldZipArchive(
        path=path.resolve(),
        kind=kind,
        raw_task_key=raw_task_key,
        order_uuid=order_uuid,
        order_number=str(manifest["orderNumber"]) if manifest.get("orderNumber") else None,
        rayon=str(manifest["rayon"]) if manifest.get("rayon") else None,
        exported_at=parse_exported_at(manifest.get("exportedAt")),
        submissions=submissions,
        features=features,
        track=track,
        stats=dict(manifest.get("stats") or {}),
    )


def discover_zips(dir_path: Path | None, explicit: Sequence[Path]) -> list[Path]:
    paths: list[Path] = []
    if dir_path is not None:
        paths.extend(sorted(dir_path.glob("*.zip")))
    for item in explicit:
        if item.is_dir():
            paths.extend(sorted(item.glob("*.zip")))
        else:
            paths.append(item)
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def is_junk_track(archive: FieldZipArchive) -> bool:
    if archive.track is None:
        return True
    if archive.order_uuid in SKIP_AREA_KEYS:
        return True
    if archive.track.duration_sec <= JUNK_TRACK_MAX_SEC:
        return True
    return archive.unique_track_points <= JUNK_TRACK_MAX_UNIQUE_POINTS


def should_skip_area_close(archive: FieldZipArchive, db_status: str | None) -> tuple[bool, str]:
    status = (db_status or "").strip().lower()
    if archive.order_uuid in SKIP_AREA_KEYS:
        return True, "explicit skip (office already processed / empty survey)"
    if status == "done":
        return True, "already done"
    if status not in AREA_CLOSE_STATUSES:
        return True, f"status {status or 'missing'} is not wip_field"
    if is_junk_track(archive):
        return True, "track looks empty"
    return False, ""
