"""Tests for DIT AI photo metadata and HTTP proxy rules."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.photos.ai_photo import PhotoFetchError
from app.photos.dit_photo import (
    DitPhotoMeta,
    fetch_dit_photo_bytes,
    image_name_from_url,
    is_http_image_url,
    issues_to_bboxes,
    normalize_result_id,
    resolve_dit_photo,
)


def _cursor_cm(cursor: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value = cursor
    cm.__exit__.return_value = False
    return cm


class NormalizeDitHelpersTests(unittest.TestCase):
    def test_result_id_rejects_paths(self) -> None:
        self.assertIsNone(normalize_result_id(""))
        self.assertIsNone(normalize_result_id("../secret"))
        self.assertIsNone(normalize_result_id("a/b"))
        self.assertEqual(normalize_result_id("  abc-1  "), "abc-1")

    def test_http_url_only(self) -> None:
        self.assertTrue(is_http_image_url("https://cdn.example/a.jpg"))
        self.assertTrue(is_http_image_url("http://cdn.example/a.jpg"))
        self.assertFalse(is_http_image_url("file:///tmp/a.jpg"))
        self.assertFalse(is_http_image_url("ftp://host/a.jpg"))
        self.assertFalse(is_http_image_url("not-a-url"))

    def test_image_name_from_url(self) -> None:
        self.assertEqual(image_name_from_url("https://cdn.example/photos/x.jpg"), "x.jpg")
        self.assertEqual(image_name_from_url("https://cdn.example/"), "photo.jpg")

    def test_issues_to_bboxes(self) -> None:
        self.assertEqual(issues_to_bboxes([[1, 2, 3, 4]]), [[1, 2, 3, 4]])
        self.assertEqual(
            issues_to_bboxes({"issues": [{"x1": 1, "y1": 2, "x2": 3, "y2": 4}]}),
            [{"x1": 1, "y1": 2, "x2": 3, "y2": 4}],
        )
        self.assertEqual(issues_to_bboxes(None), [])


class ResolveDitPhotoTests(unittest.TestCase):
    def test_reads_issues_column(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "result_id": "res-1",
            "image": "https://cdn.example/a.jpg",
            "issues": [{"bbox": [1, 2, 3, 4]}],
        }
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        meta = resolve_dit_photo(conn, "res-1")
        assert meta is not None
        self.assertEqual(meta.result_id, "res-1")
        self.assertEqual(meta.image_url, "https://cdn.example/a.jpg")
        self.assertEqual(meta.image_name, "a.jpg")
        self.assertEqual(meta.bboxes, [{"bbox": [1, 2, 3, 4]}])
        payload = meta.to_dict("/api/photos/dit/res-1/image")
        self.assertEqual(payload["bboxes"], [{"bbox": [1, 2, 3, 4]}])
        self.assertEqual(payload["url"], "/api/photos/dit/res-1/image")

    def test_missing_row(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)
        self.assertIsNone(resolve_dit_photo(conn, "missing"))

    def test_invalid_id_skips_query(self) -> None:
        conn = MagicMock()
        self.assertIsNone(resolve_dit_photo(conn, "../nope"))
        conn.cursor.assert_not_called()


class FetchDitPhotoBytesTests(unittest.TestCase):
    def test_rejects_non_http_url(self) -> None:
        meta = DitPhotoMeta(
            result_id="1",
            image_url="file:///tmp/secret.jpg",
            image_name="secret.jpg",
        )
        with self.assertRaises(PhotoFetchError) as ctx:
            fetch_dit_photo_bytes(meta)
        self.assertEqual(ctx.exception.status_code, 400)

    @patch("app.photos.dit_photo.urllib.request.urlopen")
    def test_fetches_http_url_from_meta(self, urlopen: MagicMock) -> None:
        response = MagicMock()
        response.read.return_value = b"jpeg-bytes"
        response.headers = {"Content-Type": "image/jpeg"}
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        urlopen.return_value = response

        meta = DitPhotoMeta(
            result_id="1",
            image_url="https://cdn.example/a.jpg",
            image_name="a.jpg",
        )
        content, media_type = fetch_dit_photo_bytes(meta)
        self.assertEqual(content, b"jpeg-bytes")
        self.assertEqual(media_type, "image/jpeg")
        request = urlopen.call_args[0][0]
        self.assertEqual(request.full_url, "https://cdn.example/a.jpg")


if __name__ == "__main__":
    unittest.main()
