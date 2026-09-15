"""Tests for admin GeoPackage import into crm.tasks_area."""

from __future__ import annotations

import sqlite3
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import HTTPException

from app.auth.deps import require_admin
from app.auth.session import UserSession
from app.crm.gpkg_area_import import (
    GpkgAreaImportError,
    ParsedGpkg,
    ParsedGpkgFeature,
    gpkg_binary_to_wkb,
    import_parsed_gpkg,
    parse_gpkg_bytes,
    validate_filename,
)


def _session(role: str, login: str = "admin") -> UserSession:
    return UserSession(
        uuid="11111111-2222-3333-4444-555555555555",
        login=login,
        role=role,
        work_zones=[],
    )


def _wkb_polygon(coords: list[tuple[float, float]]) -> bytes:
    buf = bytearray()
    buf.append(1)
    buf.extend(struct.pack("<I", 3))
    buf.extend(struct.pack("<I", 1))
    buf.extend(struct.pack("<I", len(coords)))
    for x, y in coords:
        buf.extend(struct.pack("<dd", x, y))
    return bytes(buf)


def _gpb(wkb: bytes | None, *, srs_id: int = 4326, empty: bool = False) -> bytes:
    flags = 0x01
    if empty:
        flags |= 0x10
    header = b"GP" + bytes([0, flags]) + struct.pack("<i", srs_id)
    return header + (b"" if empty or wkb is None else wkb)


SQUARE = [
    (37.60, 55.75),
    (37.61, 55.75),
    (37.61, 55.76),
    (37.60, 55.76),
    (37.60, 55.75),
]


def _build_gpkg(
    *,
    srs_id: int = 4326,
    organization: str = "EPSG",
    org_cs: int | None = None,
    srs_name: str = "WGS 84",
    geom_type: str = "POLYGON",
    rows: list[dict] | None = None,
) -> bytes:
    if org_cs is None:
        org_cs = srs_id
    if rows is None:
        rows = [
            {
                "geom": _gpb(_wkb_polygon(SQUARE), srs_id=srs_id),
                "gid": 98,
                "rayon": "Кузьминки",
                "okrug": "Юго-Восточный",
                "okrug_shor": "ЮВАО",
                "status": "free",
            }
        ]
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(
            """
            CREATE TABLE gpkg_spatial_ref_sys (
              srs_name TEXT NOT NULL,
              srs_id INTEGER NOT NULL PRIMARY KEY,
              organization TEXT NOT NULL,
              organization_coordsys_id INTEGER NOT NULL,
              definition TEXT NOT NULL,
              description TEXT
            );
            CREATE TABLE gpkg_contents (
              table_name TEXT NOT NULL PRIMARY KEY,
              data_type TEXT NOT NULL,
              identifier TEXT,
              description TEXT,
              last_change DATETIME NOT NULL DEFAULT '',
              min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE,
              srs_id INTEGER
            );
            CREATE TABLE gpkg_geometry_columns (
              table_name TEXT NOT NULL,
              column_name TEXT NOT NULL,
              geometry_type_name TEXT NOT NULL,
              srs_id INTEGER NOT NULL,
              z TINYINT NOT NULL,
              m TINYINT NOT NULL,
              PRIMARY KEY (table_name, column_name)
            );
            CREATE TABLE orders (
              fid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
              geom BLOB,
              gid INTEGER,
              rayon TEXT,
              okrug TEXT,
              okrug_shor TEXT,
              status TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO gpkg_spatial_ref_sys
            (srs_name, srs_id, organization, organization_coordsys_id, definition, description)
            VALUES (?, ?, ?, ?, 'def', NULL)
            """,
            (srs_name, srs_id, organization, org_cs),
        )
        conn.execute(
            "INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('orders', 'features', ?)",
            (srs_id,),
        )
        conn.execute(
            """
            INSERT INTO gpkg_geometry_columns
            (table_name, column_name, geometry_type_name, srs_id, z, m)
            VALUES ('orders', 'geom', ?, ?, 0, 0)
            """,
            (geom_type, srs_id),
        )
        for row in rows:
            conn.execute(
                """
                INSERT INTO orders (geom, gid, rayon, okrug, okrug_shor, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("geom"),
                    row.get("gid"),
                    row.get("rayon"),
                    row.get("okrug"),
                    row.get("okrug_shor"),
                    row.get("status"),
                ),
            )
        conn.commit()
        tmp = tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False)
        try:
            disk = sqlite3.connect(tmp.name)
            try:
                conn.backup(disk)
            finally:
                disk.close()
            tmp.close()
            return Path(tmp.name).read_bytes()
        finally:
            Path(tmp.name).unlink(missing_ok=True)
    finally:
        conn.close()


class GpkgBinaryTests(unittest.TestCase):
    def test_strips_header(self) -> None:
        wkb = _wkb_polygon(SQUARE)
        self.assertEqual(gpkg_binary_to_wkb(_gpb(wkb)), wkb)

    def test_empty_flag_returns_none(self) -> None:
        self.assertIsNone(gpkg_binary_to_wkb(_gpb(None, empty=True)))

    def test_short_blob_returns_none(self) -> None:
        self.assertIsNone(gpkg_binary_to_wkb(b"GP"))


class ParseGpkgTests(unittest.TestCase):
    def test_parses_polygon_attributes(self) -> None:
        parsed = parse_gpkg_bytes(_build_gpkg())
        self.assertEqual(parsed.layer, "orders")
        self.assertEqual(parsed.srid, 4326)
        self.assertEqual(parsed.skipped, 0)
        self.assertEqual(len(parsed.features), 1)
        feat = parsed.features[0]
        self.assertEqual(feat.gid, 98)
        self.assertEqual(feat.rayon, "Кузьминки")
        self.assertEqual(feat.okrug_shor, "ЮВАО")
        self.assertEqual(feat.status, "free")
        self.assertTrue(feat.wkb.startswith(b"\x01"))

    def test_skips_empty_and_null_geom(self) -> None:
        rows = [
            {
                "geom": _gpb(_wkb_polygon(SQUARE)),
                "gid": 1,
                "rayon": "Кузьминки",
                "okrug": "ЮВАО",
                "okrug_shor": "ЮВАО",
                "status": "free",
            },
            {
                "geom": None,
                "gid": 2,
                "rayon": "Кузьминки",
                "okrug": "ЮВАО",
                "okrug_shor": "ЮВАО",
                "status": "free",
            },
            {
                "geom": _gpb(None, empty=True),
                "gid": 3,
                "rayon": "Кузьминки",
                "okrug": "ЮВАО",
                "okrug_shor": "ЮВАО",
                "status": "free",
            },
        ]
        parsed = parse_gpkg_bytes(_build_gpkg(rows=rows))
        self.assertEqual(len(parsed.features), 1)
        self.assertEqual(parsed.skipped, 2)
        self.assertEqual(parsed.features[0].gid, 1)

    def test_rejects_unsupported_crs(self) -> None:
        with self.assertRaises(GpkgAreaImportError) as ctx:
            parse_gpkg_bytes(_build_gpkg(srs_id=3857, srs_name="Web Mercator"))
        self.assertIn("CRS", str(ctx.exception))

    def test_accepts_msk77_srid(self) -> None:
        parsed = parse_gpkg_bytes(
            _build_gpkg(srs_id=980077, organization="NONE", org_cs=980077, srs_name="MSK-77")
        )
        self.assertEqual(parsed.srid, 980077)

    def test_rejects_point_layer(self) -> None:
        with self.assertRaises(GpkgAreaImportError) as ctx:
            parse_gpkg_bytes(_build_gpkg(geom_type="POINT"))
        self.assertIn("полигональных", str(ctx.exception))

    def test_rejects_non_sqlite(self) -> None:
        with self.assertRaises(GpkgAreaImportError):
            parse_gpkg_bytes(b"not-a-sqlite")

    def test_rejects_all_empty(self) -> None:
        rows = [{"geom": None, "gid": 1, "rayon": "A", "okrug": "B", "okrug_shor": "C", "status": "free"}]
        with self.assertRaises(GpkgAreaImportError) as ctx:
            parse_gpkg_bytes(_build_gpkg(rows=rows))
        self.assertIn("Нет полигонов", str(ctx.exception))

    def test_invalid_status_becomes_free(self) -> None:
        rows = [
            {
                "geom": _gpb(_wkb_polygon(SQUARE)),
                "gid": 1,
                "rayon": "Кузьминки",
                "okrug": "ЮВАО",
                "okrug_shor": "ЮВАО",
                "status": "unknown",
            }
        ]
        parsed = parse_gpkg_bytes(_build_gpkg(rows=rows))
        self.assertEqual(parsed.features[0].status, "free")


class ValidateFilenameTests(unittest.TestCase):
    def test_accepts_gpkg(self) -> None:
        validate_filename("orders.gpkg")

    def test_rejects_other(self) -> None:
        with self.assertRaises(GpkgAreaImportError):
            validate_filename("orders.zip")


class ImportParsedGpkgTests(unittest.TestCase):
    def test_inserts_lock_and_refresh(self) -> None:
        parsed = ParsedGpkg(
            layer="orders",
            srid=4326,
            skipped=1,
            features=[
                ParsedGpkgFeature(
                    fid=1,
                    gid=98,
                    rayon="Кузьминки",
                    okrug="ЮВАО",
                    okrug_shor="ЮВАО",
                    status="free",
                    wkb=_wkb_polygon(SQUARE),
                )
            ],
        )
        write_cur = MagicMock()
        write_cur.fetchone.side_effect = [
            ("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",),
            None,
        ]
        write_cm = MagicMock()
        write_cm.__enter__.return_value = write_cur
        write_cm.__exit__.return_value = False

        read_cur = MagicMock()
        read_cur.fetchall.return_value = [
            {
                "key": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "status": "free",
                "task_number": "М/ЮВАО-26-3/Кузьминки-1",
                "area": 1150665.8,
                "rayon": "Кузьминки",
                "okrug_shor": "ЮВАО",
            }
        ]
        read_cm = MagicMock()
        read_cm.__enter__.return_value = read_cur
        read_cm.__exit__.return_value = False

        conn = MagicMock()

        def cursor(cursor_factory=None):
            if cursor_factory is not None:
                return read_cm
            return write_cm

        conn.cursor.side_effect = cursor

        result = import_parsed_gpkg(conn, parsed)
        self.assertEqual(result.inserted, 1)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.items[0].task_number, "М/ЮВАО-26-3/Кузьминки-1")

        sqls = [" ".join(str(c.args[0]).split()) for c in write_cur.execute.call_args_list]
        self.assertTrue(any("SET LOCAL statement_timeout" in s for s in sqls))
        self.assertTrue(any("pg_advisory_xact_lock" in s for s in sqls))
        self.assertTrue(any("CALL crm.refresh_tasks_area_quarterly()" in s for s in sqls))
        self.assertTrue(any("p.proname = 'refresh_task_area_keys'" in s for s in sqls))
        self.assertFalse(any("CALL crm.refresh_task_area_keys()" in s for s in sqls))
        conn.commit.assert_called_once()


class GpkgAreaAuthTests(unittest.TestCase):
    def test_require_admin_rejects_office(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            require_admin(_session("office"))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_route_requires_admin(self) -> None:
        from app.auth.deps import require_admin as require_dep
        from app.routes import gpkg_area as gpkg_area_routes

        paths = {getattr(route, "path", None) for route in gpkg_area_routes.router.routes}
        self.assertIn("/api/admin/tasks-area/gpkg", paths)
        for route in gpkg_area_routes.router.routes:
            dependant = getattr(route, "dependant", None)
            if dependant is None:
                continue
            dep_calls = [d.call for d in dependant.dependencies if d.call is not None]
            self.assertIn(require_dep, dep_calls)


if __name__ == "__main__":
    unittest.main()
