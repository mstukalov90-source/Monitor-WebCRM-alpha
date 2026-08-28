"""Tests for office «my closed tasks» list and snapshot relocate."""

from __future__ import annotations

import unittest
from datetime import timedelta
from unittest.mock import MagicMock, patch

from app.crm.my_closed_tasks import fetch_my_closed_tasks
from app.crm.store import (
    OrderAnaliseCompleteError,
    TaskRecord,
    moscow_today,
    relocate_task_snapshot,
)


def _cursor_cm(cursor: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value = cursor
    cm.__exit__.return_value = False
    return cm


class FetchMyClosedTasksTests(unittest.TestCase):
    def test_filters_by_login_and_builds_name_without_key(self) -> None:
        key = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        record = TaskRecord(
            key=key,
            type="oati",
            oati_id="OATI-1",
            is_office_task=False,
            is_field_data=False,
        )
        snapshot_rows = [
            {
                "task_key": key,
                "task_source": "done_legal",
                "rayon": "Тверской",
                "type": "oati",
            }
        ]

        conn = MagicMock()
        with (
            patch(
                "app.crm.my_closed_tasks._fetch_closed_snapshot_rows",
                return_value=snapshot_rows,
            ),
            patch(
                "app.crm.my_closed_tasks.fetch_tasks_by_keys",
                return_value={key: record},
            ),
            patch(
                "app.crm.my_closed_tasks.fetch_can_return_map",
                return_value={key: True},
            ),
            patch(
                "app.crm.my_closed_tasks._find_subgroup_for_record",
                return_value=("ОАТИ", "oati_id", "OATI-1"),
            ),
        ):
            items = fetch_my_closed_tasks(conn, {}, "office1")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["task_key"], key)
        self.assertEqual(items[0]["rayon"], "Тверской")
        self.assertEqual(items[0]["task_name"], "ОАТИ")
        self.assertEqual(items[0]["task_source"], "done_legal")
        self.assertTrue(items[0]["can_return_to_active"])
        self.assertNotIn(key, items[0]["task_name"])

    def test_can_return_false_when_analise_done(self) -> None:
        key = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        snapshot_rows = [
            {
                "task_key": key,
                "task_source": "clear",
                "rayon": "Арбат",
                "type": "office",
            }
        ]
        record = TaskRecord(key=key, type="office", is_office_task=True)

        conn = MagicMock()
        with (
            patch(
                "app.crm.my_closed_tasks._fetch_closed_snapshot_rows",
                return_value=snapshot_rows,
            ),
            patch(
                "app.crm.my_closed_tasks.fetch_tasks_by_keys",
                return_value={key: record},
            ),
            patch(
                "app.crm.my_closed_tasks.fetch_can_return_map",
                return_value={key: False},
            ),
        ):
            items = fetch_my_closed_tasks(conn, {}, "office1")

        self.assertEqual(items[0]["task_name"], "Задачи из камерального анализа")
        self.assertFalse(items[0]["can_return_to_active"])

    def test_snapshot_query_filters_login_on_audit_columns(self) -> None:
        from app.crm.my_closed_tasks import _fetch_closed_snapshot_rows

        cursor = MagicMock()
        cursor.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        with patch("app.crm.my_closed_tasks.ensure_rayon_column", return_value=True):
            rows = _fetch_closed_snapshot_rows(conn, {}, "office1")

        self.assertEqual(rows, [])
        self.assertGreaterEqual(cursor.execute.call_count, 3)
        sql = cursor.execute.call_args_list[0].args[0]
        params = cursor.execute.call_args_list[0].args[1]
        self.assertIn("user_last_edit[1]", sql)
        self.assertIn("user_created[1]", sql)
        self.assertEqual(params, ("office1", "office1"))
        self.assertNotIn("tasks_delay", sql)


class FetchCanReturnMapTests(unittest.TestCase):
    def test_query_uses_area_analise_and_contains(self) -> None:
        from app.crm.my_closed_tasks import fetch_can_return_map

        cursor = MagicMock()
        cursor.fetchall.return_value = [
            {"task_key": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "can_return": True},
        ]
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        with patch(
            "app.crm.tasks_area._task_geom_union_sql",
            return_value="SELECT NULL::uuid AS task_key, NULL::geometry AS geom WHERE FALSE",
        ):
            mapping = fetch_can_return_map(
                conn, {}, ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]
            )

        self.assertTrue(mapping["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"])
        sql = cursor.execute.call_args.args[0]
        self.assertIn("COALESCE(a.analise, FALSE) = FALSE", sql)
        self.assertIn("ST_Contains", sql)
        self.assertIn("crm.tasks_area", sql)


class RelocateTaskSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = TaskRecord(
            key="cccccccc-cccc-cccc-cccc-cccccccccccc",
            type="oati",
            field_observed=True,
        )
        self.store_cfg = {"schema": "crm"}

    def test_relocate_removes_old_closed_snapshot(self) -> None:
        conn = MagicMock()
        with (
            patch(
                "app.crm.store.detect_task_workflow_status",
                return_value="done_illegal",
            ),
            patch(
                "app.crm.store.fetch_snapshot_rayon_for_status",
                return_value="Тверской",
            ) as rayon_mock,
            patch(
                "app.crm.store.remove_task_from_workflow_snapshot",
                return_value="deleted",
            ) as remove_mock,
            patch(
                "app.crm.store.send_task_to_done_legal",
                return_value="inserted",
            ) as send_mock,
        ):
            status = relocate_task_snapshot(
                conn,
                self.record,
                self.store_cfg,
                "office1",
                "done_legal",
            )

        self.assertEqual(status, "inserted")
        remove_mock.assert_called_once()
        self.assertEqual(remove_mock.call_args.args[4], "done_illegal")
        send_mock.assert_called_once()
        self.assertEqual(send_mock.call_args.kwargs.get("rayon"), "Тверской")
        rayon_mock.assert_called_once()

    def test_return_to_active_forbidden_when_analise_done(self) -> None:
        conn = MagicMock()
        with (
            patch(
                "app.crm.store.detect_task_workflow_status",
                return_value="done_legal",
            ),
            patch(
                "app.crm.my_closed_tasks.containing_order_allows_return",
                return_value=False,
            ),
            patch("app.crm.store.remove_task_from_workflow_snapshot") as remove_mock,
        ):
            with self.assertRaises(OrderAnaliseCompleteError):
                relocate_task_snapshot(
                    conn,
                    self.record,
                    self.store_cfg,
                    "office1",
                    "active",
                )
        remove_mock.assert_not_called()

    def test_return_to_active_from_clear_when_analise_open(self) -> None:
        conn = MagicMock()
        with (
            patch(
                "app.crm.store.detect_task_workflow_status",
                return_value="clear",
            ),
            patch(
                "app.crm.my_closed_tasks.containing_order_allows_return",
                return_value=True,
            ),
            patch(
                "app.crm.store.remove_task_from_workflow_snapshot",
                return_value="deleted",
            ) as remove_mock,
        ):
            status = relocate_task_snapshot(
                conn,
                self.record,
                self.store_cfg,
                "office1",
                "active",
            )

        self.assertEqual(status, "deleted")
        self.assertEqual(remove_mock.call_args.args[4], "clear")

    def test_postpone_from_closed_removes_then_inserts_delay(self) -> None:
        conn = MagicMock()
        delay_until = moscow_today() + timedelta(days=2)
        with (
            patch(
                "app.crm.store.detect_task_workflow_status",
                return_value="done_legal",
            ),
            patch(
                "app.crm.store.fetch_snapshot_rayon_for_status",
                return_value="Арбат",
            ),
            patch(
                "app.crm.store.remove_task_from_workflow_snapshot",
                return_value="deleted",
            ) as remove_mock,
            patch(
                "app.crm.store.send_task_snapshot",
                return_value="inserted",
            ) as send_mock,
        ):
            status = relocate_task_snapshot(
                conn,
                self.record,
                self.store_cfg,
                "office1",
                "delay",
                delay_until=delay_until,
            )

        self.assertEqual(status, "inserted")
        remove_mock.assert_called_once()
        send_mock.assert_called_once()
        self.assertEqual(send_mock.call_args.args[3], "delay_table")
        self.assertEqual(send_mock.call_args.args[4], "tasks_delay")
        self.assertEqual(send_mock.call_args.kwargs.get("delay_until"), delay_until)

    def test_same_target_is_skipped(self) -> None:
        conn = MagicMock()
        with patch(
            "app.crm.store.detect_task_workflow_status",
            return_value="done_legal",
        ):
            status = relocate_task_snapshot(
                conn,
                self.record,
                self.store_cfg,
                "office1",
                "done_legal",
            )
        self.assertEqual(status, "skipped")


if __name__ == "__main__":
    unittest.main()
