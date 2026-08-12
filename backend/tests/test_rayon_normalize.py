"""Regression: multi-word hood rayon names with CR/LF / hyphen spaces must match tasks_area."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.auth.service import fetch_allowed_rayons, is_rayon_allowed
from app.auth.session import UserSession
from app.crm.personnel import list_area_tasks_for_assignment, list_field_tasks_for_assignment
from app.crm.snapshot_loader import fetch_snapshot_rows
from app.crm.tasks_area import fetch_tasks_area_geojson
from app.layers.geojson import (
    normalize_rayon_name,
    sql_normalize_rayon_expr,
    sql_rayon_matches,
)


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
            ("Чертаново \r\nСеверное", "Чертаново Северное"),
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

    def test_sql_rayon_matches_includes_null_fallback(self) -> None:
        expr = sql_rayon_matches('"rayon"')
        self.assertIn("regexp_replace", expr)
        self.assertIn('"rayon" IS NULL', expr)
        self.assertIn("= %s", expr)

    def test_sql_rayon_matches_can_disallow_null(self) -> None:
        expr = sql_rayon_matches('"rayon"', allow_null=False)
        self.assertNotIn("IS NULL", expr)
        self.assertIn("= %s", expr)


class FetchSnapshotRowsRayonFilterTests(unittest.TestCase):
    def test_rayon_filter_uses_normalized_sql_and_param(self) -> None:
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)
        store_cfg = {"schema": "crm", "field_table": "tasks_field"}

        with patch("app.crm.store.ensure_rayon_column", return_value=True):
            fetch_snapshot_rows(
                conn,
                store_cfg,
                "field_table",
                "tasks_field",
                rayon="Чертаново \r\nЦентральное",
            )

        sql, params = cursor.execute.call_args.args
        self.assertIn("regexp_replace", sql)
        self.assertIn("\\s*-\\s*", sql)
        self.assertIn("IS NULL", sql)
        self.assertEqual(params[0], "Чертаново Центральное")


class ListFieldTasksRayonFilterTests(unittest.TestCase):
    def test_rayon_filter_uses_normalized_sql_and_param(self) -> None:
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        with patch("app.crm.personnel.ensure_all_executor_columns"), patch(
            "app.crm.store.ensure_rayon_column",
            return_value=True,
        ), patch(
            "app.crm.personnel.crm_task_store_config",
            return_value={"schema": "crm", "field_table": "tasks_field"},
        ), patch("app.layers.geojson.fetch_district_wkt", return_value=None):
            list_field_tasks_for_assignment(conn, rayon="Чертаново \r\n Южное")

        sql, params = cursor.execute.call_args.args
        self.assertIn("regexp_replace", sql)
        self.assertEqual(params[0], "Чертаново Южное")


class ListAreaTasksRayonFilterTests(unittest.TestCase):
    def test_rayon_filter_uses_normalized_sql_and_param(self) -> None:
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        with patch("app.crm.personnel.ensure_all_executor_columns"):
            list_area_tasks_for_assignment(conn, rayon="Чертаново \r\nСеверное")

        sql, params = cursor.execute.call_args.args
        self.assertIn("regexp_replace", sql)
        self.assertNotIn("IS NULL", sql)
        self.assertEqual(params[0], "Чертаново Северное")


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
