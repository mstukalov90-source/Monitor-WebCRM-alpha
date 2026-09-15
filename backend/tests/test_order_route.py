"""Tests for order route building (OSRM integration, mocked)."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from app.crm.order_route import (
    _coords_to_wkt,
    _dedupe_nearby,
    _multiline_wkt,
)
from app.routing.gpx_export import route_to_gpx
from app.routing.osrm_client import OsrmRouteResult, OsrmWaypoint
from app.routing.osrm_profiles import (
    UnknownOsrmProfile,
    canonicalize_osrm_profile,
    route_content_disposition,
    route_export_names,
)


class DedupeNearbyTests(unittest.TestCase):
    def test_removes_duplicates(self) -> None:
        coords = [(37.6, 55.7), (37.60001, 55.70001), (37.61, 55.71)]
        result = _dedupe_nearby(coords, min_dist_deg=0.001)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], (37.6, 55.7))
        self.assertEqual(result[1], (37.61, 55.71))

    def test_keeps_all_when_far_apart(self) -> None:
        coords = [(37.5, 55.7), (37.6, 55.8), (37.7, 55.9)]
        result = _dedupe_nearby(coords)
        self.assertEqual(len(result), 3)

    def test_empty(self) -> None:
        self.assertEqual(_dedupe_nearby([]), [])


class WktTests(unittest.TestCase):
    def test_coords_to_wkt(self) -> None:
        wkt = _coords_to_wkt([(37.6, 55.7), (37.61, 55.71)])
        self.assertIn("LINESTRING", wkt)
        self.assertIn("37.6 55.7", wkt)

    def test_single_point(self) -> None:
        wkt = _coords_to_wkt([(37.6, 55.7)])
        self.assertEqual(wkt, "LINESTRING EMPTY")

    def test_multiline(self) -> None:
        wkt = _multiline_wkt([(37.6, 55.7), (37.61, 55.71)])
        self.assertIn("MULTILINESTRING", wkt)


class GpxExportTests(unittest.TestCase):
    def test_linestring(self) -> None:
        geom = {
            "type": "LineString",
            "coordinates": [[37.6, 55.7], [37.61, 55.71], [37.62, 55.72]],
        }
        gpx = route_to_gpx(geom, name="Test Route")
        self.assertIn("<?xml", gpx)
        self.assertIn("<trk>", gpx)
        self.assertIn("Test Route", gpx)
        self.assertIn('lat="55.7000000"', gpx)
        self.assertIn('lon="37.6000000"', gpx)

    def test_multilinestring(self) -> None:
        geom = {
            "type": "MultiLineString",
            "coordinates": [
                [[37.6, 55.7], [37.61, 55.71]],
                [[37.62, 55.72], [37.63, 55.73]],
            ],
        }
        gpx = route_to_gpx(geom, name="Multi")
        self.assertEqual(gpx.count("<trk>"), 2)

    def test_none_geometry(self) -> None:
        gpx = route_to_gpx(None, name="Empty")
        self.assertIn("<?xml", gpx)
        self.assertNotIn("<trk>", gpx)


class OsrmClientResultTests(unittest.TestCase):
    """Test OsrmRouteResult data structure."""

    def test_default_result(self) -> None:
        r = OsrmRouteResult()
        self.assertEqual(r.code, "Ok")
        self.assertEqual(r.distance, 0.0)
        self.assertEqual(r.geometry_coords, [])

    def test_waypoint(self) -> None:
        wp = OsrmWaypoint(location=(37.6, 55.7), distance=12.5, name="foo")
        self.assertEqual(wp.location, (37.6, 55.7))


class OsrmProfileTests(unittest.TestCase):
    def test_aliases(self) -> None:
        self.assertEqual(canonicalize_osrm_profile("А"), "driving")
        self.assertEqual(canonicalize_osrm_profile("car"), "driving")
        self.assertEqual(canonicalize_osrm_profile("В"), "bicycle")
        self.assertEqual(canonicalize_osrm_profile("bike"), "bicycle")
        self.assertEqual(canonicalize_osrm_profile("П"), "foot")
        self.assertEqual(canonicalize_osrm_profile(None), "foot")

    def test_unknown(self) -> None:
        with self.assertRaises(UnknownOsrmProfile):
            canonicalize_osrm_profile("train")

    def test_export_names_use_order_and_letter(self) -> None:
        ascii_name, utf_name = route_export_names("Измайлово-12", "abcd1234-key", "foot", "gpx")
        self.assertEqual(utf_name, "Измайлово-12_П.gpx")
        self.assertTrue(ascii_name.endswith("_P.gpx"))
        header = route_content_disposition("12345", "abcd", "driving", "geojson")
        self.assertIn("filename*=UTF-8''", header)
        self.assertIn("_A.geojson", header)
        self.assertIn("%D0%90", header)


class MockOsrmNearestTests(unittest.TestCase):
    """Test snap logic with mocked OSRM."""

    @patch("app.crm.order_route._snap_waypoints")
    def test_snap_filters_far_points(self, mock_snap: MagicMock) -> None:
        # Simulate snap that drops 1 of 3 points
        mock_snap.return_value = [(37.6, 55.7), (37.61, 55.71)]
        result = mock_snap("foot", [(37.6, 55.7), (37.61, 55.71), (99.0, 99.0)])
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
