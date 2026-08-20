"""Tests for TaskRecord row parsing after extra TASK_ID_COLUMNS."""

from __future__ import annotations

import unittest

from app.crm.store import TASK_ID_COLUMNS, TaskRecord, _TASK_SELECT_COLUMNS


class TaskRecordFromRowTests(unittest.TestCase):
    def test_from_row_keeps_photo_uuid_and_sps_after_dit_column(self) -> None:
        self.assertIn("dit_result_id", TASK_ID_COLUMNS)
        values = {col: None for col in _TASK_SELECT_COLUMNS}
        values["key"] = "task-1"
        values["type"] = "Разрытия"
        values["photo_uuid"] = "uuid-1"
        values["dit_result_id"] = "dit-9"
        values["sps"] = "SPS-1"
        values["field_observed"] = True
        values["user_created"] = ["alice", "2024-01-01"]
        row = tuple(values[col] for col in _TASK_SELECT_COLUMNS)

        record = TaskRecord.from_row(row)
        self.assertEqual(record.key, "task-1")
        self.assertEqual(record.photo_uuid, "uuid-1")
        self.assertEqual(record.dit_result_id, "dit-9")
        self.assertEqual(record.sps, "SPS-1")
        self.assertTrue(record.field_observed)
        self.assertEqual(record.user_created, ["alice", "2024-01-01"])
        self.assertIsNone(record.ogh_id)


class BackfillDitPhotoTasksTests(unittest.TestCase):
    def test_inserts_all_rows_without_district_filter(self) -> None:
        from unittest.mock import MagicMock

        from app.crm.etl_photo_loader import DIT_PHOTO_SUBGROUP
        from app.crm.store import CRM_GROUP_DISRUPTIONS, backfill_source_layer_tasks

        layer = MagicMock()
        layer.geometry_column = "geom"
        layer.primary_key = "result_id"
        layer.qualified_table = '"dit_detect"."ai_results"'
        layer.sql_filter = None
        layer.geometry_type = "point"

        cur = MagicMock()
        cur.rowcount = 12
        cm = MagicMock()
        cm.__enter__.return_value = cur
        cm.__exit__.return_value = False
        conn = MagicMock()
        conn.cursor.return_value = cm

        store_cfg = {
            "schema": "crm",
            "table": "tasks",
            "subgroups": {
                DIT_PHOTO_SUBGROUP: {
                    "task_column": "dit_result_id",
                    "source_field": "result_id",
                }
            },
        }
        inserted = backfill_source_layer_tasks(
            conn,
            CRM_GROUP_DISRUPTIONS,
            DIT_PHOTO_SUBGROUP,
            layer,
            store_cfg,
            "dit-backfill",
        )
        self.assertEqual(inserted, 12)
        sql = cur.execute.call_args[0][0]
        self.assertIn('"dit_detect"."ai_results"', sql)
        self.assertIn("dit_result_id", sql)
        self.assertIn("ON CONFLICT", sql)
        self.assertNotIn("ST_", sql)


if __name__ == "__main__":
    unittest.main()
