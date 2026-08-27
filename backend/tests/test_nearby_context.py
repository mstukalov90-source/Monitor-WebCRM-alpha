"""Nearby context helpers: order layers, OPS filter, symbology."""

from __future__ import annotations

import unittest

from app.layers.nearby_context import (
    ORDER_PREFIXES,
    iter_order_layers,
    kgs_style,
    ops_extra_where,
    quote_ident,
    style_from_symbology,
)
from app.layers.registry import LayerDef


class FakeRegistry:
    def __init__(self, layers: list[LayerDef]) -> None:
        self.by_key = {layer.layer_key: layer for layer in layers}


def _layer(table_name: str, *, schema: str = "data_mos", geom: str = "point") -> LayerDef:
    return LayerDef(
        layer_key=table_name,
        display_name=table_name,
        schema=schema,
        table_name=table_name,
        geometry_column="geom",
        geometry_type=geom,
        symbology={"color": "#006400", "width": 1.0, "size": 3},
    )


class NearbyContextHelperTests(unittest.TestCase):
    def test_quote_ident_rejects_injection(self) -> None:
        self.assertEqual(quote_ident("items_2855_points"), '"items_2855_points"')
        with self.assertRaises(ValueError):
            quote_ident('items"; DROP TABLE x; --')

    def test_ops_extra_where(self) -> None:
        self.assertEqual(ops_extra_where(True), 't."state_id" = 4')
        self.assertIsNone(ops_extra_where(False))

    def test_iter_order_layers_filters_prefixes(self) -> None:
        registry = FakeRegistry(
            [
                _layer("items_2855_points"),
                _layer("items_62441_lines", geom="line"),
                _layer("items_62461_polygons", geom="polygon"),
                _layer("items_62501_points"),
                _layer("items_1498"),
                _layer("hood", schema="odh_export"),
            ]
        )
        tables = [layer.table_name for layer in iter_order_layers(registry)]
        self.assertEqual(
            tables,
            ["items_2855_points", "items_62441_lines", "items_62461_polygons", "items_62501_points"],
        )
        for prefix in ORDER_PREFIXES:
            self.assertTrue(any(name.startswith(prefix) for name in tables))

    def test_style_from_symbology_line(self) -> None:
        style = style_from_symbology({"color": "#8B4513", "width": 1.0}, "line")
        self.assertEqual(style["color"], "#8B4513")
        self.assertGreaterEqual(style["weight"], 2)

    def test_style_from_symbology_polygon(self) -> None:
        style = style_from_symbology(
            {"fill_color": "#006400", "outline_color": "#004400", "fill_opacity": 0.5},
            "polygon",
        )
        self.assertEqual(style["fillColor"], "#006400")
        self.assertEqual(style["color"], "#004400")
        self.assertEqual(style["fillOpacity"], 0.5)

    def test_kgs_burgundy(self) -> None:
        point = kgs_style("point")
        line = kgs_style("line")
        self.assertEqual(point["color"], "#800020")
        self.assertEqual(line["color"], "#800020")
        self.assertGreaterEqual(line["weight"], 3)

    def test_msk77_sql_uses_proj_from_monitor(self) -> None:
        from app.layers.nearby_context import (
            KGS_TABLE_KINDS,
            MSK77_SRID,
            WGS84_PROJ4,
            features_within_radius_sql,
        )

        self.assertEqual(MSK77_SRID, 980077)
        self.assertIn("kgs_point", KGS_TABLE_KINDS)
        sql = features_within_radius_sql("sps", "sps_lines", "geom", source_proj="msk77")
        self.assertEqual(sql.count("%s"), 5)
        geo_pos = sql.index("ST_GeomFromGeoJSON(%s)")
        wgs_pos = sql.index("%s::text AS wgs84")
        msk_pos = sql.index("%s::text AS msk77")
        self.assertLess(geo_pos, wgs_pos)
        self.assertLess(wgs_pos, msk_pos)
        self.assertIn("ST_SetSRID(ST_Force2D(t.\"geom\"), 0)", sql)
        self.assertIn("ST_Transform(p.center_4326, p.wgs84, p.msk77)", sql)
        self.assertNotIn("ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s)", sql)
        self.assertNotIn("32637", sql)
        self.assertEqual(WGS84_PROJ4, "+proj=longlat +datum=WGS84 +no_defs")

    def test_order_sql_keeps_utm_metric(self) -> None:
        from app.layers.nearby_context import features_within_radius_sql

        sql = features_within_radius_sql("data_mos", "items_2855_points", "geom", metric=32637)
        self.assertIn("ST_Transform(t.\"geom\", 32637)", sql)
        self.assertIn("ST_Transform(t.\"geom\", 4326)", sql)
        self.assertNotIn("ST_Force2D", sql)


if __name__ == "__main__":
    unittest.main()
