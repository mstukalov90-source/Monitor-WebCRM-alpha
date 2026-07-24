"""Tests for OATI letter helpers: placeholders, map scale, geocode, lookups."""

from __future__ import annotations

import io
import unittest
from unittest.mock import MagicMock, patch
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from app.auth.deps import require_manager_or_admin
from app.auth.session import UserSession
from app.letters.docx_fill import (
    BODY_FONT_NAME,
    BODY_FONT_SIZE,
    DEFAULT_VIOLATION,
    PH_DESCRIPTION,
    PH_DOC_DATE,
    PH_STREET,
    PH_VIOLATION,
    append_map_page,
    append_photo_pages,
    document_to_bytes,
    fill_letter_template,
    format_ru_date,
    format_ru_datetime,
    format_wgs84,
)
from app.letters.geocode import (
    HOUSE_SEARCH_RADIUS_M,
    GeocodeResult,
    format_street_house,
    reverse_geocode_parts,
)
from app.letters.map_image import (
    GROUND_WIDTH_M,
    MAP_SCALE,
    classify_geometry_visibility,
    map_bbox_mercator,
)
from app.letters.oati import (
    LetterError,
    _lookup_engineering,
    _lookup_executor,
    _lookup_mos_simple_address,
    _validate_photo_ids,
    merge_engineering_values,
    pick_default_address,
    resolve_incident_datetime,
)
from fastapi import HTTPException


NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def _docx_text(data: bytes) -> str:
    root = ET.fromstring(ZipFile(io.BytesIO(data)).read("word/document.xml"))
    return "".join((t.text or "") for t in root.findall(".//w:t", NS))


def _docx_image_count(data: bytes) -> int:
    root = ET.fromstring(ZipFile(io.BytesIO(data)).read("word/document.xml"))
    drawings = root.findall(
        ".//{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}inline"
    )
    return len(drawings)


class DocxFillTests(unittest.TestCase):
    def test_replaces_new_template_placeholders(self) -> None:
        doc = fill_letter_template(
            street="ул. Ленина",
            today="23.07.2026",
            fid=7,
            executor="ООО Строй",
            incident_datetime="22.07.2026 15:30",
            address="ул. Ленина, 10",
            coordinates="55.800000, 37.500000",
            engineering="теплосеть",
            description="описание А",
            violation="",
        )
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (40, 40), (180, 180, 180)).save(buf, format="PNG")
        png = buf.getvalue()
        append_map_page(doc, png)
        append_photo_pages(doc, [(png, "Фото 1")])
        data = document_to_bytes(doc)
        text = _docx_text(data)

        self.assertNotIn(PH_DOC_DATE, text)
        self.assertNotIn(PH_STREET, text)
        self.assertNotIn(PH_DESCRIPTION, text)
        self.assertNotIn(PH_VIOLATION, text)
        self.assertIn("от 23.07.2026 г.", text)
        self.assertIn("№ 7", text)
        self.assertIn("ул. Ленина", text)
        self.assertIn("ООО Строй", text)
        self.assertIn("описание А", text)
        self.assertIn(DEFAULT_VIOLATION, text)
        self.assertIn("Ситуационный план", text)
        self.assertGreaterEqual(_docx_image_count(data), 2)

        # Soft breaks before items 1 and 7 must survive fill.
        joined = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("\n1. Сведения о производителе работ:", joined)
        self.assertIn(
            "\n7. Данные, указывающие на признаки наличия события административного правонарушения:",
            joined,
        )

        # Body text (report + appendix) must be Times New Roman 14.
        body_markers = (
            "ГБУ «Мосгоргеотрест»",
            "Отчёт об инциденте",
            "1. Сведения о производителе работ",
            "2. Дата и время",
            "7. Данные, указывающие",
            "Приложение:",
            "1. Ситуационный план:",
        )
        for paragraph in doc.paragraphs:
            if not any(m in paragraph.text for m in body_markers):
                continue
            for run in paragraph.runs:
                if not (run.text or "").strip():
                    continue
                self.assertEqual(run.font.name, BODY_FONT_NAME, msg=repr(run.text[:40]))
                self.assertEqual(
                    run.font.size.pt if run.font.size else None,
                    BODY_FONT_SIZE.pt,
                    msg=repr(run.text[:40]),
                )

    def test_format_helpers(self) -> None:
        self.assertEqual(format_wgs84(37.5, 55.8), "55.800000, 37.500000")
        self.assertRegex(format_ru_date(), r"\d{2}\.\d{2}\.\d{4}")
        self.assertEqual(format_ru_datetime("2026-07-22T12:30:00+03:00"), "22.07.2026 12:30")


class MapScaleTests(unittest.TestCase):
    def test_ground_extent_matches_scale_1000(self) -> None:
        self.assertEqual(MAP_SCALE, 1000)
        self.assertEqual(GROUND_WIDTH_M, 160.0)

    def test_bbox_centered_on_report(self) -> None:
        lon, lat = 37.5, 55.8
        minx, miny, maxx, maxy = map_bbox_mercator(lon, lat)
        self.assertAlmostEqual(maxx - minx, GROUND_WIDTH_M, places=3)
        self.assertAlmostEqual(maxy - miny, GROUND_WIDTH_M, places=3)

    def test_geometry_visibility_clipping_states(self) -> None:
        center_lon, center_lat = 37.5, 55.8
        inside = {"type": "Point", "coordinates": [center_lon, center_lat]}
        outside = {"type": "Point", "coordinates": [center_lon + 0.05, center_lat + 0.05]}
        partial = {
            "type": "LineString",
            "coordinates": [
                [center_lon, center_lat],
                [center_lon + 0.05, center_lat + 0.05],
            ],
        }
        self.assertEqual(classify_geometry_visibility(inside, center_lon, center_lat), "inside")
        self.assertEqual(classify_geometry_visibility(outside, center_lon, center_lat), "outside")
        self.assertEqual(classify_geometry_visibility(partial, center_lon, center_lat), "partial")
        self.assertEqual(classify_geometry_visibility(None, center_lon, center_lat), "missing")


class GeocodeFormatTests(unittest.TestCase):
    def test_street_house_from_nominatim(self) -> None:
        self.assertEqual(
            format_street_house({"road": "ул. Ленина", "house_number": "10"}),
            "ул. Ленина, 10",
        )
        self.assertIsNone(format_street_house({}))
        self.assertEqual(format_street_house({"road": "Тверская"}), "Тверская")

    def test_reverse_parts_prefers_house_number(self) -> None:
        from app.config import Settings

        settings = Settings(nominatim_url="https://example.invalid/reverse")
        reverse_payload = {
            "address": {"road": "ул. Ленина", "house_number": "12к1"},
        }
        with patch("app.letters.geocode._nominatim_get", return_value=reverse_payload):
            result = reverse_geocode_parts(37.5, 55.8, settings)
        self.assertEqual(result.street, "ул. Ленина")
        self.assertEqual(result.address, "ул. Ленина, 12к1")
        self.assertTrue(result.has_house)

    def test_reverse_parts_searches_nearby_when_house_missing(self) -> None:
        import math
        from app.config import Settings
        from urllib.parse import parse_qs, urlparse

        settings = Settings(nominatim_url="https://example.invalid/reverse")
        search_urls: list[str] = []

        def fake_get(url: str, _settings: Settings):
            if "/search" in url:
                search_urls.append(url)
                return [
                    {
                        "lat": "55.80001",
                        "lon": "37.50001",
                        "address": {"road": "ул. Ленина", "house_number": "5"},
                    }
                ]
            return {"address": {"road": "ул. Ленина"}}

        with patch("app.letters.geocode._nominatim_get", side_effect=fake_get):
            result = reverse_geocode_parts(37.5, 55.8, settings)
        self.assertEqual(result.address, "ул. Ленина, 5")
        self.assertTrue(result.has_house)
        self.assertEqual(HOUSE_SEARCH_RADIUS_M, 250.0)
        self.assertTrue(search_urls)
        qs = parse_qs(urlparse(search_urls[0]).query)
        self.assertEqual(qs.get("limit"), ["20"])
        left, top, right, bottom = (float(x) for x in qs["viewbox"][0].split(","))
        half_lat = (top - bottom) / 2
        expected_lat = HOUSE_SEARCH_RADIUS_M / 111_320.0
        self.assertAlmostEqual(half_lat, expected_lat, places=6)
        expected_lon = HOUSE_SEARCH_RADIUS_M / (111_320.0 * max(0.2, math.cos(math.radians(55.8))))
        self.assertAlmostEqual((right - left) / 2, expected_lon, places=6)

    def test_reverse_geocode_returns_empty_on_network_error(self) -> None:
        from app.config import Settings

        settings = Settings(nominatim_url="https://example.invalid/reverse")
        with patch("app.letters.geocode.urllib.request.urlopen", side_effect=OSError("down")):
            result = reverse_geocode_parts(37.5, 55.8, settings)
        self.assertEqual(result, GeocodeResult())


class SourceLookupTests(unittest.TestCase):
    def test_executor_from_source_general_contractor(self) -> None:
        conn = MagicMock()
        record = MagicMock(key="task-1")
        with (
            patch(
                "app.letters.oati._lookup_source_feature",
                return_value={"attributes": {"general_contractor": "ООО Ромашка"}},
            ),
            patch("app.letters.oati._lookup_field_assignee", return_value="field_user") as field_mock,
        ):
            self.assertEqual(_lookup_executor(conn, record, {}), "ООО Ромашка")
            field_mock.assert_not_called()

    def test_executor_falls_back_to_field_assignee(self) -> None:
        conn = MagicMock()
        record = MagicMock(key="task-1")
        with (
            patch("app.letters.oati._lookup_source_feature", return_value={"attributes": {}}),
            patch("app.letters.oati._lookup_field_assignee", return_value="ivanov"),
        ):
            self.assertEqual(_lookup_executor(conn, record, {}), "ivanov")

    def test_engineering_from_engineering_net_obj_not_type(self) -> None:
        conn = MagicMock()
        record = MagicMock(key="task-1", type="АВР")
        with patch(
            "app.letters.oati._lookup_source_feature",
            return_value={"attributes": {"engineering_net_obj": "теплосеть", "type": "ignore"}},
        ):
            self.assertEqual(_lookup_engineering(conn, record, {}), "теплосеть")

    def test_engineering_empty_when_only_task_type_present(self) -> None:
        conn = MagicMock()
        record = MagicMock(key="task-1", type="Разрытия")
        with patch(
            "app.letters.oati._lookup_source_feature",
            return_value={"attributes": {"something_else": "x"}},
        ):
            self.assertEqual(_lookup_engineering(conn, record, {}), "")

    def test_engineering_merges_report_comm_type(self) -> None:
        conn = MagicMock()
        record = MagicMock(key="task-1")
        with patch(
            "app.letters.oati._lookup_source_feature",
            return_value={"attributes": {"engineering_net_obj": "Тепловая сеть"}},
        ):
            self.assertEqual(
                _lookup_engineering(conn, record, {}, report_comm_type="Теплосеть"),
                "Тепловая сеть, Теплосеть",
            )

    def test_engineering_uses_comm_type_when_source_empty(self) -> None:
        conn = MagicMock()
        record = MagicMock(key="task-1")
        with patch(
            "app.letters.oati._lookup_source_feature",
            return_value={"attributes": {}},
        ):
            self.assertEqual(
                _lookup_engineering(conn, record, {}, report_comm_type="Газопровод"),
                "Газопровод",
            )

    def test_merge_engineering_values(self) -> None:
        self.assertEqual(merge_engineering_values("", ""), "")
        self.assertEqual(merge_engineering_values("A", ""), "A")
        self.assertEqual(merge_engineering_values("", "B"), "B")
        self.assertEqual(merge_engineering_values("Теплосеть", "теплосеть"), "Теплосеть")
        self.assertEqual(merge_engineering_values("A", "B"), "A, B")


class IncidentDatetimeTests(unittest.TestCase):
    def test_prefers_taken_at_over_created_at(self) -> None:
        from app.photos.field_photo import FieldPhotoItem

        photos = [
            FieldPhotoItem(
                id=1,
                file_path="a.jpg",
                banner=False,
                created_at="2026-07-23T16:40:00+03:00",
                photo_key=None,
                username=None,
                taken_at=None,
            ),
            FieldPhotoItem(
                id=2,
                file_path="b.jpg",
                banner=False,
                created_at="2026-07-23T10:00:00+03:00",
                photo_key=None,
                username=None,
                taken_at="2026-07-22T12:30:00+03:00",
            ),
        ]
        self.assertEqual(resolve_incident_datetime(photos), "22.07.2026 12:30")

    def test_falls_back_to_created_at_when_taken_at_null(self) -> None:
        from app.photos.field_photo import FieldPhotoItem

        photos = [
            FieldPhotoItem(
                id=1,
                file_path="a.jpg",
                banner=False,
                created_at="2026-07-23T16:40:00+03:00",
                photo_key=None,
                username=None,
                taken_at=None,
            ),
        ]
        self.assertEqual(resolve_incident_datetime(photos), "23.07.2026 16:40")

    def test_preferred_ids_order_for_taken_at(self) -> None:
        from app.photos.field_photo import FieldPhotoItem

        photos = [
            FieldPhotoItem(
                id=1,
                file_path="a.jpg",
                banner=False,
                created_at=None,
                photo_key=None,
                username=None,
                taken_at="2026-07-21T09:00:00+03:00",
            ),
            FieldPhotoItem(
                id=2,
                file_path="b.jpg",
                banner=False,
                created_at=None,
                photo_key=None,
                username=None,
                taken_at="2026-07-22T11:00:00+03:00",
            ),
        ]
        self.assertEqual(
            resolve_incident_datetime(photos, preferred_ids=[2, 1]),
            "22.07.2026 11:00",
        )


class MosAddressLookupTests(unittest.TestCase):
    def test_contains_hit(self) -> None:
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchone.return_value = ("Енисейская улица, дом 39А",)
        conn.cursor.return_value.__enter__.return_value = cur
        self.assertEqual(_lookup_mos_simple_address(conn, 37.5, 55.8), "Енисейская улица, дом 39А")
        self.assertEqual(cur.execute.call_count, 1)

    def test_contains_miss_falls_back_to_nearest(self) -> None:
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchone.side_effect = [None, ("Соловьиный проезд, дом 2",)]
        conn.cursor.return_value.__enter__.return_value = cur
        self.assertEqual(_lookup_mos_simple_address(conn, 37.5, 55.8), "Соловьиный проезд, дом 2")
        self.assertEqual(cur.execute.call_count, 2)
        nearest_sql = cur.execute.call_args_list[1][0][0]
        self.assertIn("<->", nearest_sql)

    def test_db_error_returns_empty(self) -> None:
        conn = MagicMock()
        conn.cursor.side_effect = OSError("db down")
        self.assertEqual(_lookup_mos_simple_address(conn, 37.5, 55.8), "")

    def test_pick_default_address_prefers_geocode_with_house(self) -> None:
        self.assertEqual(
            pick_default_address(
                address_geocode="ул. А, 1",
                address_mos="ул. Б, дом 2",
                address_has_house=True,
            ),
            "ул. А, 1",
        )

    def test_pick_default_address_prefers_mos_without_house(self) -> None:
        self.assertEqual(
            pick_default_address(
                address_geocode="ул. А",
                address_mos="ул. Б, дом 2",
                address_has_house=False,
            ),
            "ул. Б, дом 2",
        )

    def test_pick_default_address_geocode_when_mos_empty(self) -> None:
        self.assertEqual(
            pick_default_address(
                address_geocode="ул. А",
                address_mos="",
                address_has_house=False,
            ),
            "ул. А",
        )


class PhotoValidationTests(unittest.TestCase):
    def test_rejects_foreign_photo_ids(self) -> None:
        conn = MagicMock()
        photo = MagicMock()
        photo.id = 10
        with patch(
            "app.letters.oati.fetch_field_photos",
            return_value=MagicMock(photos=[photo]),
        ):
            with self.assertRaises(LetterError) as ctx:
                _validate_photo_ids(conn, "task", 1, [10, 99])
            self.assertIn("99", str(ctx.exception))

    def test_dedupes_preserving_order(self) -> None:
        conn = MagicMock()
        p1, p2 = MagicMock(id=1), MagicMock(id=2)
        with patch(
            "app.letters.oati.fetch_field_photos",
            return_value=MagicMock(photos=[p1, p2]),
        ):
            self.assertEqual(_validate_photo_ids(conn, "task", 1, [2, 1, 2]), [2, 1])


class RbacTests(unittest.TestCase):
    def test_require_manager_or_admin_rejects_office(self) -> None:
        user = UserSession(uuid="u", login="office1", role="office", work_zones=[])
        with self.assertRaises(HTTPException) as ctx:
            require_manager_or_admin(user)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_require_manager_or_admin_allows_manager(self) -> None:
        user = UserSession(uuid="u", login="mgr", role="manager", work_zones=[1])
        self.assertEqual(require_manager_or_admin(user), user)


if __name__ == "__main__":
    unittest.main()
