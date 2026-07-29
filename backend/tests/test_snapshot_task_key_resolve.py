"""Regression: snapshot geometry must resolve via task_key, not rewritten business ids."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.crm.snapshot_loader import SnapshotRow, snapshot_row_to_feature
from app.crm.store import TaskRecord, _is_data_mos_items_table
from app.layers.geojson import (
    _is_data_mos_items_table as geojson_is_items_table,
    resolve_feature_for_task_key,
)


class ItemsTableRegexTests(unittest.TestCase):
    def test_store_accepts_quoted_qualified_table(self) -> None:
        self.assertTrue(_is_data_mos_items_table('"data_mos"."items_123_points"'))
        self.assertTrue(_is_data_mos_items_table('"data_mos"."items_60562_lines"'))
        self.assertTrue(_is_data_mos_items_table('"data_mos"."items_1_polygons"'))

    def test_store_accepts_unquoted_qualified_table(self) -> None:
        self.assertTrue(_is_data_mos_items_table("data_mos.items_123_points"))

    def test_store_rejects_non_items_tables(self) -> None:
        self.assertFalse(_is_data_mos_items_table('"public"."tasks"'))
        self.assertFalse(_is_data_mos_items_table(None))
        self.assertFalse(_is_data_mos_items_table(""))

    def test_store_and_geojson_regex_agree(self) -> None:
        samples = [
            '"data_mos"."items_123_points"',
            "data_mos.items_123_points",
            '"data_mos"."items_9_polygons"',
            "other.schema",
        ]
        for sample in samples:
            self.assertEqual(
                bool(_is_data_mos_items_table(sample)),
                bool(geojson_is_items_table(sample)),
                msg=sample,
            )


class ResolveFeatureForTaskKeyOrderTests(unittest.TestCase):
    def test_prefers_task_key_over_anchor(self) -> None:
        conn = MagicMock()
        store_cfg = {"subgroups": {"Ордера ОАТИ": {"scoped_geometry_id": True}}}
        by_key = {"geometry": {"type": "Point", "coordinates": [1, 2]}, "layer_key": "a"}
        with (
            patch(
                "app.layers.geojson.fetch_feature_by_task_key",
                return_value=by_key,
            ) as by_task_key,
            patch(
                "app.layers.geojson.fetch_feature_by_source_anchor",
                return_value={"geometry": {"type": "Point", "coordinates": [9, 9]}},
            ) as by_anchor,
        ):
            result = resolve_feature_for_task_key(conn, "task-1", "Ордера ОАТИ", store_cfg)

        self.assertIs(result, by_key)
        by_task_key.assert_called_once()
        by_anchor.assert_not_called()

    def test_falls_back_to_source_anchor(self) -> None:
        conn = MagicMock()
        store_cfg = {"subgroups": {"Ордера ОАТИ": {"scoped_geometry_id": True}}}
        by_anchor = {"geometry": {"type": "Point", "coordinates": [3, 4]}, "layer_key": "b"}
        with (
            patch("app.layers.geojson.fetch_feature_by_task_key", return_value=None),
            patch(
                "app.layers.geojson.fetch_feature_by_source_anchor",
                return_value=by_anchor,
            ) as anchor,
        ):
            result = resolve_feature_for_task_key(conn, "task-1", "Ордера ОАТИ", store_cfg)

        self.assertIs(result, by_anchor)
        anchor.assert_called_once_with(conn, "task-1", store_cfg)


class SnapshotRowToFeatureTaskKeyTests(unittest.TestCase):
    def test_uses_task_key_when_business_id_would_miss(self) -> None:
        snap = SnapshotRow(
            snapshot_key="snap-1",
            task_key="task-1",
            sent_at=None,
            record=TaskRecord(
                key="task-1",
                type="Новые ордера ОАТИ, АВР и земляные работы",
                oati_id="rewritten-order-number",
            ),
            subgroup_name="Ордера ОАТИ",
            group_name="Новые ордера ОАТИ, АВР и земляные работы",
            rayon="Тверской",
        )
        store_cfg = {
            "subgroups": {
                "Ордера ОАТИ": {
                    "task_column": "oati_id",
                    "source_field": "id",
                    "scoped_geometry_id": True,
                }
            }
        }
        resolved = {
            "layer_name": "ОАТИ point",
            "layer_key": "oati_point",
            "attributes": {"id": 42},
            "geometry": {"type": "Point", "coordinates": [37.6, 55.7]},
        }
        conn = MagicMock()

        with (
            patch(
                "app.layers.geojson.resolve_feature_for_task_key",
                return_value=resolved,
            ) as resolve,
            patch("app.crm.snapshot_loader.lookup_feature") as lookup,
            patch("app.crm.snapshot_loader.geometry_in_district", return_value=True),
        ):
            feature = snapshot_row_to_feature(
                conn,
                snap,
                store_cfg,
                district_wkt="POLYGON((0 0,1 0,1 1,0 1,0 0))",
                metric_srid=32637,
                requested_rayon="Тверской",
            )

        self.assertIsNotNone(feature)
        assert feature is not None
        self.assertEqual(feature.task_key, "task-1")
        self.assertEqual(feature.geometry, resolved["geometry"])
        resolve.assert_called_once_with(conn, "task-1", "Ордера ОАТИ", store_cfg)
        lookup.assert_not_called()


class SnapshotGroupNameCanonicalTests(unittest.TestCase):
    def test_field_data_stale_type_maps_to_canonical_group(self) -> None:
        from app.crm.snapshot_loader import _row_to_snapshot_row

        store_cfg = {
            "subgroups": {
                "Полевые данные": {"source": "field_data"},
            }
        }
        crm_cfg = {
            "groups": [
                {
                    "name": "Разрытия",
                    "subgroups": [{"name": "Полевые данные"}],
                }
            ]
        }
        row = {
            "key": "snap-1",
            "task_key": "task-1",
            "sent_at": None,
            "type": "Разрытие",
            "is_field_data": True,
            "is_office_task": False,
            "rayon": "Беговой",
        }

        snap = _row_to_snapshot_row(row, store_cfg, crm_cfg, include_executor=False)

        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertEqual(snap.subgroup_name, "Полевые данные")
        self.assertEqual(snap.group_name, "Разрытия")


if __name__ == "__main__":
    unittest.main()
