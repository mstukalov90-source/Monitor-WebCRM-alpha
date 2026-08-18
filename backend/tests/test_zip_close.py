"""Tests for admin ZIP-close preview/apply (no live DB writes)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.auth.deps import require_admin
from app.auth.session import UserSession
from app.field_zip_restore.parse import DrawSubmission, FieldZipArchive
from app.field_zip_restore.plan import RestorePlan
from app.field_zip_restore.service import (
    ZipCloseError,
    apply_preview,
    ensure_field_user,
    plan_to_item,
    preview_files,
    read_zip_uploads,
)
from app.field_zip_restore.staging import (
    PREVIEW_TTL,
    get_preview,
    reset_previews_for_tests,
    save_preview,
)


def _session(role: str, login: str = "admin") -> UserSession:
    return UserSession(
        uuid="11111111-2222-3333-4444-555555555555",
        login=login,
        role=role,
        work_zones=[],
    )


def _cursor_cm(cursor: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value = cursor
    cm.__exit__.return_value = False
    return cm


def _archive(path: Path, *, kind: str = "field_order") -> FieldZipArchive:
    key = "11111111-1111-1111-1111-111111111111"
    submissions = ()
    if kind == "field_order":
        submissions = (
            DrawSubmission(
                id="sub-1",
                kind="EVENT_POINT",
                event_type="NO_DISRUPTION",
                created_at_ms=1,
                lat=55.0,
                lon=37.0,
                comment=None,
                photos=(),
            ),
        )
    return FieldZipArchive(
        path=path,
        kind=kind,
        raw_task_key=key,
        order_uuid=key,
        order_number="U-TEST",
        rayon="Беговой",
        exported_at=None,
        submissions=submissions,
        features=(),
        track=None,
    )


def _plan(path: Path, *, will_write: bool, skip_reason: str | None = None) -> RestorePlan:
    return RestorePlan(
        archive=_archive(path),
        actions=["insert report"] if will_write else ["skip"],
        photos=[],
        sql_statements=["SELECT 1"] if will_write else [],
        skip_reason=skip_reason,
        original_name=path.name,
    )


class ReadUploadsTests(unittest.TestCase):
    def test_rejects_non_zip(self) -> None:
        with self.assertRaises(ZipCloseError) as ctx:
            read_zip_uploads(
                [("notes.txt", b"hello")],
                max_files=20,
                max_bytes=50 * 1024 * 1024,
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_accepts_zip_magic(self) -> None:
        payloads = read_zip_uploads(
            [("a.zip", b"PK\x03\x04body")],
            max_files=20,
            max_bytes=50 * 1024 * 1024,
        )
        self.assertEqual(payloads[0][0], "a.zip")


class ZipCloseAuthTests(unittest.TestCase):
    def test_require_admin_allows_admin(self) -> None:
        self.assertEqual(require_admin(_session("admin")).role, "admin")

    def test_require_admin_rejects_office(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            require_admin(_session("office"))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_routes_require_admin(self) -> None:
        from app.auth.deps import require_admin as require_dep
        from app.routes import zip_close as zip_close_routes

        paths = {
            getattr(route, "path", None)
            for route in zip_close_routes.router.routes
        }
        self.assertIn("/api/admin/zip-close/preview", paths)
        self.assertIn("/api/admin/zip-close/apply", paths)
        for route in zip_close_routes.router.routes:
            dependant = getattr(route, "dependant", None)
            if dependant is None:
                continue
            dep_calls = [d.call for d in dependant.dependencies if d.call is not None]
            self.assertIn(require_dep, dep_calls)


class StagingTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_previews_for_tests()
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(reset_previews_for_tests)

    def test_save_and_get(self) -> None:
        staged = save_preview(
            username="ZhuchenkoAA",
            admin_login="admin",
            files=[("У0219455.zip", b"PK\x03\x04payload")],
            staging_root=Path(self.tmp.name),
        )
        loaded = get_preview(staged.preview_id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.username, "ZhuchenkoAA")
        self.assertEqual(loaded.files[0].original_name, "У0219455.zip")
        self.assertEqual(loaded.files[0].path.read_bytes(), b"PK\x03\x04payload")

    def test_expired_preview_is_gone(self) -> None:
        staged = save_preview(
            username="ZhuchenkoAA",
            admin_login="admin",
            files=[("a.zip", b"PK\x03\x04x")],
            staging_root=Path(self.tmp.name),
        )
        staged.created_at = datetime.now(timezone.utc) - PREVIEW_TTL - timedelta(seconds=1)
        self.assertIsNone(get_preview(staged.preview_id))


class EnsureFieldUserTests(unittest.TestCase):
    def test_rejects_missing_user(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)
        with self.assertRaises(ZipCloseError) as ctx:
            ensure_field_user(conn, "nobody")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_returns_login(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = {"login": "ZhuchenkoAA"}
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)
        self.assertEqual(ensure_field_user(conn, "ZhuchenkoAA"), "ZhuchenkoAA")


class PlanItemTests(unittest.TestCase):
    def test_mismatch_when_tasks_field_missing(self) -> None:
        plan = RestorePlan(
            archive=_archive(Path("missing.zip")),
            actions=[],
            photos=[],
            sql_statements=[],
            skip_reason="crm.tasks_field row not found",
            original_name="missing.zip",
        )
        item = plan_to_item(plan)
        self.assertEqual(item["outcome"], "mismatch")
        self.assertFalse(item["will_write"])


class PreviewApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_previews_for_tests()
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(reset_previews_for_tests)
        self.conn = MagicMock()

    def test_preview_does_not_write(self) -> None:
        calls: list[str] = []

        class FakeClient:
            def psql_json(self, sql: str):
                return {}

            def apply_sql(self, statements):
                calls.append("sql")

            def copy_photos(self, files, dest_dir):
                calls.append("photos")

        path = Path(self.tmp.name) / "ok.zip"
        path.write_bytes(b"PK")
        plan = _plan(path, will_write=True)

        with (
            patch("app.field_zip_restore.service.ensure_field_user", return_value="ZhuchenkoAA"),
            patch("app.field_zip_restore.service.PgClient", return_value=FakeClient()),
            patch("app.field_zip_restore.service._plan_for_file", return_value=plan),
            patch("app.field_zip_restore.service.apply_plan") as apply_mock,
        ):
            result = preview_files(
                self.conn,
                username="ZhuchenkoAA",
                admin_login="admin",
                files=[("ok.zip", b"PK\x03\x04x")],
                staging_root=Path(self.tmp.name),
            )
        self.assertTrue(result["can_apply"])
        self.assertEqual(result["items"][0]["will_write"], True)
        apply_mock.assert_not_called()
        self.assertEqual(calls, [])

    def test_apply_writes_only_matching(self) -> None:
        staged = save_preview(
            username="ZhuchenkoAA",
            admin_login="admin",
            files=[("ok.zip", b"PK\x03\x04a"), ("skip.zip", b"PK\x03\x04b")],
            staging_root=Path(self.tmp.name),
        )
        write_plan = _plan(staged.files[0].path, will_write=True)
        write_plan.original_name = "ok.zip"
        skip_plan = _plan(
            staged.files[1].path,
            will_write=False,
            skip_reason="already restored (no tasks_field, reports present)",
        )
        skip_plan.original_name = "skip.zip"
        applied: list[str] = []

        def fake_apply(plan, client, photo_dir):
            applied.append(plan.original_name or plan.archive.path.name)

        with (
            patch("app.field_zip_restore.service.ensure_field_user", return_value="ZhuchenkoAA"),
            patch("app.field_zip_restore.service.PgClient"),
            patch(
                "app.field_zip_restore.service._plan_for_file",
                side_effect=[write_plan, skip_plan],
            ),
            patch("app.field_zip_restore.service.apply_plan", side_effect=fake_apply),
        ):
            result = apply_preview(
                self.conn,
                preview_id=staged.preview_id,
                username="ZhuchenkoAA",
                admin_login="admin",
                photo_dir=Path(self.tmp.name) / "photos",
            )

        self.assertEqual(applied, ["ok.zip"])
        self.assertEqual(result["applied_count"], 1)
        self.assertTrue(result["items"][0]["applied"])
        self.assertFalse(result["items"][1]["applied"])
        self.assertIsNone(get_preview(staged.preview_id))

    def test_apply_rejects_expired_preview(self) -> None:
        with (
            patch("app.field_zip_restore.service.ensure_field_user", return_value="ZhuchenkoAA"),
            self.assertRaises(ZipCloseError) as ctx,
        ):
            apply_preview(
                self.conn,
                preview_id="00000000-0000-0000-0000-000000000000",
                username="ZhuchenkoAA",
                admin_login="admin",
                photo_dir=Path(self.tmp.name),
            )
        self.assertIn("устарела", str(ctx.exception))

    def test_apply_rejects_username_mismatch(self) -> None:
        staged = save_preview(
            username="ZhuchenkoAA",
            admin_login="admin",
            files=[("a.zip", b"PK\x03\x04x")],
            staging_root=Path(self.tmp.name),
        )
        with (
            patch("app.field_zip_restore.service.ensure_field_user", return_value="OtherUser"),
            self.assertRaises(ZipCloseError) as ctx,
        ):
            apply_preview(
                self.conn,
                preview_id=staged.preview_id,
                username="OtherUser",
                admin_login="admin",
                photo_dir=Path(self.tmp.name),
            )
        self.assertIn("не совпадает", str(ctx.exception))
