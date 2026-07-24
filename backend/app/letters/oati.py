"""OATI letter draft and DOCX generation service."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import Json, RealDictCursor

from app.config import Settings, crm_task_store_config, get_settings
from app.crm.field_data_loader import fetch_field_report_rows
from app.crm.snapshot_loader import _lookup_feature_for_record
from app.crm.store import TaskRecord, _find_subgroup_for_record, fetch_task_by_key
from app.letters.docx_fill import (
    DEFAULT_VIOLATION,
    append_map_page,
    append_photo_pages,
    document_to_bytes,
    fill_letter_template,
    format_ru_date,
    format_ru_datetime,
    format_wgs84,
)
from app.letters.geocode import reverse_geocode_parts
from app.letters.map_image import classify_geometry_visibility, render_situational_map
from app.photos.field_photo import fetch_field_photos, read_field_photo
from app.photos.sftp_fetch import SftpPhotoError

logger = logging.getLogger(__name__)
MSK = ZoneInfo("Europe/Moscow")

# Same fields as UI «Источник» labels «Исполнитель» in taskTableColumnsForSubgroup.
SOURCE_EXECUTOR_FIELDS = ("general_contractor", "executor", "lead_of_work")


class LetterError(Exception):
    """Domain error for letter generation."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class LetterPhotoDraft:
    id: int
    file_path: str
    banner: bool
    created_at: str | None
    label: str | None
    image_url: str


@dataclass
class LetterDraft:
    task_key: str
    report_id: int
    rayon: str
    street: str
    today: str
    coordinates: str
    lon: float
    lat: float
    incident_datetime: str
    executor: str
    address: str
    engineering: str
    description: str
    violation: str
    photos: list[LetterPhotoDraft] = field(default_factory=list)
    map_warning: str | None = None
    task_geometry_visibility: str = "missing"
    address_auto: bool = False
    address_has_house: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_key": self.task_key,
            "report_id": self.report_id,
            "rayon": self.rayon,
            "street": self.street,
            "today": self.today,
            "coordinates": self.coordinates,
            "lon": self.lon,
            "lat": self.lat,
            "incident_datetime": self.incident_datetime,
            "executor": self.executor,
            "address": self.address,
            "engineering": self.engineering,
            "description": self.description,
            "violation": self.violation,
            "photos": [
                {
                    "id": p.id,
                    "file_path": p.file_path,
                    "banner": p.banner,
                    "created_at": p.created_at,
                    "label": p.label,
                    "image_url": p.image_url,
                }
                for p in self.photos
            ],
            "map_warning": self.map_warning,
            "task_geometry_visibility": self.task_geometry_visibility,
            "address_auto": self.address_auto,
            "address_has_house": self.address_has_house,
        }


def _geometry_centroid_lonlat(geometry: dict[str, Any]) -> tuple[float, float]:
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Point" and isinstance(coords, (list, tuple)) and len(coords) >= 2:
        return float(coords[0]), float(coords[1])

    points: list[tuple[float, float]] = []

    def walk(node: Any, depth: int) -> None:
        if not isinstance(node, (list, tuple)) or not node:
            return
        if depth == 0 and len(node) >= 2 and isinstance(node[0], (int, float)):
            points.append((float(node[0]), float(node[1])))
            return
        for child in node:
            walk(child, depth - 1)

    depth = {
        "MultiPoint": 1,
        "LineString": 1,
        "MultiLineString": 2,
        "Polygon": 2,
        "MultiPolygon": 3,
    }.get(gtype or "", 1)
    walk(coords, depth)
    if not points:
        raise LetterError("Не удалось определить координаты объекта reports", status_code=400)
    lon = sum(p[0] for p in points) / len(points)
    lat = sum(p[1] for p in points) / len(points)
    return lon, lat


def _lookup_rayon(conn: PgConnection, lon: float, lat: float) -> str:
    query = """
        SELECT rayon::text AS rayon
        FROM odh_export.hood
        WHERE geom IS NOT NULL
          AND ST_Contains(
              ST_Transform(geom, 4326),
              ST_SetSRID(ST_MakePoint(%s, %s), 4326)
          )
        ORDER BY gid
        LIMIT 1
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (lon, lat))
        row = cur.fetchone()
    if not row or not row.get("rayon"):
        return ""
    return " ".join(str(row["rayon"]).split()).strip()


def _attr_text(attrs: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = attrs.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    lower_map = {str(k).lower(): v for k, v in attrs.items()}
    for key in keys:
        value = lower_map.get(key.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _lookup_source_feature(
    conn: PgConnection,
    record: TaskRecord,
    store_cfg: dict[str, Any],
) -> dict[str, Any] | None:
    resolved = _find_subgroup_for_record(record, store_cfg)
    if resolved is None:
        return None
    subgroup_name, _, _ = resolved
    return _lookup_feature_for_record(conn, record, subgroup_name, store_cfg)


def _lookup_field_assignee(conn: PgConnection, task_key: str) -> str:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT executor
            FROM crm.tasks_field
            WHERE task_key = %s::uuid
            ORDER BY sent_at DESC NULLS LAST, key DESC
            LIMIT 1
            """,
            (task_key,),
        )
        row = cur.fetchone()
    if not row:
        return ""
    value = row.get("executor")
    return str(value).strip() if value is not None and str(value).strip() else ""


def _lookup_executor(
    conn: PgConnection,
    record: TaskRecord,
    store_cfg: dict[str, Any],
) -> str:
    """Producer of works from source object «Исполнитель», then field assignee."""
    feature = _lookup_source_feature(conn, record, store_cfg)
    if feature:
        attrs = feature.get("attributes") or {}
        if isinstance(attrs, dict):
            from_source = _attr_text(attrs, *SOURCE_EXECUTOR_FIELDS)
            if from_source:
                return from_source
    return _lookup_field_assignee(conn, record.key)


def _lookup_engineering(conn: PgConnection, record: TaskRecord, store_cfg: dict[str, Any]) -> str:
    """Only engineering_net_obj from source feature — never TaskRecord.type."""
    feature = _lookup_source_feature(conn, record, store_cfg)
    if not feature:
        return ""
    attrs = feature.get("attributes") or {}
    if not isinstance(attrs, dict):
        return ""
    return _attr_text(attrs, "engineering_net_obj", "engineering_net", "eng_net_obj")


def _lookup_task_geometry(
    conn: PgConnection,
    record: TaskRecord,
    store_cfg: dict[str, Any],
) -> dict[str, Any] | None:
    feature = _lookup_source_feature(conn, record, store_cfg)
    if not feature:
        return None
    geometry = feature.get("geometry")
    if isinstance(geometry, str):
        try:
            geometry = json.loads(geometry)
        except json.JSONDecodeError:
            return None
    return geometry if isinstance(geometry, dict) else None


def _load_report_geometry(
    conn: PgConnection,
    task_key: str,
    report_id: int,
    store_cfg: dict[str, Any],
) -> dict[str, Any]:
    rows = fetch_field_report_rows(conn, task_key, store_cfg)
    for row in rows:
        rid = row.get("id")
        if rid is None or int(rid) != int(report_id):
            continue
        geometry = row.get("_geometry")
        if isinstance(geometry, str):
            geometry = json.loads(geometry)
        if not isinstance(geometry, dict):
            raise LetterError("У выбранного отчёта отсутствует геометрия", status_code=400)
        return geometry
    raise LetterError("Отчёт не найден или не связан с задачей", status_code=404)


def _map_warning_for_visibility(visibility: str) -> str | None:
    if visibility == "partial":
        return (
            "Объект задачи частично выходит за рамку ситуационного плана 1:1000; "
            "на карте будет показана только попадающая часть."
        )
    if visibility == "outside":
        return (
            "Объект задачи не помещается в рамку ситуационного плана 1:1000 "
            "(центр — объект reports); на карте будет виден только маркер reports."
        )
    if visibility == "missing":
        return "Геометрия объекта задачи не найдена; на карте будет только объект reports."
    return None


def build_letter_draft(
    conn: PgConnection,
    task_key: str,
    report_id: int,
    *,
    settings: Settings | None = None,
) -> LetterDraft:
    settings = settings or get_settings()
    store_cfg = crm_task_store_config()

    record = fetch_task_by_key(conn, store_cfg, task_key)
    if record is None:
        raise LetterError("Задача не найдена", status_code=404)

    report_geometry = _load_report_geometry(conn, task_key, report_id, store_cfg)
    lon, lat = _geometry_centroid_lonlat(report_geometry)

    photos_result = fetch_field_photos(conn, task_key, report_id=report_id)
    photos: list[LetterPhotoDraft] = []
    for photo in photos_result.photos:
        name = Path(photo.file_path).name
        photos.append(
            LetterPhotoDraft(
                id=photo.id,
                file_path=photo.file_path,
                banner=photo.banner,
                created_at=photo.created_at,
                label="Фото баннера" if photo.banner else None,
                image_url=f"/api/photos/field/{quote(name)}/image",
            )
        )

    incident_dt = ""
    for photo in photos_result.photos:
        if photo.created_at:
            incident_dt = format_ru_datetime(photo.created_at)
            break

    task_geometry = _lookup_task_geometry(conn, record, store_cfg)
    visibility = classify_geometry_visibility(task_geometry, lon, lat)

    geo = reverse_geocode_parts(lon, lat, settings)
    description = (photos_result.comment or "").strip()

    return LetterDraft(
        task_key=task_key,
        report_id=report_id,
        rayon=_lookup_rayon(conn, lon, lat),
        street=geo.street,
        today=format_ru_date(),
        coordinates=format_wgs84(lon, lat),
        lon=lon,
        lat=lat,
        incident_datetime=incident_dt,
        executor=_lookup_executor(conn, record, store_cfg),
        address=geo.address,
        engineering=_lookup_engineering(conn, record, store_cfg),
        description=description,
        violation=DEFAULT_VIOLATION,
        photos=photos,
        map_warning=_map_warning_for_visibility(visibility),
        task_geometry_visibility=visibility,
        address_auto=bool(geo.address),
        address_has_house=geo.has_house,
    )


def _validate_photo_ids(
    conn: PgConnection,
    task_key: str,
    report_id: int,
    photo_ids: list[int],
) -> list[int]:
    if not photo_ids:
        return []
    available = {p.id for p in fetch_field_photos(conn, task_key, report_id=report_id).photos}
    missing = [pid for pid in photo_ids if pid not in available]
    if missing:
        raise LetterError(
            f"Выбранные фото не принадлежат отчёту: {', '.join(str(x) for x in missing)}",
            status_code=400,
        )
    seen: set[int] = set()
    ordered: list[int] = []
    for pid in photo_ids:
        if pid not in seen:
            seen.add(pid)
            ordered.append(pid)
    return ordered


def _insert_letter_row(
    conn: PgConnection,
    *,
    task_key: str,
    report_id: int,
    created_by: str,
    payload: dict[str, Any],
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO webcrm.oati_letters (task_key, report_id, created_by, payload)
            VALUES (%s::uuid, %s, %s, %s)
            RETURNING fid
            """,
            (task_key, report_id, created_by, Json(payload)),
        )
        row = cur.fetchone()
    conn.commit()
    if not row:
        raise LetterError("Не удалось сохранить запись письма", status_code=500)
    return int(row[0])


def _read_photo_bytes(file_path: str, settings: Settings) -> bytes | None:
    name = Path(file_path).name
    try:
        path, _media = read_field_photo(name, settings)
        return path.read_bytes()
    except (SftpPhotoError, OSError) as exc:
        logger.warning("Cannot read field photo %s: %s", name, exc)
        return None


def generate_letter_docx(
    conn: PgConnection,
    *,
    task_key: str,
    report_id: int,
    created_by: str,
    executor: str,
    address: str,
    engineering: str,
    description: str,
    violation: str,
    photo_ids: list[int],
    settings: Settings | None = None,
) -> tuple[int, bytes, str]:
    """Create letter row, build DOCX, return (fid, bytes, filename)."""
    settings = settings or get_settings()
    store_cfg = crm_task_store_config()

    record = fetch_task_by_key(conn, store_cfg, task_key)
    if record is None:
        raise LetterError("Задача не найдена", status_code=404)

    report_geometry = _load_report_geometry(conn, task_key, report_id, store_cfg)
    lon, lat = _geometry_centroid_lonlat(report_geometry)
    ordered_ids = _validate_photo_ids(conn, task_key, report_id, photo_ids)

    photos_result = fetch_field_photos(conn, task_key, report_id=report_id)
    photos_by_id = {p.id: p for p in photos_result.photos}

    incident_dt = ""
    for pid in ordered_ids:
        photo = photos_by_id.get(pid)
        if photo and photo.created_at:
            incident_dt = format_ru_datetime(photo.created_at)
            break
    if not incident_dt:
        for photo in photos_result.photos:
            if photo.created_at:
                incident_dt = format_ru_datetime(photo.created_at)
                break

    geo = reverse_geocode_parts(lon, lat, settings)
    street = geo.street
    if address and "," in address:
        street = address.split(",", 1)[0].strip() or street
    elif address and not street:
        street = address.strip()

    today = format_ru_date()
    coordinates = format_wgs84(lon, lat)
    violation_text = (violation or "").strip() or DEFAULT_VIOLATION

    payload = {
        "executor": executor,
        "address": address,
        "engineering": engineering,
        "description": description,
        "violation": violation_text,
        "photo_ids": ordered_ids,
        "street": street,
        "rayon": _lookup_rayon(conn, lon, lat),
        "coordinates": coordinates,
        "incident_datetime": incident_dt,
        "today": today,
    }
    fid = _insert_letter_row(
        conn,
        task_key=task_key,
        report_id=report_id,
        created_by=created_by,
        payload=payload,
    )

    document = fill_letter_template(
        street=street or "__________",
        today=today,
        fid=fid,
        executor=(executor or "").strip(),
        incident_datetime=incident_dt,
        address=(address or "").strip(),
        coordinates=coordinates,
        engineering=(engineering or "").strip(),
        description=(description or "").strip(),
        violation=violation_text,
    )

    task_geometry = _lookup_task_geometry(conn, record, store_cfg)
    try:
        map_png = render_situational_map(lon, lat, task_geometry, settings)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Map render failed, using blank canvas fallback: %s", exc)
        from PIL import Image
        import io as _io

        img = Image.new("RGB", (800, 800), color=(240, 240, 240))
        buf = _io.BytesIO()
        img.save(buf, format="PNG")
        map_png = buf.getvalue()

    append_map_page(document, map_png)

    photo_payloads: list[tuple[bytes, str]] = []
    for index, pid in enumerate(ordered_ids, start=1):
        photo = photos_by_id.get(pid)
        if not photo:
            continue
        raw = _read_photo_bytes(photo.file_path, settings)
        if raw is None:
            continue
        label_parts = [f"Фото {index}"]
        if photo.banner:
            label_parts.append("баннер")
        if photo.created_at:
            label_parts.append(format_ru_datetime(photo.created_at))
        photo_payloads.append((raw, " · ".join(label_parts)))

    append_photo_pages(document, photo_payloads)

    filename = f"Письмо_ОАТИ_{fid}.docx"
    return fid, document_to_bytes(document), filename
