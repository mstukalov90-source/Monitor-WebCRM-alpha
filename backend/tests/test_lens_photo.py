"""Tests for lens (Объектив) photo path resolution."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.photos.lens_photo import (
    DEFAULT_WINDOWS_ROOT,
    build_lens_photo_item,
    join_windows_path,
    normalize_lens_relative_path,
    reset_lens_photo_table_cache,
    resolve_lens_photo_table,
    resolve_lens_photos,
)


def _cursor_cm(cursor: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value = cursor
    cm.__exit__.return_value = False
    return cm


class NormalizeLensRelativePathTests(unittest.TestCase):
    def test_strips_uploads_prefix(self) -> None:
        self.assertEqual(
            normalize_lens_relative_path("uploads/2024/05/a.jpg"),
            "2024/05/a.jpg",
        )
        self.assertEqual(
            normalize_lens_relative_path(r"uploads\2024\05\a.jpg"),
            "2024/05/a.jpg",
        )
        self.assertEqual(
            normalize_lens_relative_path("Uploads/2024/a.jpg"),
            "2024/a.jpg",
        )
        self.assertEqual(
            normalize_lens_relative_path("/uploads/2024/a.jpg"),
            "2024/a.jpg",
        )

    def test_keeps_path_without_uploads(self) -> None:
        self.assertEqual(
            normalize_lens_relative_path("2024/05/a.jpg"),
            "2024/05/a.jpg",
        )

    def test_rejects_parent_and_absolute(self) -> None:
        self.assertIsNone(normalize_lens_relative_path("uploads/../secret.jpg"))
        self.assertIsNone(normalize_lens_relative_path("2024/../a.jpg"))
        self.assertIsNone(normalize_lens_relative_path(r"X:\Common\a.jpg"))
        self.assertIsNone(normalize_lens_relative_path(""))
        self.assertIsNone(normalize_lens_relative_path("uploads/"))

    def test_collapses_dot_segments(self) -> None:
        self.assertEqual(normalize_lens_relative_path("uploads/./a.jpg"), "a.jpg")


class JoinWindowsPathTests(unittest.TestCase):
    def test_joins_relative_under_root(self) -> None:
        self.assertEqual(
            join_windows_path(DEFAULT_WINDOWS_ROOT, "2024/05/a.jpg"),
            r"X:\Common\Объектив\2024\05\a.jpg",
        )

    def test_normalizes_root_slashes(self) -> None:
        self.assertEqual(
            join_windows_path(r"X:/Common/Объектив/", "a.jpg"),
            r"X:\Common\Объектив\a.jpg",
        )


class BuildLensPhotoItemTests(unittest.TestCase):
    def test_builds_item_from_uploads_path(self) -> None:
        item = build_lens_photo_item(12, "uploads/2024/05/a.jpg")
        assert item is not None
        self.assertEqual(item.relative_path, "2024/05/a.jpg")
        self.assertEqual(item.file_name, "a.jpg")
        self.assertEqual(item.windows_path, r"X:\Common\Объектив\2024\05\a.jpg")

    def test_skips_unsafe_path(self) -> None:
        self.assertIsNone(build_lens_photo_item(1, "../x.jpg"))


class ResolveLensPhotosTests(unittest.TestCase):
    def tearDown(self) -> None:
        reset_lens_photo_table_cache()

    def test_empty_id_returns_no_photos(self) -> None:
        result = resolve_lens_photos(MagicMock(), "  ")
        self.assertEqual(result.photos, [])
        self.assertEqual(result.external_report_id, "")

    def test_joins_report_photos_and_skips_unsafe(self) -> None:
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            {"id": 1, "file_path": "uploads/ok.jpg"},
            {"id": 2, "file_path": "../bad.jpg"},
            {"id": 3, "file_path": r"nested\dir\b.png"},
        ]
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        result = resolve_lens_photos(conn, "ext-1", photo_table="report_photos")
        self.assertEqual(result.external_report_id, "ext-1")
        self.assertEqual([p.id for p in result.photos], [1, 3])
        self.assertEqual(result.photos[0].windows_path, r"X:\Common\Объектив\ok.jpg")
        self.assertEqual(result.photos[1].relative_path, "nested/dir/b.png")
        sql = cursor.execute.call_args[0][0]
        self.assertIn("lens.report_photos", sql)
        self.assertEqual(cursor.execute.call_args[0][1], ("ext-1",))

    def test_detects_reports_photos_table_name(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = {"table_name": "reports_photos"}
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        self.assertEqual(resolve_lens_photo_table(conn), "reports_photos")
        self.assertEqual(resolve_lens_photo_table(conn), "reports_photos")
        cursor.execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
