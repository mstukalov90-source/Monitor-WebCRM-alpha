"""Tests for GenPlan camera task blocks."""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from app.crm.camera_blocks import (
    ENSURE_STATEMENTS,
    apply_camera_block,
    is_camera_block_active,
    next_quarter_start,
    resolve_cam_id,
    resolve_order_end_date,
    should_skip_photo_task_insert,
)
from app.crm.store import TaskRecord


def _cursor_cm(cursor: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value = cursor
    cm.__exit__.return_value = False
    return cm


class NextQuarterStartTests(unittest.TestCase):
    def test_august_goes_to_october(self) -> None:
        self.assertEqual(next_quarter_start(date(2026, 8, 21)), date(2026, 10, 1))

    def test_quarter_boundaries(self) -> None:
        self.assertEqual(next_quarter_start(date(2026, 1, 1)), date(2026, 4, 1))
        self.assertEqual(next_quarter_start(date(2026, 3, 31)), date(2026, 4, 1))
        self.assertEqual(next_quarter_start(date(2026, 4, 1)), date(2026, 7, 1))
        self.assertEqual(next_quarter_start(date(2026, 9, 30)), date(2026, 10, 1))
        self.assertEqual(next_quarter_start(date(2026, 10, 1)), date(2027, 1, 1))
        self.assertEqual(next_quarter_start(date(2026, 12, 31)), date(2027, 1, 1))


class CameraIsBlockedTests(unittest.TestCase):
    today = date(2026, 8, 21)

    def test_until_field_observed(self) -> None:
        self.assertTrue(
            is_camera_block_active(
                mode="until_field_observed",
                until_date=None,
                task_field_observed=False,
                today=self.today,
            )
        )
        self.assertTrue(
            is_camera_block_active(
                mode="until_field_observed",
                until_date=None,
                task_field_observed=None,
                today=self.today,
            )
        )
        self.assertFalse(
            is_camera_block_active(
                mode="until_field_observed",
                until_date=None,
                task_field_observed=True,
                today=self.today,
            )
        )
        self.assertTrue(
            is_camera_block_active(
                mode="until_field_observed",
                until_date=None,
                task_field_observed=True,
                today=self.today,
                has_task_key=False,
            )
        )

    def test_until_quarter(self) -> None:
        until = date(2026, 10, 1)
        self.assertTrue(
            is_camera_block_active(
                mode="until_quarter",
                until_date=until,
                task_field_observed=None,
                today=self.today,
            )
        )
        self.assertFalse(
            is_camera_block_active(
                mode="until_quarter",
                until_date=until,
                task_field_observed=None,
                today=date(2026, 10, 1),
            )
        )

    def test_until_date_inclusive(self) -> None:
        until = date(2026, 8, 25)
        self.assertTrue(
            is_camera_block_active(
                mode="until_date",
                until_date=until,
                task_field_observed=None,
                today=until,
            )
        )
        self.assertFalse(
            is_camera_block_active(
                mode="until_date",
                until_date=until,
                task_field_observed=None,
                today=date(2026, 8, 26),
            )
        )

    def test_until_order_end_inclusive(self) -> None:
        until = date(2026, 9, 1)
        self.assertTrue(
            is_camera_block_active(
                mode="until_order_end",
                until_date=until,
                task_field_observed=None,
                today=until,
            )
        )
        self.assertFalse(
            is_camera_block_active(
                mode="until_order_end",
                until_date=until,
                task_field_observed=None,
                today=date(2026, 9, 2),
            )
        )


class SkipInsertTests(unittest.TestCase):
    def test_skip_only_when_cam_blocked(self) -> None:
        self.assertFalse(should_skip_photo_task_insert(None, "cam-1", True))
        self.assertFalse(should_skip_photo_task_insert("uuid-1", None, True))
        self.assertFalse(should_skip_photo_task_insert("uuid-1", "cam-1", False))
        self.assertTrue(should_skip_photo_task_insert("uuid-1", "cam-1", True))

    def test_sql_trigger_returns_null(self) -> None:
        ddl = "\n".join(ENSURE_STATEMENTS)
        self.assertIn("RETURN NULL", ddl)
        self.assertIn("crm.camera_is_blocked", ddl)
        self.assertIn("BEFORE INSERT ON crm.tasks", ddl)
        self.assertIn("field_observed", ddl)


class ResolveCamIdTests(unittest.TestCase):
    def test_empty_uuid(self) -> None:
        self.assertIsNone(resolve_cam_id(MagicMock(), None))
        self.assertIsNone(resolve_cam_id(MagicMock(), "  "))

    def test_reads_cam_id(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = ("42",)
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)
        self.assertEqual(resolve_cam_id(conn, "photo-uuid"), "42")
        sql = cursor.execute.call_args[0][0]
        self.assertIn("genplan.photo_meta", sql)
        self.assertIn("cam_id", sql)


class ResolveOrderEndDateTests(unittest.TestCase):
    def _record(self, **kwargs) -> TaskRecord:
        values = {"key": "task-1", "type": "Разрытия"}
        values.update(kwargs)
        return TaskRecord(**values)

    def test_no_order_ids(self) -> None:
        self.assertIsNone(
            resolve_order_end_date(MagicMock(), self._record(), {}, MagicMock())
        )

    def test_localwork_id_alone_is_ignored(self) -> None:
        self.assertIsNone(
            resolve_order_end_date(
                MagicMock(),
                self._record(localwork_id="lw-1"),
                {},
                MagicMock(),
            )
        )

    @patch("app.crm.link_resolver.resolve_linked_features")
    def test_max_work_end_date(self, resolve_linked: MagicMock) -> None:
        resolve_linked.return_value = (
            [
                {
                    "link_column": "oati_id",
                    "attributes": {"work_end_date": "2026-08-10"},
                },
                {
                    "link_column": "earthwork_id",
                    "attributes": {"work_end_date": "15.09.2026"},
                },
                {
                    "link_column": "localwork_id",
                    "attributes": {"work_end_date": "2026-12-01"},
                },
            ],
            [],
        )
        got = resolve_order_end_date(
            MagicMock(),
            self._record(oati_id="o-1", earthwork_id="e-1"),
            {},
            MagicMock(),
        )
        self.assertEqual(got, date(2026, 9, 15))

    @patch("app.crm.link_resolver.resolve_linked_features")
    def test_bad_date_is_null(self, resolve_linked: MagicMock) -> None:
        resolve_linked.return_value = (
            [{"link_column": "avr_mos_id", "attributes": {"work_end_date": "soon"}}],
            [],
        )
        got = resolve_order_end_date(
            MagicMock(),
            self._record(avr_mos_id="avr-1"),
            {},
            MagicMock(),
        )
        self.assertIsNone(got)


class ApplyCameraBlockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = TaskRecord(key="task-1", type="Разрытия", photo_uuid="photo-1")
        self.conn = MagicMock()

    @patch("app.crm.camera_blocks.resolve_cam_id", return_value=None)
    def test_missing_cam_id(self, _resolve_cam: MagicMock) -> None:
        with self.assertRaisesRegex(ValueError, "камеры"):
            apply_camera_block(
                self.conn,
                self.record,
                mode="until_quarter",
                until_date=None,
                login="alice",
                store_cfg={},
                registry=MagicMock(),
            )

    @patch("app.crm.camera_blocks.upsert_camera_block")
    @patch("app.crm.camera_blocks.moscow_today", return_value=date(2026, 8, 21))
    @patch("app.crm.camera_blocks.resolve_cam_id", return_value="cam-9")
    def test_quarter_uses_next_quarter_start(
        self,
        _resolve_cam: MagicMock,
        _today: MagicMock,
        upsert: MagicMock,
    ) -> None:
        upsert.return_value = {
            "cam_id": "cam-9",
            "mode": "until_quarter",
            "until_date": date(2026, 10, 1),
            "task_key": None,
        }
        apply_camera_block(
            self.conn,
            self.record,
            mode="until_quarter",
            until_date=None,
            login="alice",
            store_cfg={},
            registry=MagicMock(),
        )
        kwargs = upsert.call_args.kwargs
        self.assertEqual(kwargs["until_date"], date(2026, 10, 1))
        self.assertIsNone(kwargs["task_key"])

    @patch("app.crm.camera_blocks.upsert_camera_block")
    @patch("app.crm.camera_blocks.moscow_today", return_value=date(2026, 8, 21))
    @patch("app.crm.camera_blocks.resolve_cam_id", return_value="cam-9")
    def test_until_date_rejects_today(
        self,
        _resolve_cam: MagicMock,
        _today: MagicMock,
        upsert: MagicMock,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "позже"):
            apply_camera_block(
                self.conn,
                self.record,
                mode="until_date",
                until_date=date(2026, 8, 21),
                login="alice",
                store_cfg={},
                registry=MagicMock(),
            )
        upsert.assert_not_called()

    @patch("app.crm.camera_blocks.resolve_order_end_date", return_value=None)
    @patch("app.crm.camera_blocks.moscow_today", return_value=date(2026, 8, 21))
    @patch("app.crm.camera_blocks.resolve_cam_id", return_value="cam-9")
    def test_order_end_requires_date(
        self,
        _resolve_cam: MagicMock,
        _today: MagicMock,
        _order: MagicMock,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "ордера"):
            apply_camera_block(
                self.conn,
                self.record,
                mode="until_order_end",
                until_date=None,
                login="alice",
                store_cfg={},
                registry=MagicMock(),
            )


if __name__ == "__main__":
    unittest.main()
