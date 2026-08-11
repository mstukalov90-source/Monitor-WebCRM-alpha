"""Tests for manager order-status notification feed."""

from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from app.crm.statistics import ORDER_STATUS_FEED_ACTIONS, fetch_order_status_feed


def _cursor_cm(cursor: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value = cursor
    cm.__exit__.return_value = False
    return cm


class FetchOrderStatusFeedTests(unittest.TestCase):
    def test_query_filters_feed_actions_and_orders_desc(self) -> None:
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            {
                "user_login": "office1",
                "user_role": "office",
                "object_type": "order",
                "action": "field_order_closed",
                "object_key": "11111111-1111-1111-1111-111111111111",
                "created_at": datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc),
                "task_number": "A-1",
                "rayon": "Тверской",
                "area_hectares": 1.5,
                "duration_seconds": None,
                "order_score": "good",
            },
            {
                "user_login": "office2",
                "user_role": "office",
                "object_type": "task",
                "action": "office_closed_legal",
                "object_key": "22222222-2222-2222-2222-222222222222",
                "created_at": datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc),
                "task_number": None,
                "rayon": "Арбат",
                "area_hectares": 0,
                "duration_seconds": None,
                "order_score": None,
            },
        ]
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        with patch("app.config.crm_task_store_config", return_value={}):
            rows = fetch_order_status_feed(
                conn,
                date_from=date(2026, 8, 1),
                date_to=date(2026, 8, 7),
                limit=50,
            )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["action"], "field_order_closed")
        self.assertEqual(rows[0]["task_number"], "A-1")
        self.assertEqual(rows[0]["order_score"], "good")
        self.assertEqual(rows[1]["action"], "office_closed_legal")
        self.assertEqual(rows[1]["rayon"], "Арбат")
        self.assertIsNone(rows[1]["duration_minutes"])
        self.assertIsNone(rows[1]["order_score"])

        sql = cursor.execute.call_args.args[0]
        params = cursor.execute.call_args.args[1]
        self.assertIn("ORDER BY s.created_at DESC", sql)
        self.assertIn("LIMIT %s", sql)
        self.assertIn("crm.field_score", sql)
        self.assertIn("fs.order_score", sql)
        for action in ORDER_STATUS_FEED_ACTIONS:
            self.assertIn(action, params)
        self.assertNotIn("office_analise_completed", params)
        self.assertEqual(params[-1], 50)

    def test_limit_is_capped(self) -> None:
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        with patch("app.config.crm_task_store_config", return_value={}):
            fetch_order_status_feed(
                conn,
                date_from=date(2026, 8, 1),
                date_to=date(2026, 8, 7),
                limit=10_000,
            )

        params = cursor.execute.call_args.args[1]
        self.assertEqual(params[-1], 500)


class OrderStatusRouteAuthTests(unittest.TestCase):
    def test_order_status_route_requires_manager_or_admin(self) -> None:
        from app.routes import personnel as personnel_routes

        route = next(
            r
            for r in personnel_routes.router.routes
            if getattr(r, "path", None) == "/api/personnel/order-status"
        )
        dependant = route.dependant
        dep_calls = [d.call for d in dependant.dependencies if d.call is not None]
        from app.auth.deps import require_manager_or_admin

        self.assertIn(require_manager_or_admin, dep_calls)


if __name__ == "__main__":
    unittest.main()
