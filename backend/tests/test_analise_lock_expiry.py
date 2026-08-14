"""Tests for daily reset of area-analise locks and completed analyses."""

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
    def test_clear_runs_completed_and_lock_updates(self) -> None:
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [("done-1",), ("done-2",)],  # completed reset
            [("lock-1",)],  # incomplete lock reset
        ]
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        with patch("app.crm.tasks_area.ensure_analise_audit_columns", return_value=True):
            cleared = clear_stale_analise_locks(conn)

        self.assertEqual(cleared, 3)
        self.assertEqual(cursor.execute.call_count, 2)

        completed_sql = cursor.execute.call_args_list[0].args[0]
        self.assertIn("analise = FALSE", completed_sql)
        self.assertIn("analise_finished_at = NULL", completed_sql)
        self.assertIn("COALESCE(a.analise, FALSE) = TRUE", completed_sql)
        self.assertIn("Europe/Moscow", completed_sql)
        self.assertIn("07:00:00", completed_sql)
        self.assertIn("EXISTS", completed_sql)
        self.assertIn("field_observed", completed_sql)
        self.assertIn("user_created", completed_sql)
        self.assertIn("t.field_observed IS TRUE", completed_sql)
        self.assertIn('NOT EXISTS (SELECT 1 FROM "crm"."tasks_field"', completed_sql)
        self.assertNotIn("f.geom", completed_sql)
        self.assertIn("office_task_points", completed_sql)
        self.assertNotIn(
            'EXISTS (SELECT 1 FROM "crm"."tasks_field" s WHERE s.task_key = t.key) OR',
            completed_sql,
        )

        lock_sql = cursor.execute.call_args_list[1].args[0]
        self.assertIn("COALESCE(a.analise, FALSE) = FALSE", lock_sql)
        self.assertIn("analise_started_by = NULL", lock_sql)
        self.assertIn("Europe/Moscow", lock_sql)
        self.assertIn("07:00:00", lock_sql)
        self.assertNotIn("field_observed", lock_sql)
        self.assertNotIn("user_created", lock_sql)

        conn.commit.assert_called_once()

    def test_clear_returns_zero_when_nothing_stale(self) -> None:
        cursor = MagicMock()
        cursor.fetchall.side_effect = [[], []]
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        with patch("app.crm.tasks_area.ensure_analise_audit_columns", return_value=True):
            cleared = clear_stale_analise_locks(conn)

        self.assertEqual(cleared, 0)
        self.assertEqual(cursor.execute.call_count, 2)


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
            result = start_area_analise(conn, self.key, "OtherUser")

        self.assertEqual(result, "updated")
        clear_mock.assert_called_once_with(conn)
        update_sql = update_cursor.execute.call_args.args[0]
        self.assertIn("analise_started_by = %s", update_sql)
        self.assertEqual(update_cursor.execute.call_args.args[1][0], "OtherUser")

    def test_yesterday_completed_allows_reclaim_after_clear(self) -> None:
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
                # After daily reset of yesterday's completion, order is idle again.
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
            result = start_area_analise(conn, self.key, "OtherUser")

        self.assertEqual(result, "updated")
        clear_mock.assert_called_once_with(conn)

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

    def test_same_day_completed_analise_not_reclaimed(self) -> None:
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
                    "analise_started_at": self.now_msk - timedelta(hours=2),
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

        with (
            patch("app.crm.tasks_area.clear_stale_analise_locks", return_value=3) as clear_mock,
            patch("app.crm.tasks_area.clear_stale_pre_analise_locks", return_value=1) as clear_pre_mock,
        ):
            result = fetch_tasks_area_geojson(conn, rayon="Сокол")

        clear_mock.assert_called_once_with(conn)
        clear_pre_mock.assert_called_once_with(conn)
        self.assertEqual(result["type"], "FeatureCollection")


class ClearStalePreAnaliseLocksTests(unittest.TestCase):
    def test_clear_runs_completed_and_lock_updates(self) -> None:
        from app.crm.tasks_area import clear_stale_pre_analise_locks

        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [("done-1",), ("done-2",)],
            [("lock-1",)],
        ]
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        with patch("app.crm.tasks_area.ensure_pre_analise_audit_columns", return_value=True):
            cleared = clear_stale_pre_analise_locks(conn)

        self.assertEqual(cleared, 3)
        self.assertEqual(cursor.execute.call_count, 2)

        completed_sql = cursor.execute.call_args_list[0].args[0]
        self.assertIn("pre_analise = FALSE", completed_sql)
        self.assertIn("pre_analise_finished_at = NULL", completed_sql)
        self.assertIn("COALESCE(a.pre_analise, FALSE) = TRUE", completed_sql)
        self.assertIn("Europe/Moscow", completed_sql)
        self.assertIn("07:00:00", completed_sql)
        self.assertIn("EXISTS", completed_sql)
        self.assertIn("field_observed", completed_sql)
        self.assertIn("user_created", completed_sql)
        self.assertIn("COALESCE(t.field_observed, FALSE) = FALSE", completed_sql)
        self.assertIn(
            'EXISTS (SELECT 1 FROM "crm"."tasks_field" s WHERE s.task_key = t.key) OR',
            completed_sql,
        )

        lock_sql = cursor.execute.call_args_list[1].args[0]
        self.assertIn("COALESCE(a.pre_analise, FALSE) = FALSE", lock_sql)
        self.assertIn("pre_analise_started_by = NULL", lock_sql)
        self.assertIn("Europe/Moscow", lock_sql)
        self.assertIn("07:00:00", lock_sql)
        self.assertNotIn("field_observed", lock_sql)
        self.assertNotIn("user_created", lock_sql)

        conn.commit.assert_called_once()


class StartAreaPreAnaliseAfterDailyResetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = str(uuid.uuid4())
        self.now_msk = datetime.now(MSK)

    def test_yesterday_lock_allows_other_user_after_clear(self) -> None:
        from app.crm.tasks_area import start_area_pre_analise

        update_cursor = MagicMock()
        update_cursor.fetchone.return_value = (self.key,)
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(update_cursor)

        with (
            patch("app.crm.tasks_area.ensure_tasks_area_audit_columns", return_value=True),
            patch("app.crm.tasks_area.ensure_pre_analise_audit_columns", return_value=True),
            patch("app.crm.tasks_area.clear_stale_pre_analise_locks", return_value=1) as clear_mock,
            patch(
                "app.crm.tasks_area._fetch_pre_analise_state",
                return_value={
                    "pre_analise": False,
                    "pre_analise_started_by": None,
                    "pre_analise_started_at": None,
                    "pre_analise_paused_by": None,
                    "pre_analise_paused_at": None,
                },
            ),
            patch("app.crm.tasks_area.make_user_audit", return_value=["OtherUser", "ts"]),
        ):
            result = start_area_pre_analise(conn, self.key, "OtherUser")

        self.assertEqual(result, "updated")
        clear_mock.assert_called_once_with(conn)
        update_sql = update_cursor.execute.call_args.args[0]
        self.assertIn("pre_analise_started_by = %s", update_sql)
        self.assertEqual(update_cursor.execute.call_args.args[1][0], "OtherUser")

    def test_same_day_lock_still_conflicts_for_other_user(self) -> None:
        from app.crm.tasks_area import start_area_pre_analise

        started_at = self.now_msk.replace(hour=10, minute=0, second=0, microsecond=0)
        if started_at > self.now_msk:
            started_at = self.now_msk - timedelta(hours=1)

        conn = MagicMock()

        with (
            patch("app.crm.tasks_area.ensure_tasks_area_audit_columns", return_value=True),
            patch("app.crm.tasks_area.ensure_pre_analise_audit_columns", return_value=True),
            patch("app.crm.tasks_area.clear_stale_pre_analise_locks", return_value=0) as clear_mock,
            patch(
                "app.crm.tasks_area._fetch_pre_analise_state",
                return_value={
                    "pre_analise": False,
                    "pre_analise_started_by": "SkachkovNA",
                    "pre_analise_started_at": started_at.astimezone(timezone.utc),
                    "pre_analise_paused_by": None,
                    "pre_analise_paused_at": None,
                },
            ),
        ):
            result = start_area_pre_analise(conn, self.key, "OtherUser")

        self.assertEqual(result, "conflict")
        clear_mock.assert_called_once_with(conn)

    def test_same_day_completed_pre_analise_not_reclaimed(self) -> None:
        from app.crm.tasks_area import start_area_pre_analise

        conn = MagicMock()

        with (
            patch("app.crm.tasks_area.ensure_tasks_area_audit_columns", return_value=True),
            patch("app.crm.tasks_area.ensure_pre_analise_audit_columns", return_value=True),
            patch("app.crm.tasks_area.clear_stale_pre_analise_locks", return_value=0),
            patch(
                "app.crm.tasks_area._fetch_pre_analise_state",
                return_value={
                    "pre_analise": True,
                    "pre_analise_started_by": "SkachkovNA",
                    "pre_analise_started_at": self.now_msk - timedelta(hours=2),
                    "pre_analise_paused_by": None,
                    "pre_analise_paused_at": None,
                },
            ),
        ):
            result = start_area_pre_analise(conn, self.key, "OtherUser")

        self.assertEqual(result, "skipped")


class FetchTasksAreaSurvivesResetFailureTests(unittest.TestCase):
    def test_geojson_loads_when_reset_raises(self) -> None:
        from app.crm.tasks_area import fetch_tasks_area_geojson

        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "geojson": {"type": "FeatureCollection", "features": []}
        }
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        with patch(
            "app.crm.tasks_area.clear_stale_analise_locks",
            side_effect=Exception("column f.geom does not exist"),
        ):
            result = fetch_tasks_area_geojson(conn)

        self.assertEqual(result["type"], "FeatureCollection")
        conn.rollback.assert_called()


class AnaliseResetCutoffTests(unittest.TestCase):
    def test_moscow_reset_at_uses_seven_am(self) -> None:
        from app.crm.tasks_area import ANALISE_RESET_HOUR, _moscow_reset_at_sql

        self.assertEqual(ANALISE_RESET_HOUR, 7)
        sql = _moscow_reset_at_sql()
        self.assertIn("07:00:00", sql)
        self.assertIn("Europe/Moscow", sql)

    def test_seconds_until_next_analise_reset_is_positive(self) -> None:
        from app.crm.delay_scheduler import _seconds_until_next_moscow_analise_reset

        delay = _seconds_until_next_moscow_analise_reset()
        self.assertGreater(delay, 0)
        self.assertLessEqual(delay, 24 * 3600 + 1)


if __name__ == "__main__":
    unittest.main()
