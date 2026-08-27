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


def mm_to_px(value: float, *, default: float = 2.0, cap: float = 12.0, floor: float = 0.5) -> float:
    if value <= 0:
        return default
    return max(floor, min(cap, value * 3.0))


def _is_near_black(color: str | None) -> bool:
    if not color or not color.startswith("#") or len(color) < 7:
        return True
    try:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
    except ValueError:
        return True
    return r < 28 and g < 28 and b < 28


def _dash_array(props: dict[str, str]) -> str | None:
    use_custom = (props.get("use_custom_dash") or "").lower()
    if use_custom in ("1", "true"):
        raw = props.get("customdash") or ""
        parts = [p.strip() for p in raw.replace(",", ";").split(";") if p.strip()]
        px: list[str] = []
        for part in parts:
            try:
                px.append(str(round(mm_to_px(float(part), default=2.0, cap=24.0), 1)))
            except ValueError:
                continue
        if px:
            return ",".join(px)
    style = (props.get("line_style") or "solid").lower().replace("_", " ").strip()
    mapping = {
        "dash": "6,4",
        "dot": "1,4",
        "dash dot": "8,4,1,4",
        "dash dot dot": "8,4,1,4,1,4",
    }
    return mapping.get(style)


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


def _apply_line_props(style: FeatureStyle, props: dict[str, str]) -> None:
    color = parse_qgis_color(
        props.get("line_color") or props.get("color") or props.get("outline_color")
    )
    width = _float_prop(props, "line_width", "outline_width", "stroke_width", default=0.5) or 0.5
    alpha = parse_qgis_alpha(props.get("line_color") or props.get("color"))
    if color:
        style["color"] = color
        style["fillColor"] = color
    style["weight"] = mm_to_px(width, default=1.0, cap=10.0, floor=0.5)
    if alpha is not None:
        style["opacity"] = alpha
    dash = _dash_array(props)
    if dash:
        style["dashArray"] = dash
    elif "dashArray" in style:
        del style["dashArray"]


def _apply_fill_props(style: FeatureStyle, props: dict[str, str]) -> None:
    fill = parse_qgis_color(props.get("color") or props.get("fill_color"))
    outline = parse_qgis_color(
        props.get("outline_color") or props.get("stroke_color") or props.get("line_color")
    )
    width = _float_prop(props, "outline_width", "stroke_width", "line_width", default=0.4) or 0.4
    alpha = parse_qgis_alpha(props.get("color") or props.get("fill_color"))
    if fill:
        style["fillColor"] = fill
        if not outline:
            style["color"] = fill
    if outline:
        style["color"] = outline
    style["weight"] = mm_to_px(width, default=1.0, cap=8.0, floor=0.5)
    style["fillOpacity"] = alpha if alpha is not None else 0.45


def _apply_marker_props(style: FeatureStyle, props: dict[str, str]) -> None:
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
    style["radius"] = mm_to_px(size, default=4.0, cap=14.0, floor=2.0)
    style["weight"] = mm_to_px(outline_w, default=1.0, cap=6.0, floor=0.5)
    if alpha is not None:
        style["fillOpacity"] = alpha
        style["opacity"] = alpha
    else:
        style["fillOpacity"] = 0.95


def style_from_symbol_element(symbol_el: ET.Element) -> FeatureStyle:
    """Merge all enabled QGIS symbol layers (paint order: last layer on top)."""
    style = dict(DEFAULT_STYLE)
    symbol_type = (symbol_el.get("type") or "line").lower()
    line_layers: list[dict[str, str]] = []
    fill_layers: list[dict[str, str]] = []
    marker_layers: list[dict[str, str]] = []
    markerline_layers: list[dict[str, str]] = []
    for layer in symbol_el.findall("layer"):
        enabled = layer.get("enabled", "1")
        if enabled in ("0", "false", "False"):
            continue
        props = _layer_props(layer)
        cls = (layer.get("class") or "").lower()
        if cls == "markerline":
            markerline_layers.append(props)
            continue
        if "marker" in cls or symbol_type == "marker":
            marker_layers.append(props)
            continue
        if "fill" in cls or (symbol_type == "fill" and "line" not in cls):
            fill_layers.append(props)
            continue
        if "line" in cls or symbol_type == "line":
            line_layers.append(props)
    if fill_layers:
        for props in fill_layers:
            _apply_fill_props(style, props)
        if line_layers:
            outline = dict(style)
            _apply_line_props(outline, line_layers[-1])
            style["color"] = outline.get("color") or style.get("color")
            style["weight"] = outline.get("weight") or style.get("weight")
            if outline.get("dashArray"):
                style["dashArray"] = outline["dashArray"]
        return style
    if marker_layers:
        _apply_marker_props(style, marker_layers[-1])
        return style
    if line_layers:
        chosen = line_layers[-1]
        for props in reversed(line_layers):
            color = parse_qgis_color(
                props.get("line_color") or props.get("color") or props.get("outline_color")
            )
            if color and not _is_near_black(color):
                chosen = props
                break
        _apply_line_props(style, chosen)
        style["fillOpacity"] = 0
        if _is_near_black(style.get("color")):
            for props in reversed(markerline_layers):
                mark_color = parse_qgis_color(
                    props.get("color") or props.get("line_color") or props.get("fill_color")
                )
                if mark_color and not _is_near_black(mark_color):
                    style["color"] = mark_color
                    style["fillColor"] = mark_color
                    break
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
    label_field: str | None = None
    label_color: str | None = None

    def resolve(self, attrs: dict[str, Any] | None = None) -> FeatureStyle:
        values = attrs or {}
        if self.mode == "categorized" and self.attr:
            raw = values.get(self.attr)
            for key in _category_lookup_keys(raw):
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


def _category_lookup_keys(raw: Any) -> list[str]:
    if raw is None:
        return [""]
    keys = [str(raw).strip()]
    try:
        as_int = str(int(raw))
        if as_int not in keys:
            keys.append(as_int)
    except (TypeError, ValueError):
        try:
            as_int = str(int(float(str(raw).strip())))
            if as_int not in keys:
                keys.append(as_int)
        except (TypeError, ValueError):
            pass
    return keys


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


def parse_labeling(root: ET.Element) -> tuple[str | None, str | None]:
    """Return (field_name, text_color) from QGIS labeling XML."""
    field: str | None = None
    color: str | None = None
    text_style = root.find(".//text-style")
    if text_style is not None:
        field = text_style.get("fieldName") or None
        color = parse_qgis_color(text_style.get("textColor"))
    labeling = root.find(".//labeling")
    if labeling is not None:
        if not field:
            field = labeling.get("fieldName") or None
        for opt in labeling.iter("Option"):
            name = opt.get("name")
            value = opt.get("value")
            if not value:
                continue
            if name in ("fieldName", "field_name") and not field:
                field = value
            if name == "textColor" and not color:
                color = parse_qgis_color(value)
    if field and not _IDENT_RE.match(field):
        field = None
    return field, color


LABEL_ONLY_STYLE: FeatureStyle = {
    "color": "#323232",
    "weight": 0,
    "fillColor": "#323232",
    "fillOpacity": 0,
    "opacity": 0,
    "radius": 0,
}


def parse_styleqml(styleqml: str | None) -> ParsedLayerStyle:
    parsed = ParsedLayerStyle()
    if not styleqml or not str(styleqml).strip():
        return parsed
    try:
        root = ET.fromstring(str(styleqml))
    except ET.ParseError:
        return parsed
    parsed.label_field, parsed.label_color = parse_labeling(root)
    renderer = root.find(".//renderer-v2")
    if renderer is None:
        renderer = root.find("renderer-v2")
    if renderer is None:
        return parsed
    renderer_type = (renderer.get("type") or "singleSymbol").lower()
    if renderer_type == "nullsymbol":
        parsed.mode = "single"
        parsed.default = dict(LABEL_ONLY_STYLE)
        if parsed.label_color:
            parsed.default["color"] = parsed.label_color
            parsed.default["fillColor"] = parsed.label_color
        return parsed
    symbols = _symbols_by_name(renderer)
    if "0" in symbols:
        parsed.default = symbols["0"]
    elif symbols:
        parsed.default = next(iter(symbols.values()))
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
