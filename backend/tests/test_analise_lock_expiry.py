"""Tests for daily expiry of incomplete area-analise locks."""

from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from app.crm.tasks_area import clear_stale_analise_locks, start_area_analise

MSK = ZoneInfo("Europe/Moscow")


def _cursor_cm(cursor: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value = cursor
    cm.__exit__.return_value = False
    return cm


class ClearStaleAnaliseLocksTests(unittest.TestCase):
    def test_clear_runs_moscow_day_boundary_update(self) -> None:
        cursor = MagicMock()
        cursor.fetchall.return_value = [("key-1",), ("key-2",)]
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        with patch("app.crm.tasks_area.ensure_analise_audit_columns", return_value=True):
            cleared = clear_stale_analise_locks(conn)

        self.assertEqual(cleared, 2)
        sql = cursor.execute.call_args.args[0]
        self.assertIn("analise_started_by = NULL", sql)
        self.assertIn("analise_paused_at = NULL", sql)
        self.assertIn("Europe/Moscow", sql)
        self.assertIn("COALESCE(analise, FALSE) = FALSE", sql)
        conn.commit.assert_called_once()

    def test_clear_returns_zero_when_nothing_stale(self) -> None:
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        with patch("app.crm.tasks_area.ensure_analise_audit_columns", return_value=True):
            cleared = clear_stale_analise_locks(conn)

        self.assertEqual(cleared, 0)


class StartAreaAnaliseAfterDailyResetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = str(uuid.uuid4())
        self.now_msk = datetime.now(MSK)

    def test_yesterday_lock_allows_other_user_after_clear(self) -> None:
        update_cursor = MagicMock()
        update_cursor.fetchone.return_value = (self.key,)
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(update_cursor)

        with (
            patch("app.crm.tasks_area.ensure_tasks_area_audit_columns", return_value=True),
            patch("app.crm.tasks_area.ensure_analise_audit_columns", return_value=True),
            patch("app.crm.tasks_area.clear_stale_analise_locks", return_value=1) as clear_mock,
            patch(
                "app.crm.tasks_area._fetch_analise_state",
                return_value={
                    "analise": False,
                    "analise_started_by": None,
                    "analise_started_at": None,
                    "analise_paused_by": None,
                    "analise_paused_at": None,
                },
            ),
            patch("app.crm.tasks_area.make_user_audit", return_value=["OtherUser", "ts"]),
        ):
            # Simulate that clear already wiped yesterday's SkachkovNA lock.
            result = start_area_analise(conn, self.key, "OtherUser")

        self.assertEqual(result, "updated")
        clear_mock.assert_called_once_with(conn)
        update_sql = update_cursor.execute.call_args.args[0]
        self.assertIn("analise_started_by = %s", update_sql)
        self.assertEqual(update_cursor.execute.call_args.args[1][0], "OtherUser")

    def test_same_day_lock_still_conflicts_for_other_user(self) -> None:
        started_at = self.now_msk.replace(hour=10, minute=0, second=0, microsecond=0)
        if started_at > self.now_msk:
            started_at = self.now_msk - timedelta(hours=1)

        conn = MagicMock()

        with (
            patch("app.crm.tasks_area.ensure_tasks_area_audit_columns", return_value=True),
            patch("app.crm.tasks_area.ensure_analise_audit_columns", return_value=True),
            patch("app.crm.tasks_area.clear_stale_analise_locks", return_value=0) as clear_mock,
            patch(
                "app.crm.tasks_area._fetch_analise_state",
                return_value={
                    "analise": False,
                    "analise_started_by": "SkachkovNA",
                    "analise_started_at": started_at.astimezone(timezone.utc),
                    "analise_paused_by": None,
                    "analise_paused_at": None,
                },
            ),
        ):
            result = start_area_analise(conn, self.key, "OtherUser")

        self.assertEqual(result, "conflict")
        clear_mock.assert_called_once_with(conn)

    def test_completed_analise_not_reclaimed(self) -> None:
        conn = MagicMock()

        with (
            patch("app.crm.tasks_area.ensure_tasks_area_audit_columns", return_value=True),
            patch("app.crm.tasks_area.ensure_analise_audit_columns", return_value=True),
            patch("app.crm.tasks_area.clear_stale_analise_locks", return_value=0),
            patch(
                "app.crm.tasks_area._fetch_analise_state",
                return_value={
                    "analise": True,
                    "analise_started_by": "SkachkovNA",
                    "analise_started_at": self.now_msk - timedelta(days=2),
                    "analise_paused_by": None,
                    "analise_paused_at": None,
                },
            ),
        ):
            result = start_area_analise(conn, self.key, "OtherUser")

        self.assertEqual(result, "skipped")


class FetchTasksAreaClearsStaleLocksTests(unittest.TestCase):
    def test_fetch_geojson_clears_stale_locks_first(self) -> None:
        from app.crm.tasks_area import fetch_tasks_area_geojson

        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "geojson": {"type": "FeatureCollection", "features": []},
        }
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        with patch("app.crm.tasks_area.clear_stale_analise_locks", return_value=3) as clear_mock:
            result = fetch_tasks_area_geojson(conn, rayon="Сокол")

        clear_mock.assert_called_once_with(conn)
        self.assertEqual(result["type"], "FeatureCollection")


if __name__ == "__main__":
    unittest.main()
