"""QGIS layer_styles QML → Leaflet style."""

from __future__ import annotations

import unittest

from app.layers.qgis_styles import parse_qgis_color, parse_styleqml, style_from_symbol_element
from xml.etree import ElementTree as ET

SINGLE_QML = """
<qgis>
  <renderer-v2 type="singleSymbol">
    <symbols>
      <symbol type="line" name="0">
        <layer class="SimpleLine" enabled="1">
          <prop k="line_color" v="227,26,28,255"/>
          <prop k="line_width" v="0.8"/>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
</qgis>
"""

CATEGORIZED_QML = """
<qgis>
  <renderer-v2 type="categorizedSymbol" attr="kind">
    <categories>
      <category symbol="0" value="a" label="A"/>
      <category symbol="1" value="b" label="B"/>
      <category symbol="2" value="" label="other"/>
    </categories>
    <symbols>
      <symbol type="marker" name="0">
        <layer class="SimpleMarker" enabled="1">
          <prop k="color" v="0,128,0,255"/>
          <prop k="size" v="2"/>
        </layer>
      </symbol>
      <symbol type="marker" name="1">
        <layer class="SimpleMarker" enabled="1">
          <prop k="color" v="0,0,255,255"/>
          <prop k="size" v="2"/>
        </layer>
      </symbol>
      <symbol type="marker" name="2">
        <layer class="SimpleMarker" enabled="1">
          <prop k="color" v="128,128,128,255"/>
          <prop k="size" v="2"/>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
</qgis>
"""

RULE_QML = """
<qgis>
  <renderer-v2 type="RuleRenderer">
    <rules>
      <rule filter='"state_id" = 4' symbol="0" label="ops"/>
      <rule filter="ELSE" symbol="1" label="other"/>
    </rules>
    <symbols>
      <symbol type="line" name="0">
        <layer class="SimpleLine" enabled="1">
          <prop k="line_color" v="106,27,154,255"/>
          <prop k="line_width" v="0.5"/>
        </layer>
      </symbol>
      <symbol type="line" name="1">
        <layer class="SimpleLine" enabled="1">
          <prop k="line_color" v="21,101,192,255"/>
          <prop k="line_width" v="0.5"/>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
</qgis>
"""


class QgisStyleTests(unittest.TestCase):
    def test_parse_qgis_color_rgba(self) -> None:
        self.assertEqual(parse_qgis_color("227,26,28,255"), "#e31a1c")
        self.assertEqual(parse_qgis_color("#006400"), "#006400")
        self.assertIsNone(parse_qgis_color(""))

    def test_single_symbol_line_color(self) -> None:
        parsed = parse_styleqml(SINGLE_QML)
        self.assertEqual(parsed.mode, "single")
        style = parsed.resolve({})
        self.assertEqual(style["color"], "#e31a1c")
        self.assertGreaterEqual(style["weight"], 2)

    def test_categorized_by_attr(self) -> None:
        parsed = parse_styleqml(CATEGORIZED_QML)
        self.assertEqual(parsed.mode, "categorized")
        self.assertEqual(parsed.attr, "kind")
        self.assertEqual(parsed.resolve({"kind": "a"})["fillColor"], "#008000")
        self.assertEqual(parsed.resolve({"kind": "b"})["fillColor"], "#0000ff")
        self.assertEqual(parsed.resolve({"kind": "zzz"})["fillColor"], "#808080")

    def test_rule_renderer_state_id(self) -> None:
        parsed = parse_styleqml(RULE_QML)
        self.assertEqual(parsed.mode, "rules")
        self.assertEqual(parsed.resolve({"state_id": 4})["color"], "#6a1b9a")
        self.assertEqual(parsed.resolve({"state_id": 1})["color"], "#1565c0")

    def test_empty_qml_falls_back(self) -> None:
        parsed = parse_styleqml(None)
        self.assertEqual(parsed.mode, "single")
        self.assertEqual(parsed.resolve({})["color"], "#3388ff")

    def test_option_tree_symbol(self) -> None:
        xml = """
        <symbol type="line" name="0">
          <layer class="SimpleLine" enabled="1">
            <Option type="Map">
              <Option name="line_color" value="255,0,0,255" type="QString"/>
              <Option name="line_width" value="1" type="QString"/>
            </Option>
          </layer>
        </symbol>
        """
        style = style_from_symbol_element(ET.fromstring(xml))
        self.assertEqual(style["color"], "#ff0000")


if __name__ == "__main__":
    unittest.main()
