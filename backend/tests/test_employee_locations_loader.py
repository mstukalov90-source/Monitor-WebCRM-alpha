"""Tests for employee real-time location loader."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from app.crm.employee_locations_loader import fetch_employee_locations


class EmployeeLocationsLoaderTests(unittest.TestCase):
    @patch("app.crm.employee_locations_loader.fetch_district_wkt", return_value=None)
    def test_returns_error_when_district_not_found(self, _wkt: MagicMock) -> None:
        conn = MagicMock()
        locations, errors = fetch_employee_locations(conn, "Unknown")
        self.assertEqual(locations, [])
        self.assertTrue(any("District polygon not found" in err for err in errors))

    @patch("app.crm.employee_locations_loader.fetch_district_wkt", return_value="POLYGON((0 0,1 0,1 1,0 1,0 0))")
    def test_returns_only_user_in_attributes(self, _wkt: MagicMock) -> None:
        geometry = {"type": "Point", "coordinates": [37.62, 55.75]}
        row_json = {
            "user": "IvanovII",
            "time": "2026-07-13T10:00:00+00:00",
            "number": "uuid-123",
        }

        cursor = MagicMock()
        cursor.fetchall.return_value = [
            {
                "location_id": "IvanovII",
                "geometry": geometry,
                "row_json": row_json,
            }
        ]
        cursor_cm = MagicMock()
        cursor_cm.__enter__.return_value = cursor
        cursor_cm.__exit__.return_value = False

        conn = MagicMock()
        conn.cursor.return_value = cursor_cm

        locations, errors = fetch_employee_locations(conn, "Сокол")

        self.assertEqual(errors, [])
        self.assertEqual(len(locations), 1)
        self.assertEqual(locations[0]["id"], "IvanovII")
        self.assertEqual(locations[0]["attributes"], {"user": "IvanovII"})
        self.assertEqual(locations[0]["geometry"], geometry)

    @patch("app.crm.employee_locations_loader.fetch_district_wkt", return_value="POLYGON((0 0,1 0,1 1,0 1,0 0))")
    def test_parses_geometry_json_string(self, _wkt: MagicMock) -> None:
        geometry = {"type": "Point", "coordinates": [37.62, 55.75]}
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            {
                "location_id": "PetrovPP",
                "geometry": json.dumps(geometry),
                "row_json": json.dumps({"user": "PetrovPP", "time": "2026-07-13T10:00:00+00:00"}),
            }
        ]
        cursor_cm = MagicMock()
        cursor_cm.__enter__.return_value = cursor
        cursor_cm.__exit__.return_value = False

        conn = MagicMock()
        conn.cursor.return_value = cursor_cm

        locations, errors = fetch_employee_locations(conn, "Сокол")

        self.assertEqual(errors, [])
        self.assertEqual(locations[0]["geometry"]["type"], "Point")
        self.assertEqual(locations[0]["attributes"], {"user": "PetrovPP"})


if __name__ == "__main__":
    unittest.main()
