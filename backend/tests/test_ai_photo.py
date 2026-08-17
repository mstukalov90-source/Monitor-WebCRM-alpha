"""Tests for AI photo metadata, including detection bboxes."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.photos.ai_photo import AiPhotoMeta, normalize_bboxes, resolve_ai_photo


def _cursor_cm(cursor: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value = cursor
    cm.__exit__.return_value = False
    return cm


SAMPLE_UUID = "d01cb344-e047-4ade-a0bf-387cbd607bf2"


class NormalizeBboxesTests(unittest.TestCase):
    def test_none_and_empty(self) -> None:
        self.assertEqual(normalize_bboxes(None), [])
        self.assertEqual(normalize_bboxes(""), [])
        self.assertEqual(normalize_bboxes("   "), [])

    def test_list_passthrough(self) -> None:
        boxes = [[10, 20, 30, 40], {"x": 1, "y": 2, "w": 3, "h": 4}]
        self.assertEqual(normalize_bboxes(boxes), boxes)

    def test_json_string_and_wrapped_dict(self) -> None:
        self.assertEqual(
            normalize_bboxes('[{"x1": 1, "y1": 2, "x2": 3, "y2": 4}]'),
            [{"x1": 1, "y1": 2, "x2": 3, "y2": 4}],
        )
        self.assertEqual(
            normalize_bboxes({"boxes": [[0, 0, 1, 1]]}),
            [[0, 0, 1, 1]],
        )
        self.assertEqual(normalize_bboxes({"detections": [{"bbox": [1, 2, 3, 4]}]}), [{"bbox": [1, 2, 3, 4]}])

    def test_invalid_payload(self) -> None:
        self.assertEqual(normalize_bboxes("{not-json"), [])
        self.assertEqual(normalize_bboxes({"foo": 1}), [])
        self.assertEqual(normalize_bboxes(12), [])


class AiPhotoMetaToDictTests(unittest.TestCase):
    def test_includes_bboxes(self) -> None:
        meta = AiPhotoMeta(
            uuid=SAMPLE_UUID,
            image_name="a.jpg",
            date=None,
            azimuth_deg=118.4,
            order_id=None,
            bboxes=[{"x": 10, "y": 20, "w": 30, "h": 40}],
        )
        payload = meta.to_dict("/api/photos/ai/x/image")
        self.assertEqual(payload["bboxes"], [{"x": 10, "y": 20, "w": 30, "h": 40}])
        self.assertEqual(payload["url"], "/api/photos/ai/x/image")

    def test_null_bboxes_become_empty_list(self) -> None:
        meta = AiPhotoMeta(
            uuid=SAMPLE_UUID,
            image_name="a.jpg",
            date=None,
            azimuth_deg=None,
            order_id=None,
        )
        self.assertEqual(meta.to_dict("/img")["bboxes"], [])


class ResolveAiPhotoTests(unittest.TestCase):
    def test_reads_bboxes_column(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "uuid": SAMPLE_UUID,
            "image_name": "PVN_hd_ZAO_8_96_1.jpg",
            "date": "2024-05-01",
            "azimuth_deg": 68.5,
            "order_id": "ord-1",
            "bboxes": None,
        }
        conn = MagicMock()
        conn.cursor.return_value = _cursor_cm(cursor)

        meta = resolve_ai_photo(conn, SAMPLE_UUID)
        assert meta is not None
        self.assertEqual(meta.bboxes, [])
        sql = cursor.execute.call_args[0][0]
        self.assertIn("bboxes", sql)
        self.assertEqual(meta.to_dict("/img")["bboxes"], [])

    def test_invalid_uuid(self) -> None:
        self.assertIsNone(resolve_ai_photo(MagicMock(), "not-a-uuid"))


if __name__ == "__main__":
    unittest.main()
