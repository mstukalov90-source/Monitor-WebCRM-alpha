"""Regression: multi-word hood rayon names with CR/LF / hyphen spaces must match tasks_area."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.auth.service import fetch_allowed_rayons, is_rayon_allowed
from app.auth.session import UserSession
from app.crm.tasks_area import fetch_tasks_area_geojson
from app.layers.geojson import normalize_rayon_name, sql_normalize_rayon_expr


def _cursor_cm(cursor: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value = cursor
    cm.__exit__.return_value = False
    return cm


class NormalizeRayonNameTests(unittest.TestCase):
    def test_yuao_hood_artifacts_match_tasks_area(self) -> None:
        cases = [
            ("Бирюлево \r\nВосточное", "Бирюлево Восточное"),
            ("Бирюлево \r\nЗападное", "Бирюлево Западное"),
            ("Москворечье-  Сабурово", "Москворечье-Сабурово"),
            ("Нагатино-\r\nСадовники", "Нагатино-Садовники"),
            ("Нагатинский \r\n  затон", "Нагатинский затон"),
            ("Орехово-\r\nБорисово \r\nСеверное", "Орехово-Борисово Северное"),
            ("Орехово-\r\nБорисово \r\nЮжное", "Орехово-Борисово Южное"),
            ("Чертаново \r\nЦентральное", "Чертаново Центральное"),
            ("Чертаново \r\n Южное", "Чертаново Южное"),
            ("Тропарево- Никулино", "Тропарево-Никулино"),
            ("Фили- Давыдково", "Фили-Давыдково"),
            ("Братеево", "Братеево"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_rayon_name(raw), expected)
                self.assertEqual(normalize_rayon_name(expected), expected)

    def test_empty_and_noneish(self) -> None:
        self.assertEqual(normalize_rayon_name(""), "")
        self.assertEqual(normalize_rayon_name("   "), "")
        self.assertEqual(normalize_rayon_name(None), "")  # type: ignore[arg-type]

    def test_sql_expr_collapses_whitespace_and_hyphen_spaces(self) -> None:
        expr = sql_normalize_rayon_expr('"rayon"')
        self.assertIn("regexp_replace", expr)
        self.assertIn("\\s+", expr)
        self.assertIn("\\s*-\\s*", expr)


class FetchTasksAreaGeojsonRayonFilterTests(unittest.TestCase):
    def test_single_rayon_uses_normalized_sql_and_param(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "geojson": {"type": "FeatureCollection", "features": []},
        }
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        with patch("app.crm.tasks_area.clear_stale_analise_locks", return_value=0):
            fetch_tasks_area_geojson(conn, rayon="Нагатино-\r\nСадовники")

        sql, params = cursor.execute.call_args.args
        self.assertIn("regexp_replace", sql)
        self.assertIn("\\s*-\\s*", sql)
        self.assertEqual(params[0], "Нагатино-Садовники")

    def test_rayons_list_normalizes_each_entry(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "geojson": {"type": "FeatureCollection", "features": []},
        }
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        with patch("app.crm.tasks_area.clear_stale_analise_locks", return_value=0):
            fetch_tasks_area_geojson(
                conn,
                rayons=["Орехово-\r\nБорисово \r\nСеверное", "Бирюлево \r\nВосточное"],
            )

        sql, params = cursor.execute.call_args.args
        self.assertIn("= ANY(%s)", sql)
        self.assertEqual(
            params[0],
            ["Орехово-Борисово Северное", "Бирюлево Восточное"],
        )


class IsRayonAllowedNormalizeTests(unittest.TestCase):
    def test_allows_when_hood_name_has_crlf(self) -> None:
        cursor = MagicMock()
        cursor.fetchall.return_value = [("Нагатино-\r\nСадовники",)]
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)
        session = UserSession(
            uuid="u1",
            login="field1",
            role="field",
            work_zones=[42],
        )

        self.assertTrue(is_rayon_allowed(conn, session, "Нагатино-Садовники"))
        self.assertTrue(is_rayon_allowed(conn, session, "Нагатино-\r\nСадовники"))

    def test_fetch_allowed_rayons_returns_normalized(self) -> None:
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            ("Орехово-\r\nБорисово \r\nЮжное",),
            ("Братеево",),
        ]
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)
        session = UserSession(
            uuid="u1",
            login="field1",
            role="field",
            work_zones=[1, 2],
        )

        self.assertEqual(
            fetch_allowed_rayons(conn, session),
            ["Орехово-Борисово Южное", "Братеево"],
        )


if __name__ == "__main__":
    unittest.main()
