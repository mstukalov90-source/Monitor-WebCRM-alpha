"""Parse GeoPackage polygons and insert them into crm.tasks_area."""

from __future__ import annotations

import sqlite3
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.crm.tasks_area import AREA_STATUSES

SQLITE_MAGIC = b"SQLite format 3"
GPKG_MAGIC = b"GP"
MSK77_SRID = 980077
WGS84_SRID = 4326
ALLOWED_SRIDS = frozenset({WGS84_SRID, MSK77_SRID})
POLYGON_TYPES = frozenset(
    {
        "POLYGON",
        "MULTIPOLYGON",
        "GEOMETRY",
        "GEOMETRYCOLLECTION",
    }
)
ATTR_KEYS = ("fid", "gid", "rayon", "okrug", "okrug_shor", "status")
STATEMENT_TIMEOUT = "120s"
MAX_FEATURES_DEFAULT = 5000

_ENVELOPE_BYTES = {
    0: 0,
    1: 32,
    2: 48,
    3: 48,
    4: 64,
}


class GpkgAreaImportError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ParsedGpkgFeature:
    fid: int | None
    gid: int | None
    rayon: str | None
    okrug: str | None
    okrug_shor: str | None
    status: str
    wkb: bytes


@dataclass(frozen=True)
class ParsedGpkg:
    layer: str
    srid: int
    features: list[ParsedGpkgFeature]
    skipped: int


@dataclass(frozen=True)
class ImportedAreaItem:
    key: str
    status: str | None
    task_number: str | None
    area: float | None
    rayon: str | None
    okrug_shor: str | None


@dataclass(frozen=True)
class GpkgAreaImportResult:
    inserted: int
    skipped: int
    layer: str
    srid: int
    items: list[ImportedAreaItem]


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_status(value: Any) -> str:
    text = (_as_text(value) or "free").lower()
    if text not in AREA_STATUSES:
        return "free"
    return text


def gpkg_binary_to_wkb(blob: bytes) -> bytes | None:
    """Strip GeoPackageBinary header; return WKB or None if empty/invalid."""
    if not blob or len(blob) < 8:
        return None
    if blob[:2] != GPKG_MAGIC:
        return None
    flags = blob[3]
    empty = bool(flags & 0x10)
    if empty:
        return None
    little = bool(flags & 0x01)
    envelope_code = (flags >> 1) & 0x07
    envelope_len = _ENVELOPE_BYTES.get(envelope_code)
    if envelope_len is None:
        return None
    header_len = 8 + envelope_len
    if len(blob) <= header_len:
        return None
    endian = "<" if little else ">"
    try:
        struct.unpack_from(endian + "i", blob, 4)
    except struct.error:
        return None
    wkb = blob[header_len:]
    return wkb or None


def _resolve_srid(srs_id: int | None, organization: str | None, org_cs_id: int | None, srs_name: str | None) -> int:
    org = (organization or "").strip().upper()
    name = (srs_name or "").upper()
    org_cs = org_cs_id if org_cs_id is not None else -1
    sid = srs_id if srs_id is not None else -1

    if sid == WGS84_SRID or (org == "EPSG" and org_cs == WGS84_SRID):
        return WGS84_SRID
    if sid == MSK77_SRID or org_cs == MSK77_SRID:
        return MSK77_SRID
    if "MSK-77" in name or "МСК-77" in (srs_name or "").upper() or "MSK77" in name.replace("-", ""):
        return MSK77_SRID
    if "МСК" in (srs_name or "") and "77" in (srs_name or ""):
        return MSK77_SRID
    raise GpkgAreaImportError(
        f"Неподдерживаемый CRS слоя (srs_id={srs_id}, {organization}:{org_cs_id}). "
        "Допустимы EPSG:4326 и МСК-77 (980077)."
    )


def _layer_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT
                gc.table_name AS table_name,
                gc.column_name AS column_name,
                gc.geometry_type_name AS geometry_type_name,
                gc.srs_id AS srs_id,
                srs.organization AS organization,
                srs.organization_coordsys_id AS organization_coordsys_id,
                srs.srs_name AS srs_name
            FROM gpkg_geometry_columns gc
            LEFT JOIN gpkg_spatial_ref_sys srs ON srs.srs_id = gc.srs_id
            """
        )
        return list(cur.fetchall())
    except sqlite3.Error as exc:
        raise GpkgAreaImportError(f"Файл не похож на GeoPackage: {exc}") from exc


def _column_map(names: Iterable[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for name in names:
        mapping[name.lower()] = name
    return mapping


def _open_sqlite_gpkg(content: bytes) -> tuple[sqlite3.Connection, str]:
    tmp = tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False)
    tmp.write(content)
    tmp.close()
    try:
        return sqlite3.connect(tmp.name), tmp.name
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        raise


def _read_layer_features(
    conn: sqlite3.Connection,
    table_name: str,
    geom_column: str,
    remaining: int,
    *,
    max_features: int,
) -> tuple[list[ParsedGpkgFeature], int]:
    quoted_table = _quote_ident(table_name)
    try:
        info = conn.execute(f"PRAGMA table_info({quoted_table})").fetchall()
    except sqlite3.Error as exc:
        raise GpkgAreaImportError(f"Не удалось прочитать слой {table_name}: {exc}") from exc

    col_names = [str(row["name"] if isinstance(row, sqlite3.Row) else row[1]) for row in info]
    cmap = _column_map(col_names)
    geom_actual = cmap.get(geom_column.lower())
    if geom_actual is None:
        raise GpkgAreaImportError(f"В слое {table_name} нет колонки геометрии {geom_column}")

    select_cols = [_quote_ident(geom_actual)]
    wanted: dict[str, str] = {}
    for key in ATTR_KEYS:
        actual = cmap.get(key)
        if actual and actual != geom_actual:
            wanted[key] = actual
            select_cols.append(_quote_ident(actual))

    sql = f"SELECT {', '.join(select_cols)} FROM {quoted_table}"
    try:
        rows = conn.execute(sql).fetchall()
    except sqlite3.Error as exc:
        raise GpkgAreaImportError(f"Не удалось прочитать объекты слоя {table_name}: {exc}") from exc

    features: list[ParsedGpkgFeature] = []
    skipped = 0
    for row in rows:
        if isinstance(row, sqlite3.Row):
            values = {k.lower(): row[k] for k in row.keys()}
        else:
            keys = [geom_actual] + [wanted[k] for k in ATTR_KEYS if k in wanted]
            values = {k.lower(): v for k, v in zip(keys, row)}

        blob = values.get(geom_actual.lower())
        wkb = gpkg_binary_to_wkb(blob) if isinstance(blob, (bytes, memoryview, bytearray)) else None
        if wkb is None:
            skipped += 1
            continue
        if remaining <= 0:
            raise GpkgAreaImportError(
                f"Слишком много полигонов в файле (больше {max_features})"
            )
        features.append(
            ParsedGpkgFeature(
                fid=_as_int(values.get("fid")),
                gid=_as_int(values.get("gid")),
                rayon=_as_text(values.get("rayon")),
                okrug=_as_text(values.get("okrug")),
                okrug_shor=_as_text(values.get("okrug_shor")),
                status=_normalize_status(values.get("status")),
                wkb=bytes(wkb),
            )
        )
        remaining -= 1
    return features, skipped


def parse_gpkg_bytes(content: bytes, *, max_features: int = MAX_FEATURES_DEFAULT) -> ParsedGpkg:
    if not content:
        raise GpkgAreaImportError("Файл пустой")
    if not content.startswith(SQLITE_MAGIC):
        raise GpkgAreaImportError("Файл не похож на GeoPackage (ожидается SQLite)")

    conn, tmp_path = _open_sqlite_gpkg(content)
    try:
        layers = _layer_rows(conn)
        polygon_layers = [
            row
            for row in layers
            if str(row["geometry_type_name"] or "").upper() in POLYGON_TYPES
        ]
        if not polygon_layers:
            raise GpkgAreaImportError("В GeoPackage нет полигональных слоёв")

        srids: list[int] = []
        all_features: list[ParsedGpkgFeature] = []
        skipped = 0
        names: list[str] = []
        remaining = max_features
        for row in polygon_layers:
            srid = _resolve_srid(
                _as_int(row["srs_id"]),
                _as_text(row["organization"]),
                _as_int(row["organization_coordsys_id"]),
                _as_text(row["srs_name"]),
            )
            srids.append(srid)
            feats, skip = _read_layer_features(
                conn,
                str(row["table_name"]),
                str(row["column_name"]),
                remaining,
                max_features=max_features,
            )
            all_features.extend(feats)
            skipped += skip
            remaining = max_features - len(all_features)
            names.append(str(row["table_name"]))

        unique_srids = set(srids)
        if len(unique_srids) != 1:
            raise GpkgAreaImportError("В файле полигональные слои с разным CRS")
        if not all_features:
            raise GpkgAreaImportError("Нет полигонов для загрузки (пустая или битая геометрия)")
        return ParsedGpkg(
            layer=", ".join(names),
            srid=next(iter(unique_srids)),
            features=all_features,
            skipped=skipped,
        )
    finally:
        conn.close()
        Path(tmp_path).unlink(missing_ok=True)


def _geom_sql(srid: int) -> str:
    if srid == MSK77_SRID:
        inner = f"ST_Transform(ST_SetSRID(ST_GeomFromWKB(%s), {MSK77_SRID}), {WGS84_SRID})"
    else:
        inner = f"ST_SetSRID(ST_GeomFromWKB(%s), {WGS84_SRID})"
    return f"ST_Multi(ST_CollectionExtract(ST_MakeValid({inner}), 3))"


def import_parsed_gpkg(conn: PgConnection, parsed: ParsedGpkg) -> GpkgAreaImportResult:
    geom_expr = _geom_sql(parsed.srid)
    insert_sql = f"""
        INSERT INTO crm.tasks_area (
            key, fid, gid, rayon, okrug, okrug_shor, geom, status
        )
        SELECT
            gen_random_uuid(),
            s.fid,
            s.gid,
            crm.normalize_attr_text(s.rayon),
            crm.normalize_attr_text(s.okrug),
            crm.normalize_attr_text(s.okrug_shor),
            s.geom,
            s.status
        FROM (
            SELECT
                %s::bigint AS fid,
                %s::bigint AS gid,
                %s::text AS rayon,
                %s::text AS okrug,
                %s::text AS okrug_shor,
                {geom_expr} AS geom,
                COALESCE(NULLIF(btrim(%s), ''), 'free') AS status
        ) s
        WHERE s.geom IS NOT NULL AND NOT ST_IsEmpty(s.geom)
        RETURNING key
    """

    keys: list[str] = []
    skipped = parsed.skipped
    try:
        with conn.cursor() as cur:
            cur.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
            for feat in parsed.features:
                cur.execute(
                    insert_sql,
                    (
                        feat.fid,
                        feat.gid,
                        feat.rayon,
                        feat.okrug,
                        feat.okrug_shor,
                        feat.wkb,
                        feat.status,
                    ),
                )
                row = cur.fetchone()
                if row:
                    keys.append(str(row[0]))
                else:
                    skipped += 1

            if not keys:
                raise GpkgAreaImportError("Нет полигонов для загрузки (пустая или битая геометрия)")

            cur.execute("UPDATE crm.tasks_area SET status = 'free' WHERE status IS NULL")
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtext('crm.refresh_tasks_area_quarterly'))"
            )
            cur.execute("CALL crm.refresh_tasks_area_quarterly()")
            # Docs mention crm.refresh_task_area_keys(); it is not on this MONITOR DB.
            cur.execute(
                """
                SELECT 1
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'crm' AND p.proname = 'refresh_task_area_keys'
                LIMIT 1
                """
            )
            if cur.fetchone():
                cur.execute("CALL crm.refresh_task_area_keys()")

        items = _fetch_inserted(conn, keys)
        conn.commit()
    except GpkgAreaImportError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise

    return GpkgAreaImportResult(
        inserted=len(keys),
        skipped=skipped,
        layer=parsed.layer,
        srid=parsed.srid,
        items=items,
    )


def _fetch_inserted(conn: PgConnection, keys: list[str]) -> list[ImportedAreaItem]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT key, status, task_number, area, rayon, okrug_shor
            FROM crm.tasks_area
            WHERE key = ANY(%s::uuid[])
            ORDER BY task_number NULLS LAST, key
            """,
            (keys,),
        )
        rows = cur.fetchall()
    items: list[ImportedAreaItem] = []
    for row in rows:
        area = row.get("area")
        items.append(
            ImportedAreaItem(
                key=str(row["key"]),
                status=row.get("status"),
                task_number=row.get("task_number"),
                area=float(area) if area is not None else None,
                rayon=row.get("rayon"),
                okrug_shor=row.get("okrug_shor"),
            )
        )
    return items


def import_gpkg_bytes(
    conn: PgConnection,
    content: bytes,
    *,
    max_features: int = MAX_FEATURES_DEFAULT,
) -> GpkgAreaImportResult:
    parsed = parse_gpkg_bytes(content, max_features=max_features)
    return import_parsed_gpkg(conn, parsed)


def result_to_dict(result: GpkgAreaImportResult) -> dict[str, Any]:
    return {
        "inserted": result.inserted,
        "skipped": result.skipped,
        "layer": result.layer,
        "srid": result.srid,
        "items": [
            {
                "key": item.key,
                "status": item.status,
                "task_number": item.task_number,
                "area": item.area,
                "rayon": item.rayon,
                "okrug_shor": item.okrug_shor,
            }
            for item in result.items
        ],
    }


def validate_filename(filename: str | None) -> None:
    suffix = Path((filename or "").replace("\\", "/")).name.lower()
    if not suffix.endswith(".gpkg"):
        raise GpkgAreaImportError("Допустим только файл .gpkg")
