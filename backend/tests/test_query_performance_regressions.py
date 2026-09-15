"""Regression tests for bounded, read-only task loading SQL."""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from app.crm.collector import (
    CollectLayerPlanItem,
    CollectQueryContext,
    TaskGroup,
    TaskResult,
    TaskSubgroup,
    collect_tasks,
)
from app.crm.snapshot_loader import SnapshotRow, _batch_layer_snaps_in_district
from app.crm.store import TaskRecord
from app.layers.geojson import (
    _source_table_names,
    fetch_features_by_source_anchors,
    fetch_task_attributes_in_district,
)
from app.layers.registry import LayerDef


def _cursor_cm(cursor: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value = cursor
    cm.__exit__.return_value = False
    return cm


class ActiveTaskSqlTests(unittest.TestCase):
    def test_snapshot_exclusions_are_pushed_into_layer_query(self) -> None:
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)
        layer = LayerDef(
            layer_key="orders",
            display_name="Orders",
            schema="data_mos",
            table_name="items_1_points",
            geometry_column="geom",
            geometry_type="point",
            symbology={},
        )

        fetch_task_attributes_in_district(
            conn,
            layer,
            "id",
            "oati_id",
            "crm",
            "tasks",
            "POLYGON()",
            excluded_task_tables=(("crm", "tasks_field"), ("crm", "tasks_clear")),
        )

        sql = cursor.execute.call_args.args[0]
        self.assertEqual(sql.count("NOT EXISTS"), 4)
        self.assertIn('snap.task_key = ct.key', sql)
        self.assertIn("ON ct.key = t.task_key", sql)
        self.assertIn("t.task_key IS NULL", sql)
        self.assertNotIn("SELECT task_key FROM", sql)

    def test_source_table_normalizes_scalar_and_text_array(self) -> None:
        self.assertEqual(
            _source_table_names(["data_mos.items_1_points", "lens.reports"]),
            ("data_mos.items_1_points", "lens.reports"),
        )
        self.assertEqual(
            _source_table_names("{data_mos.items_1_points,lens.reports}"),
            ("data_mos.items_1_points", "lens.reports"),
        )
        self.assertEqual(
            _source_table_names("genplan.photo_meta"), ("genplan.photo_meta",)
        )

    @patch("app.layers.registry.get_registry")
    def test_batch_source_anchor_accepts_text_array_and_non_data_mos_layer(
        self, registry_mock: MagicMock
    ) -> None:
        layer = LayerDef(
            layer_key="genplan_photo",
            display_name="Genplan photo",
            schema="genplan",
            table_name="photo_meta",
            geometry_column="geom",
            geometry_type="point",
            symbology={},
        )
        registry_mock.return_value.by_key = {layer.layer_key: layer}
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [
                {
                    "task_key": "11111111-1111-1111-1111-111111111111",
                    "source_table": ["genplan.photo_meta"],
                    "source_row_id": 17,
                }
            ],
            [
                {
                    "source_row_id": 17,
                    "attrs": {"uuid": "photo-1"},
                    "geometry": {"type": "Point", "coordinates": [37.5, 55.7]},
                }
            ],
        ]
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        features = fetch_features_by_source_anchors(
            conn,
            ["11111111-1111-1111-1111-111111111111"],
            {"schema": "crm", "table": "tasks"},
            None,
            allowed_layers=[layer],
        )

        self.assertEqual(len(features), 1)
        self.assertEqual(features[0]["task_key"], "11111111-1111-1111-1111-111111111111")
        self.assertEqual(features[0]["layer_key"], "genplan_photo")

    @patch("app.crm.collector.collect_office_data_tasks")
    @patch("app.crm.collector.collect_field_data_tasks")
    @patch("app.crm.collector.collect_layer_tasks", return_value=([], []))
    @patch(
        "app.crm.collector.build_collect_query_context",
        return_value=CollectQueryContext("POLYGON()", 32637),
    )
    @patch("app.crm.collector.build_collect_plan")
    def test_full_collection_visits_each_planned_source_once(
        self,
        plan_mock: MagicMock,
        _context_mock: MagicMock,
        collect_layer_mock: MagicMock,
        field_mock: MagicMock,
        office_mock: MagicMock,
    ) -> None:
        result = TaskResult(
            "Сокол",
            date.today(),
            date.today(),
            groups=[
                TaskGroup(
                    "Разрытия",
                    [TaskSubgroup("Полевые данные"), TaskSubgroup("Задачи из камерального анализа")],
                )
            ],
        )
        layers = [
            CollectLayerPlanItem("Разрытия", "Полевые данные", "field_data", "field"),
            CollectLayerPlanItem(
                "Разрытия", "Задачи из камерального анализа", "office_data", "office"
            ),
        ]
        plan_mock.return_value = (result, layers)

        collect_tasks(MagicMock(), "Сокол", False, persist=False)

        self.assertEqual(collect_layer_mock.call_count, 2)
        field_mock.assert_not_called()
        office_mock.assert_not_called()


class SnapshotBatchTests(unittest.TestCase):
    def test_linked_snapshot_is_resolved_by_one_batch_query(self) -> None:
        snap = SnapshotRow(
            snapshot_key="snap-1",
            task_key="11111111-1111-1111-1111-111111111111",
            sent_at=None,
            record=TaskRecord(
                key="11111111-1111-1111-1111-111111111111",
                type="Новые ордера ОАТИ, АВР и земляные работы",
                oati_id="point:42",
            ),
            subgroup_name="Ордера ОАТИ",
            group_name="Новые ордера ОАТИ, АВР и земляные работы",
            rayon="Сокол",
        )
        layer = LayerDef(
            layer_key="orders",
            display_name="Orders",
            schema="data_mos",
            table_name="items_2855_points",
            geometry_column="geom",
            geometry_type="point",
            symbology={},
        )
        registry = MagicMock()
        registry.resolve_subgroup_layers.return_value = ([layer], [])
        feature = {
            "task_key": snap.task_key,
            "layer_name": "Orders",
            "layer_key": "orders",
            "attributes": {"id": 42},
            "geometry": {"type": "Point", "coordinates": [37.5, 55.7]},
        }
        store_cfg = {
            "subgroups": {
                "Ордера ОАТИ": {
                    "task_column": "oati_id",
                    "source_field": "id",
                    "scoped_geometry_id": True,
                }
            }
        }

        with (
            patch("app.crm.snapshot_loader.get_registry", return_value=registry),
            patch("app.crm.snapshot_loader._subgroup_cfg", return_value={"layers": ["Orders"]}),
            patch(
                "app.crm.snapshot_loader.fetch_features_by_task_keys",
                return_value=[feature],
            ) as batch,
            patch("app.crm.snapshot_loader.fetch_features_by_business_ids") as by_id,
            patch("app.layers.geojson.resolve_feature_for_task_key") as fallback,
        ):
            result = _batch_layer_snaps_in_district(
                MagicMock(),
                [snap],
                store_cfg,
                "POLYGON()",
                32637,
                apply_district_filter=False,
            )

        self.assertIn("snap-1", result)
        batch.assert_called_once()
        by_id.assert_not_called()
        fallback.assert_not_called()

    def test_data_mos_snapshot_does_not_fall_back_to_business_id(self) -> None:
        snap = SnapshotRow(
            snapshot_key="snap-legacy",
            task_key="22222222-2222-2222-2222-222222222222",
            sent_at=None,
            record=TaskRecord(
                key="22222222-2222-2222-2222-222222222222",
                type="Новые ордера ОАТИ, АВР и земляные работы",
                oati_id="point:42",
            ),
            subgroup_name="Ордера ОАТИ",
            group_name="Новые ордера ОАТИ, АВР и земляные работы",
        )
        layer = LayerDef(
            layer_key="orders",
            display_name="Orders",
            schema="data_mos",
            table_name="items_2855_points",
            geometry_column="geom",
            geometry_type="point",
            symbology={},
        )
        registry = MagicMock()
        registry.resolve_subgroup_layers.return_value = ([layer], [])
        store_cfg = {
            "subgroups": {
                "Ордера ОАТИ": {
                    "task_column": "oati_id",
                    "source_field": "id",
                    "scoped_geometry_id": True,
                }
            }
        }

        with (
            patch("app.crm.snapshot_loader.get_registry", return_value=registry),
            patch("app.crm.snapshot_loader._subgroup_cfg", return_value={"layers": ["Orders"]}),
            patch("app.crm.snapshot_loader.fetch_features_by_task_keys", return_value=[]),
            patch("app.crm.snapshot_loader.fetch_features_by_source_anchors", return_value=[]),
            patch("app.crm.snapshot_loader.fetch_features_by_business_ids") as by_id,
        ):
            result = _batch_layer_snaps_in_district(
                MagicMock(), [snap], store_cfg, "POLYGON()", 32637
            )

        self.assertEqual(result, {})
        by_id.assert_not_called()


if __name__ == "__main__":
    unittest.main()
