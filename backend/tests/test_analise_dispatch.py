"""Tests for manager analise dispatch (start/complete as office user)."""

from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from app.crm.tasks_area import (
    AnaliseDispatchError,
    _analise_eligible_tasks_count_sql,
    complete_area_analise_as,
    dispatch_area_analise,
    fetch_analise_dispatch_context,
    start_area_analise,
)

MSK = ZoneInfo("Europe/Moscow")


def _cursor_cm(cursor: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value = cursor
    cm.__exit__.return_value = False
    return cm


class AnaliseEligibleTasksSqlTests(unittest.TestCase):
    def test_count_sql_matches_office_analise_criteria(self) -> None:
        sql = _analise_eligible_tasks_count_sql()
        self.assertIn("t.field_observed IS TRUE", sql)
        self.assertIn("NOT EXISTS", sql)
        self.assertIn('"crm"."tasks_field"', sql)
        self.assertIn("ST_Intersects", sql)
        self.assertIn("office_task_points", sql)
        self.assertNotIn("user_created", sql)


class FetchAnaliseDispatchContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = str(uuid.uuid4())

    def test_context_with_tasks_idle(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "order_key": self.key,
            "task_number": "42",
            "rayon": "Сокол",
            "analise": False,
            "analise_started_by": None,
            "analise_started_at": None,
            "analise_paused_at": None,
            "task_count": 3,
        }
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        with (
            patch("app.crm.tasks_area.ensure_analise_audit_columns", return_value=True),
            patch("app.crm.tasks_area.analise_lock_holder", return_value=None),
            patch(
                "app.crm.personnel.list_office_users",
                return_value=[{"login": "office1", "name": "Office One"}],
            ),
        ):
            ctx = fetch_analise_dispatch_context(conn, self.key)

        self.assertIsNotNone(ctx)
        assert ctx is not None
        sql = cursor.execute.call_args.args[0]
        self.assertIn("t.field_observed IS TRUE", sql)
        self.assertNotIn("user_created", sql)
        self.assertTrue(ctx["has_analise_tasks"])
        self.assertEqual(ctx["task_count"], 3)
        self.assertEqual(ctx["workflow"], "idle")
        self.assertEqual(ctx["task_number"], "42")
        self.assertEqual(ctx["office_users"][0]["login"], "office1")

    def test_context_without_tasks(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "order_key": self.key,
            "task_number": "7",
            "rayon": "Сокол",
            "analise": False,
            "analise_started_by": None,
            "analise_started_at": None,
            "analise_paused_at": None,
            "task_count": 0,
        }
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        with (
            patch("app.crm.tasks_area.ensure_analise_audit_columns", return_value=True),
            patch("app.crm.tasks_area.analise_lock_holder", return_value=None),
            patch("app.crm.personnel.list_office_users", return_value=[]),
        ):
            ctx = fetch_analise_dispatch_context(conn, self.key)

        assert ctx is not None
        self.assertFalse(ctx["has_analise_tasks"])
        self.assertEqual(ctx["task_count"], 0)
        self.assertEqual(ctx["workflow"], "idle")


class StartAreaAnaliseDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = str(uuid.uuid4())
        self.now_msk = datetime.now(MSK)

    def test_start_sets_lock_on_office_login_and_audit_actor(self) -> None:
        update_cursor = MagicMock()
        update_cursor.fetchone.return_value = (self.key,)
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(update_cursor)
        audit = ["Manager", "ts"]

        with (
            patch("app.crm.tasks_area.ensure_tasks_area_audit_columns", return_value=True),
            patch("app.crm.tasks_area.ensure_analise_audit_columns", return_value=True),
            patch("app.crm.tasks_area.clear_stale_analise_locks", return_value=0),
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
            patch("app.crm.tasks_area.make_user_audit", return_value=audit) as audit_mock,
        ):
            result = start_area_analise(
                conn, self.key, "OfficeUser", actor_login="Manager"
            )

        self.assertEqual(result, "updated")
        audit_mock.assert_called_once_with("Manager")
        params = update_cursor.execute.call_args.args[1]
        self.assertEqual(params[0], "OfficeUser")
        self.assertEqual(params[1], audit)

    def test_force_reassigns_other_users_lock(self) -> None:
        started_at = self.now_msk.replace(hour=10, minute=0, second=0, microsecond=0)
        if started_at > self.now_msk:
            started_at = self.now_msk - timedelta(hours=1)
        update_cursor = MagicMock()
        update_cursor.fetchone.return_value = (self.key,)
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(update_cursor)

        with (
            patch("app.crm.tasks_area.ensure_tasks_area_audit_columns", return_value=True),
            patch("app.crm.tasks_area.ensure_analise_audit_columns", return_value=True),
            patch("app.crm.tasks_area.clear_stale_analise_locks", return_value=0),
            patch(
                "app.crm.tasks_area._fetch_analise_state",
                return_value={
                    "analise": False,
                    "analise_started_by": "OtherOffice",
                    "analise_started_at": started_at.astimezone(timezone.utc),
                    "analise_paused_by": None,
                    "analise_paused_at": None,
                },
            ),
            patch("app.crm.tasks_area.make_user_audit", return_value=["Manager", "ts"]),
        ):
            result = start_area_analise(
                conn, self.key, "OfficeUser", actor_login="Manager", force=True
            )

        self.assertEqual(result, "updated")
        sql = update_cursor.execute.call_args.args[0]
        self.assertIn("analise_started_by = %s", sql)
        self.assertNotIn("analise_started_at IS NULL", sql)
        self.assertEqual(update_cursor.execute.call_args.args[1][0], "OfficeUser")

    def test_without_force_still_conflicts_for_other_user(self) -> None:
        started_at = self.now_msk.replace(hour=10, minute=0, second=0, microsecond=0)
        if started_at > self.now_msk:
            started_at = self.now_msk - timedelta(hours=1)
        conn = MagicMock()

        with (
            patch("app.crm.tasks_area.ensure_tasks_area_audit_columns", return_value=True),
            patch("app.crm.tasks_area.ensure_analise_audit_columns", return_value=True),
            patch("app.crm.tasks_area.clear_stale_analise_locks", return_value=0),
            patch(
                "app.crm.tasks_area._fetch_analise_state",
                return_value={
                    "analise": False,
                    "analise_started_by": "OtherOffice",
                    "analise_started_at": started_at.astimezone(timezone.utc),
                    "analise_paused_by": None,
                    "analise_paused_at": None,
                },
            ),
        ):
            result = start_area_analise(conn, self.key, "OfficeUser")

        self.assertEqual(result, "conflict")


class CompleteAreaAnaliseAsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = str(uuid.uuid4())

    def test_complete_sets_analise_and_finished_by_assignee(self) -> None:
        update_cursor = MagicMock()
        update_cursor.fetchone.return_value = (self.key,)
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(update_cursor)
        audit = ["Manager", "ts"]

        with (
            patch("app.crm.tasks_area.ensure_tasks_area_audit_columns", return_value=True),
            patch("app.crm.tasks_area.ensure_analise_audit_columns", return_value=True),
            patch("app.crm.tasks_area.make_user_audit", return_value=audit) as audit_mock,
        ):
            result = complete_area_analise_as(conn, self.key, "OfficeUser", "Manager")

        self.assertEqual(result, "updated")
        audit_mock.assert_called_once_with("Manager")
        sql = update_cursor.execute.call_args.args[0]
        self.assertIn("analise = TRUE", sql)
        self.assertIn("analise_finished_by = %s", sql)
        self.assertIn("COALESCE(analise_started_at, NOW())", sql)
        params = update_cursor.execute.call_args.args[1]
        self.assertEqual(params[0], "OfficeUser")
        self.assertEqual(params[1], "OfficeUser")
        self.assertEqual(params[2], audit)


class DispatchAreaAnaliseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = str(uuid.uuid4())
        self.conn = MagicMock()

    def test_start_when_tasks_exist(self) -> None:
        with (
            patch("app.crm.personnel.get_user_role_by_login", return_value="office"),
            patch(
                "app.crm.tasks_area.fetch_analise_dispatch_context",
                return_value={"workflow": "idle", "has_analise_tasks": True},
            ),
            patch(
                "app.crm.tasks_area.start_area_analise", return_value="updated"
            ) as start_mock,
        ):
            result = dispatch_area_analise(
                self.conn,
                self.key,
                assignee_login="office1",
                mode="start",
                actor_login="manager1",
            )

        self.assertEqual(result, "updated")
        start_mock.assert_called_once_with(
            self.conn,
            self.key,
            "office1",
            actor_login="manager1",
            force=True,
        )

    def test_complete_when_no_tasks(self) -> None:
        with (
            patch("app.crm.personnel.get_user_role_by_login", return_value="office"),
            patch(
                "app.crm.tasks_area.fetch_analise_dispatch_context",
                return_value={"workflow": "idle", "has_analise_tasks": False},
            ),
            patch(
                "app.crm.tasks_area.complete_area_analise_as", return_value="updated"
            ) as complete_mock,
        ):
            result = dispatch_area_analise(
                self.conn,
                self.key,
                assignee_login="office1",
                mode="complete",
                actor_login="manager1",
            )

        self.assertEqual(result, "updated")
        complete_mock.assert_called_once_with(
            self.conn, self.key, "office1", "manager1"
        )

    def test_rejects_non_office_role(self) -> None:
        with patch("app.crm.personnel.get_user_role_by_login", return_value="field"):
            with self.assertRaises(AnaliseDispatchError) as ctx:
                dispatch_area_analise(
                    self.conn,
                    self.key,
                    assignee_login="field1",
                    mode="start",
                    actor_login="manager1",
                )
        self.assertIn("office", str(ctx.exception))

    def test_rejects_start_when_no_tasks(self) -> None:
        with (
            patch("app.crm.personnel.get_user_role_by_login", return_value="office"),
            patch(
                "app.crm.tasks_area.fetch_analise_dispatch_context",
                return_value={"workflow": "idle", "has_analise_tasks": False},
            ),
        ):
            with self.assertRaises(AnaliseDispatchError) as ctx:
                dispatch_area_analise(
                    self.conn,
                    self.key,
                    assignee_login="office1",
                    mode="start",
                    actor_login="manager1",
                )
        self.assertIn("Нет задач", str(ctx.exception))

    def test_rejects_complete_when_tasks_exist(self) -> None:
        with (
            patch("app.crm.personnel.get_user_role_by_login", return_value="office"),
            patch(
                "app.crm.tasks_area.fetch_analise_dispatch_context",
                return_value={"workflow": "idle", "has_analise_tasks": True},
            ),
        ):
            with self.assertRaises(AnaliseDispatchError) as ctx:
                dispatch_area_analise(
                    self.conn,
                    self.key,
                    assignee_login="office1",
                    mode="complete",
                    actor_login="manager1",
                )
        self.assertIn("есть задачи", str(ctx.exception).lower())

    def test_empty_assignee(self) -> None:
        with self.assertRaises(AnaliseDispatchError):
            dispatch_area_analise(
                self.conn,
                self.key,
                assignee_login="  ",
                mode="start",
                actor_login="manager1",
            )

    def test_already_done_skipped(self) -> None:
        with (
            patch("app.crm.personnel.get_user_role_by_login", return_value="office"),
            patch(
                "app.crm.tasks_area.fetch_analise_dispatch_context",
                return_value={"workflow": "done", "has_analise_tasks": False},
            ),
        ):
            result = dispatch_area_analise(
                self.conn,
                self.key,
                assignee_login="office1",
                mode="complete",
                actor_login="manager1",
            )
        self.assertEqual(result, "skipped")


if __name__ == "__main__":
    unittest.main()
