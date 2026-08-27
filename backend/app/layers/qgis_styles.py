"""Parse QGIS public.layer_styles QML into Leaflet-ready feature styles."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree as ET

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

FeatureStyle = dict[str, Any]

DEFAULT_STYLE: FeatureStyle = {
    "color": "#3388ff",
    "weight": 2,
    "fillColor": "#3388ff",
    "fillOpacity": 0.35,
    "opacity": 0.9,
    "radius": 5,
}

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_EQ_FILTER_RE = re.compile(
    r'^\s*"?(?P<field>[A-Za-z_][A-Za-z0-9_]*)"?\s*=\s*(?P<value>.+?)\s*$'
)


def parse_qgis_color(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if text.startswith("#") and len(text) in (4, 7, 9):
        if len(text) == 4:
            return f"#{text[1]*2}{text[2]*2}{text[3]*2}".lower()
        return text[:7].lower()
    parts = [p.strip() for p in text.split(",")]
    if len(parts) < 3:
        return None
    try:
        r = max(0, min(255, int(float(parts[0]))))
        g = max(0, min(255, int(float(parts[1]))))
        b = max(0, min(255, int(float(parts[2]))))
    except ValueError:
        return None
    return f"#{r:02x}{g:02x}{b:02x}"


def parse_qgis_alpha(value: str | None) -> float | None:
    if not value:
        return None
    parts = [p.strip() for p in value.split(",")]
    if len(parts) < 4:
        return None
    try:
        alpha = float(parts[3])
    except ValueError:
        return None
    if alpha > 1:
        alpha = alpha / 255.0
    return max(0.0, min(1.0, alpha))


def mm_to_px(value: float, *, default: float = 2.0, cap: float = 12.0) -> float:
    if value <= 0:
        return default
    return max(1.0, min(cap, value * 3.0))


def _layer_props(layer_el: ET.Element) -> dict[str, str]:
    props: dict[str, str] = {}
    for prop in layer_el.findall("prop"):
        key = prop.get("k")
        val = prop.get("v")
        if key and val is not None:
            props[key] = val
    for opt in layer_el.iter("Option"):
        name = opt.get("name")
        val = opt.get("value")
        if name and val is not None and name not in props:
            props[name] = val
    return props


def _float_prop(props: dict[str, str], *keys: str, default: float | None = None) -> float | None:
    for key in keys:
        raw = props.get(key)
        if raw is None or raw == "":
            continue
        try:
            return float(raw)
        except ValueError:
            continue
    return default


def style_from_symbol_element(symbol_el: ET.Element) -> FeatureStyle:
    style = dict(DEFAULT_STYLE)
    symbol_type = (symbol_el.get("type") or "line").lower()
    for layer in symbol_el.findall("layer"):
        enabled = layer.get("enabled", "1")
        if enabled in ("0", "false", "False"):
            continue
        props = _layer_props(layer)
        cls = (layer.get("class") or "").lower()
        if "marker" in cls or symbol_type == "marker":
            color = parse_qgis_color(
                props.get("color") or props.get("color_1") or props.get("fill_color")
            )
            outline = parse_qgis_color(props.get("outline_color") or props.get("stroke_color"))
            size = _float_prop(props, "size", "size_1", default=2.0) or 2.0
            outline_w = _float_prop(props, "outline_width", "stroke_width", default=0.4) or 0.4
            alpha = parse_qgis_alpha(props.get("color") or props.get("color_1"))
            if color:
                style["fillColor"] = color
                style["color"] = outline or color
            elif outline:
                style["color"] = outline
            style["radius"] = max(3.0, mm_to_px(size, default=4.0, cap=14.0))
            style["weight"] = max(1.0, mm_to_px(outline_w, default=1.0, cap=6.0))
            if alpha is not None:
                style["fillOpacity"] = alpha
                style["opacity"] = alpha
            return style
        if "fill" in cls or symbol_type == "fill":
            fill = parse_qgis_color(props.get("color") or props.get("fill_color"))
            outline = parse_qgis_color(
                props.get("outline_color") or props.get("stroke_color") or props.get("line_color")
            )
            width = _float_prop(props, "outline_width", "stroke_width", "line_width", default=0.4) or 0.4
            alpha = parse_qgis_alpha(props.get("color") or props.get("fill_color"))
            if fill:
                style["fillColor"] = fill
                style["color"] = outline or fill
            elif outline:
                style["color"] = outline
            style["weight"] = max(1.0, mm_to_px(width, default=1.0, cap=8.0))
            style["fillOpacity"] = alpha if alpha is not None else 0.45
            return style
        color = parse_qgis_color(
            props.get("line_color") or props.get("color") or props.get("outline_color")
        )
        width = _float_prop(props, "line_width", "outline_width", "stroke_width", default=0.5) or 0.5
        alpha = parse_qgis_alpha(props.get("line_color") or props.get("color"))
        if color:
            style["color"] = color
            style["fillColor"] = color
        style["weight"] = max(2.0, mm_to_px(width, default=2.0, cap=10.0))
        if alpha is not None:
            style["opacity"] = alpha
        return style
    return style


def _symbols_by_name(renderer: ET.Element) -> dict[str, FeatureStyle]:
    result: dict[str, FeatureStyle] = {}
    symbols_el = renderer.find("symbols")
    if symbols_el is None:
        return result
    for symbol in symbols_el.findall("symbol"):
        name = symbol.get("name")
        if name is None:
            continue
        result[name] = style_from_symbol_element(symbol)
    return result


@dataclass
class ParsedLayerStyle:
    mode: str = "single"
    default: FeatureStyle = field(default_factory=lambda: dict(DEFAULT_STYLE))
    attr: str | None = None
    categories: dict[str, FeatureStyle] = field(default_factory=dict)
    rules: list[tuple[str | None, FeatureStyle]] = field(default_factory=list)

    def resolve(self, attrs: dict[str, Any] | None = None) -> FeatureStyle:
        values = attrs or {}
        if self.mode == "categorized" and self.attr:
            raw = values.get(self.attr)
            key = "" if raw is None else str(raw)
            if key in self.categories:
                return dict(self.categories[key])
            if "" in self.categories:
                return dict(self.categories[""])
            return dict(self.default)
        if self.mode == "rules":
            fallback: FeatureStyle | None = None
            for filter_expr, style in self.rules:
                if not filter_expr or filter_expr.strip().upper() == "ELSE":
                    fallback = style
                    continue
                if _rule_matches(filter_expr, values):
                    return dict(style)
            if fallback is not None:
                return dict(fallback)
            return dict(self.default)
        return dict(self.default)


def _rule_matches(filter_expr: str, attrs: dict[str, Any]) -> bool:
    match = _EQ_FILTER_RE.match(filter_expr)
    if not match:
        return False
    field = match.group("field")
    raw = match.group("value").strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        expected = raw[1:-1]
    else:
        expected = raw
    actual = attrs.get(field)
    if actual is None:
        return False
    return str(actual).strip() == expected.strip()


def parse_styleqml(styleqml: str | None) -> ParsedLayerStyle:
    parsed = ParsedLayerStyle()
    if not styleqml or not styleqml.strip():
        return parsed
    try:
        root = ET.fromstring(styleqml)
    except ET.ParseError:
        return parsed
    renderer = root.find(".//renderer-v2")
    if renderer is None:
        renderer = root.find("renderer-v2")
    if renderer is None:
        return parsed
    symbols = _symbols_by_name(renderer)
    if "0" in symbols:
        parsed.default = symbols["0"]
    elif symbols:
        parsed.default = next(iter(symbols.values()))
    renderer_type = (renderer.get("type") or "singleSymbol").lower()
    if renderer_type == "categorizedsymbol":
        parsed.mode = "categorized"
        attr = renderer.get("attr")
        parsed.attr = attr if attr and _IDENT_RE.match(attr) else None
        for category in renderer.findall("categories/category"):
            symbol_name = category.get("symbol") or "0"
            value = category.get("value")
            if value is None:
                value = ""
            parsed.categories[value] = symbols.get(symbol_name, parsed.default)
        return parsed
    if renderer_type == "rulerenderer":
        parsed.mode = "rules"
        for rule in renderer.findall(".//rule"):
            symbol_name = rule.get("symbol")
            if symbol_name is None:
                continue
            parsed.rules.append((rule.get("filter"), symbols.get(symbol_name, parsed.default)))
        return parsed
    parsed.mode = "single"
    return parsed


def load_sps_styles(conn: PgConnection, schema: str = "sps") -> dict[str, ParsedLayerStyle]:
    """Map table name → parsed QGIS style for the given schema."""
    query = """
        SELECT f_table_name, styleqml, useasdefault, update_time
        FROM public.layer_styles
        WHERE f_table_schema = %s
        ORDER BY useasdefault DESC NULLS LAST, update_time DESC NULLS LAST
    """
    styles: dict[str, ParsedLayerStyle] = {}
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (schema,))
            rows = cur.fetchall()
    except Exception:
        conn.rollback()
        return styles
    for row in rows:
        table = str(row.get("f_table_name") or "")
        if not table or table in styles:
            continue
        styles[table] = parse_styleqml(row.get("styleqml"))
    return styles
