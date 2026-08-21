"""Parent items_* extra columns are merged into split-table feature attributes."""

from __future__ import annotations

import unittest

from app.layers.geojson import _attrs_sql, _parent_table_from_split
from app.layers.registry import LayerDef


def _layer(table_name: str, *, schema: str = "data_mos") -> LayerDef:
    return LayerDef(
        layer_key=table_name,
        display_name=table_name,
        schema=schema,
        table_name=table_name,
        geometry_column="geom",
        geometry_type="point",
        symbology={},
    )


class ItemsParentAttrsTests(unittest.TestCase):
    def test_parent_table_from_quoted_split(self) -> None:
        self.assertEqual(
            _parent_table_from_split('"data_mos"."items_62501_points"'),
            '"data_mos"."items_62501"',
        )
        self.assertEqual(
            _parent_table_from_split('"data_mos"."items_2855_lines"'),
            '"data_mos"."items_2855"',
        )
        self.assertEqual(
            _parent_table_from_split("data_mos.items_62461_polygons"),
            '"data_mos"."items_62461"',
        )

    def test_earthwork_attrs_join_parent_objectives(self) -> None:
        expr, join = _attrs_sql(_layer("items_62501_points"))
        self.assertIn("earthwork_objectives", expr)
        self.assertIn("objectives_of_the_installation_of_temporary_fences", expr)
        self.assertIn("objectives_of_the_placement_of_temporary_objects", expr)
        self.assertNotIn("damage_type", expr)
        self.assertIn('LEFT JOIN "data_mos"."items_62501" p ON p.id = t.source_id', join)

    def test_oati_attrs_join_parent_objectives(self) -> None:
        expr, join = _attrs_sql(_layer("items_2855_lines"))
        self.assertIn("earthwork_objectives", expr)
        self.assertIn('LEFT JOIN "data_mos"."items_2855" p', join)

    def test_avr_attrs_join_parent_damage_type(self) -> None:
        expr, join = _attrs_sql(_layer("items_62461_polygons"))
        self.assertIn("damage_type", expr)
        self.assertNotIn("earthwork_objectives", expr)
        self.assertIn('LEFT JOIN "data_mos"."items_62461" p', join)

    def test_other_items_table_has_no_parent_join(self) -> None:
        expr, join = _attrs_sql(_layer("items_62441_points"))
        self.assertEqual(expr, "to_jsonb(t) - 'geom'")
        self.assertEqual(join, "")

    def test_non_items_layer_has_no_parent_join(self) -> None:
        expr, join = _attrs_sql(_layer("hood", schema="odh_export"))
        self.assertEqual(expr, "to_jsonb(t) - 'geom'")
        self.assertEqual(join, "")


if __name__ == "__main__":
    unittest.main()
