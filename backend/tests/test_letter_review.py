"""Tests for OATI letter manager review and area-order executor rules."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.auth.deps import require_manager_or_admin
from app.auth.session import UserSession
from app.crm.personnel import PersonnelError, _validate_executor
from app.crm.tasks_area import bulk_send_area_to_survey
from app.letters.oati import LetterError
from app.letters.review import (
    hide_letter,
    letter_row_to_out,
    list_letters_for_review,
    normalize_letter_list_limit,
    parse_letter_lonlat,
    set_letter_review,
)


def _session(role: str) -> UserSession:
    return UserSession(
        uuid="11111111-2222-3333-4444-555555555555",
        login="tester",
        role=role,
        work_zones=[],
    )


def _cursor_cm(cursor: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value = cursor
    cm.__exit__.return_value = False
    return cm


class LetterReviewHelperTests(unittest.TestCase):
    def test_parse_wgs84_lat_lon(self) -> None:
        self.assertEqual(parse_letter_lonlat("55.755800, 37.617300"), (37.6173, 55.7558))

    def test_parse_invalid(self) -> None:
        self.assertEqual(parse_letter_lonlat(""), (None, None))
        self.assertEqual(parse_letter_lonlat("55.7"), (None, None))
        self.assertEqual(parse_letter_lonlat("xx, yy"), (None, None))

    def test_limit_allowed(self) -> None:
        self.assertEqual(normalize_letter_list_limit(None), 50)
        self.assertEqual(normalize_letter_list_limit(20), 20)

    def test_limit_rejected(self) -> None:
        with self.assertRaises(LetterError) as ctx:
            normalize_letter_list_limit(7)
        self.assertEqual(ctx.exception.status_code, 422)

    def test_row_maps_payload_and_coords(self) -> None:
        out = letter_row_to_out(
            {
                "fid": 12,
                "task_key": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "report_id": 3,
                "created_by": "office1",
                "created_at": None,
                "review_status": "approved",
                "reviewed_by": "mgr",
                "reviewed_at": None,
                "payload": {
                    "street": "Тверская",
                    "address": "Тверская, 1",
                    "rayon": "Тверской",
                    "customer": "Заказчик",
                    "executor": "Исполнитель",
                    "description": "Яма",
                    "today": "15.09.2026",
                    "coordinates": "55.755800, 37.617300",
                },
            }
        )
        self.assertEqual(out["fid"], 12)
        self.assertEqual(out["street"], "Тверская")
        self.assertEqual(out["lon"], 37.6173)
        self.assertEqual(out["lat"], 55.7558)
        self.assertEqual(out["review_status"], "approved")


class LetterReviewStoreTests(unittest.TestCase):
    def test_list_uses_hidden_filter_and_limit(self) -> None:
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)
        with patch("app.letters.review.ensure_letter_review_columns", return_value=True):
            rows = list_letters_for_review(conn, limit=20)
        self.assertEqual(rows, [])
        sql = cursor.execute.call_args[0][0]
        self.assertIn("hidden_at IS NULL", sql)
        self.assertIn("ORDER BY created_at DESC", sql)
        self.assertEqual(cursor.execute.call_args[0][1], (20,))

    def test_set_review_404(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)
        with patch("app.letters.review.ensure_letter_review_columns", return_value=True):
            with self.assertRaises(LetterError) as ctx:
                set_letter_review(conn, 9, status="approved", login="mgr")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_set_review_clears_on_null(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "fid": 9,
            "task_key": "k",
            "report_id": 1,
            "created_by": "a",
            "created_at": None,
            "payload": {},
            "review_status": None,
            "reviewed_by": None,
            "reviewed_at": None,
        }
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)
        with patch("app.letters.review.ensure_letter_review_columns", return_value=True):
            out = set_letter_review(conn, 9, status=None, login="mgr")
        self.assertIsNone(out["review_status"])
        params = cursor.execute.call_args[0][1]
        self.assertEqual(params[0], None)

    def test_hide_keeps_row(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (4,)
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)
        with patch("app.letters.review.ensure_letter_review_columns", return_value=True):
            hide_letter(conn, 4, login="mgr")
        sql = cursor.execute.call_args[0][0]
        self.assertIn("hidden_at = NOW()", sql)
        self.assertNotIn("DELETE", sql.upper())


class LetterReviewAuthTests(unittest.TestCase):
    def test_route_requires_manager_or_admin(self) -> None:
        from app.routes import letter_review as letter_review_routes

        route = next(
            r
            for r in letter_review_routes.router.routes
            if getattr(r, "path", None) == "/api/letters"
        )
        dependant = route.dependant
        dep_calls = [d.call for d in dependant.dependencies if d.call is not None]
        self.assertIn(require_manager_or_admin, dep_calls)

    def test_office_rejected(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            require_manager_or_admin(_session("office"))
        self.assertEqual(ctx.exception.status_code, 403)


class ExecutorRoleTests(unittest.TestCase):
    def test_office_executor_rejected(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)
        with self.assertRaises(PersonnelError):
            _validate_executor(conn, "office1")
        sql, params = cursor.execute.call_args[0]
        self.assertIn("role = ANY(%s)", sql)
        self.assertEqual(params[1], ["field"])

    def test_field_executor_ok(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)
        _validate_executor(conn, "field1")

    def test_clear_executor_skips_lookup(self) -> None:
        conn = MagicMock()
        _validate_executor(conn, None)
        conn.cursor.assert_not_called()


class BulkSendSurveyTests(unittest.TestCase):
    def test_empty_rayon_rejected(self) -> None:
        conn = MagicMock()
        with self.assertRaises(PersonnelError):
            bulk_send_area_to_survey(conn, rayon="  ", executor="field1", login="mgr")

    def test_updates_only_free(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (5,)
        cursor.rowcount = 2
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)
        with (
            patch("app.crm.personnel._validate_executor"),
            patch("app.crm.tasks_area.ensure_tasks_area_audit_columns", return_value=True),
        ):
            result = bulk_send_area_to_survey(
                conn, rayon="Арбат", executor="field1", login="mgr"
            )
        self.assertEqual(result, {"updated": 2, "skipped": 3})
        update_sql = cursor.execute.call_args_list[-1][0][0]
        self.assertIn("COALESCE(status, '') = 'free'", update_sql)
        self.assertIn("status = 'wip'", update_sql)

    def test_non_field_executor_rejected(self) -> None:
        conn = MagicMock()
        with patch(
            "app.crm.personnel._validate_executor",
            side_effect=PersonnelError("Исполнитель «office1» не найден или недоступен для назначения"),
        ):
            with self.assertRaises(PersonnelError):
                bulk_send_area_to_survey(
                    conn, rayon="Арбат", executor="office1", login="mgr"
                )


if __name__ == "__main__":
    unittest.main()
