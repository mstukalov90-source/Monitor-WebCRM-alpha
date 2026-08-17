"""Tests for OZN vs Monitoring spatial matching."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.auth.deps import require_manager_or_admin
from app.auth.session import UserSession
from app.crm.ozn_match import (
    OznMatchError,
    fetch_ozn_matches,
    resolve_ogh_analiz_columns,
)


def _session(role: str) -> UserSession:
    return UserSession(
        uuid="11111111-2222-3333-4444-555555555555",
        login="tester",
        role=role,
        work_zones=[],
    )


def _cursor_cm(cursor: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value = cursor
    cm.__exit__.return_value = False
    return cm


class OznMatchAuthTests(unittest.TestCase):
    def test_manager_and_admin_allowed(self) -> None:
        self.assertEqual(require_manager_or_admin(_session("admin")).role, "admin")
        self.assertEqual(require_manager_or_admin(_session("manager")).role, "manager")

    def test_office_and_field_rejected(self) -> None:
        for role in ("office", "field"):
            with self.assertRaises(HTTPException) as ctx:
                require_manager_or_admin(_session(role))
            self.assertEqual(ctx.exception.status_code, 403)

    def test_route_requires_manager_or_admin(self) -> None:
        from app.auth.deps import require_manager_or_admin as require_dep
        from app.routes import ozn_match as ozn_match_routes

        route = next(
            r
            for r in ozn_match_routes.router.routes
            if getattr(r, "path", None) == "/api/ozn-match"
        )
        dependant = route.dependant
        dep_calls = [d.call for d in dependant.dependencies if d.call is not None]
        self.assertIn(require_dep, dep_calls)


class OznMatchLoaderTests(unittest.TestCase):
    def test_missing_table_raises_503(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (None,)
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        with self.assertRaises(OznMatchError) as ctx:
            resolve_ogh_analiz_columns(conn)
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("не найдена", str(ctx.exception))

    def test_orders_sorted_by_match_count_desc(self) -> None:
        geom_a = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
        geom_b = {"type": "Polygon", "coordinates": [[[2, 2], [3, 2], [3, 3], [2, 2]]]}
        ozn_1 = {"type": "Polygon", "coordinates": [[[0.2, 0.2], [0.4, 0.2], [0.4, 0.4], [0.2, 0.2]]]}
        ozn_2 = {"type": "Polygon", "coordinates": [[[0.5, 0.5], [0.7, 0.5], [0.7, 0.7], [0.5, 0.5]]]}
        ozn_3 = {"type": "Polygon", "coordinates": [[[2.1, 2.1], [2.2, 2.1], [2.2, 2.2], [2.1, 2.1]]]}

        pair_cursor = MagicMock()
        pair_cursor.fetchall.return_value = [
            {
                "order_key": "aaa",
                "task_number": "10",
                "rayon": "Сокол",
                "area": 1000,
                "status": "wip",
                "order_geometry": geom_a,
                "ozn_id": "o1",
                "ozn_label": "ОЗН-1",
                "ozn_geometry": ozn_1,
            },
            {
                "order_key": "bbb",
                "task_number": "20",
                "rayon": "Сокол",
                "area": 500,
                "status": "free",
                "order_geometry": geom_b,
                "ozn_id": "o2",
                "ozn_label": "ОЗН-2",
                "ozn_geometry": ozn_2,
            },
            {
                "order_key": "bbb",
                "task_number": "20",
                "rayon": "Сокол",
                "area": 500,
                "status": "free",
                "order_geometry": geom_b,
                "ozn_id": "o3",
                "ozn_label": "ОЗН-3",
                "ozn_geometry": ozn_3,
            },
        ]
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(pair_cursor)

        with patch(
            "app.crm.ozn_match.resolve_ogh_analiz_columns",
            return_value={"geom": "geom", "id": "id", "label": "number"},
        ):
            result = fetch_ozn_matches(conn, rayon="Сокол")

        self.assertEqual([order["order_key"] for order in result["orders"]], ["bbb", "aaa"])
        self.assertEqual(result["orders"][0]["match_count"], 2)
        self.assertEqual(result["orders"][1]["match_count"], 1)
        self.assertEqual(sorted(result["matches"]["bbb"]), ["o2", "o3"])
        self.assertEqual(len(result["ozn_objects"]), 3)
        self.assertEqual(result["district_name"], "Сокол")

    def test_duplicate_ozn_id_counted_once(self) -> None:
        geom = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
        ozn = {"type": "Polygon", "coordinates": [[[0.2, 0.2], [0.4, 0.2], [0.4, 0.4], [0.2, 0.2]]]}
        pair_cursor = MagicMock()
        pair_cursor.fetchall.return_value = [
            {
                "order_key": "aaa",
                "task_number": "10",
                "rayon": "Сокол",
                "area": 1000,
                "status": "wip",
                "order_geometry": geom,
                "ozn_id": "o1",
                "ozn_label": "ОЗН-1",
                "ozn_geometry": ozn,
            },
            {
                "order_key": "aaa",
                "task_number": "10",
                "rayon": "Сокол",
                "area": 1000,
                "status": "wip",
                "order_geometry": geom,
                "ozn_id": "o1",
                "ozn_label": "ОЗН-1",
                "ozn_geometry": ozn,
            },
        ]
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(pair_cursor)

        with patch(
            "app.crm.ozn_match.resolve_ogh_analiz_columns",
            return_value={"geom": "geom", "id": "id", "label": "id"},
        ):
            result = fetch_ozn_matches(conn)

        self.assertEqual(result["orders"][0]["match_count"], 1)
        self.assertEqual(result["matches"]["aaa"], ["o1"])
        self.assertEqual(len(result["ozn_objects"]), 1)

    def test_query_filters_free_and_wip_and_selects_ozn_fields(self) -> None:
        pair_cursor = MagicMock()
        pair_cursor.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(pair_cursor)

        with patch(
            "app.crm.ozn_match.resolve_ogh_analiz_columns",
            return_value={
                "geom": "geom",
                "id": "id",
                "label": "order_name",
                "order_name": "order_name",
                "ozn_date": "ozn_date",
                "executor": "executor",
            },
        ):
            fetch_ozn_matches(conn)

        sql = pair_cursor.execute.call_args[0][0]
        self.assertIn("ta.status IN ('free', 'wip')", sql)
        self.assertIn("ta.executor", sql)
        self.assertIn("ozn_order_name", sql)
        self.assertIn("ozn_date", sql)
        self.assertIn("ozn_executor", sql)

    def test_ozn_and_order_executor_fields_mapped(self) -> None:
        geom = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
        ozn = {"type": "Polygon", "coordinates": [[[0.2, 0.2], [0.4, 0.2], [0.4, 0.4], [0.2, 0.2]]]}
        pair_cursor = MagicMock()
        pair_cursor.fetchall.return_value = [
            {
                "order_key": "aaa",
                "task_number": "10",
                "rayon": "Сокол",
                "area": 1000,
                "status": "free",
                "executor": "ivanov",
                "order_geometry": geom,
                "ozn_id": "o1",
                "ozn_label": "ОЗН-1",
                "ozn_order_name": "Заказ ОЗН 77",
                "ozn_date": "2026-04-01",
                "ozn_executor": "Иванов Иван",
                "ozn_geometry": ozn,
            },
        ]
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(pair_cursor)

        with patch(
            "app.crm.ozn_match.resolve_ogh_analiz_columns",
            return_value={"geom": "geom", "id": "id", "label": "order_name"},
        ):
            result = fetch_ozn_matches(conn)

        self.assertEqual(result["orders"][0]["executor"], "ivanov")
        self.assertEqual(result["orders"][0]["status"], "free")
        obj = result["ozn_objects"][0]
        self.assertEqual(obj["order_name"], "Заказ ОЗН 77")
        self.assertEqual(obj["ozn_date"], "2026-04-01")
        self.assertEqual(obj["executor"], "Иванов Иван")

    def test_resolve_optional_columns_and_prefers_order_name_label(self) -> None:
        table_cursor = MagicMock()
        table_cursor.fetchone.return_value = ("odh_export.ogh_analiz",)
        cols_cursor = MagicMock()
        cols_cursor.fetchall.return_value = [
            {"column_name": "id", "udt_name": "int4"},
            {"column_name": "geom", "udt_name": "geometry"},
            {"column_name": "number", "udt_name": "text"},
            {"column_name": "order_name", "udt_name": "text"},
            {"column_name": "ozn_date", "udt_name": "date"},
            {"column_name": "executor", "udt_name": "text"},
        ]
        conn = MagicMock()
        conn.cursor.side_effect = [_cursor_cm(table_cursor), _cursor_cm(cols_cursor)]

        resolved = resolve_ogh_analiz_columns(conn)
        self.assertEqual(resolved["label"], "order_name")
        self.assertEqual(resolved["order_name"], "order_name")
        self.assertEqual(resolved["ozn_date"], "ozn_date")
        self.assertEqual(resolved["executor"], "executor")


if __name__ == "__main__":
    unittest.main()
