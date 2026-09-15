"""Minimal GPX export from route geometry (no extra dependencies)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any


GPX_NS = "http://www.topografix.com/GPX/1/1"
GPX_XSI = "http://www.w3.org/2001/XMLSchema-instance"
GPX_SCHEMA = "http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd"


def route_to_gpx(
    route_geometry: dict[str, Any] | None,
    *,
    name: str = "Survey Route",
    description: str = "",
) -> str:
    """Convert a GeoJSON LineString / MultiLineString to GPX XML string."""
    root = ET.Element("gpx", {
        "xmlns": GPX_NS,
        "xmlns:xsi": GPX_XSI,
        "xsi:schemaLocation": GPX_SCHEMA,
        "version": "1.1",
        "creator": "MONITOR-WebCRM",
    })

    metadata = ET.SubElement(root, "metadata")
    ET.SubElement(metadata, "name").text = name
    if description:
        ET.SubElement(metadata, "desc").text = description
    time_el = ET.SubElement(metadata, "time")
    time_el.text = datetime.now(timezone.utc).isoformat()

    if not route_geometry:
        return _to_string(root)

    geom_type = route_geometry.get("type", "")
    coords_lists: list[list] = []

    if geom_type == "LineString":
        coords_lists.append(route_geometry.get("coordinates", []))
    elif geom_type == "MultiLineString":
        coords_lists.extend(route_geometry.get("coordinates", []))
    elif geom_type == "GeometryCollection":
        for g in route_geometry.get("geometries", []):
            if g.get("type") == "LineString":
                coords_lists.append(g.get("coordinates", []))
            elif g.get("type") == "MultiLineString":
                coords_lists.extend(g.get("coordinates", []))

    for idx, coords in enumerate(coords_lists):
        trk = ET.SubElement(root, "trk")
        ET.SubElement(trk, "name").text = f"{name} #{idx + 1}" if len(coords_lists) > 1 else name
        trkseg = ET.SubElement(trk, "trkseg")
        for point in coords:
            if len(point) < 2:
                continue
            attrs = {"lat": f"{point[1]:.7f}", "lon": f"{point[0]:.7f}"}
            trkpt = ET.SubElement(trkseg, "trkpt", attrs)
            if len(point) >= 3:
                ET.SubElement(trkpt, "ele").text = f"{point[2]:.1f}"

    return _to_string(root)


def _to_string(root: ET.Element) -> str:
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode"
    )
