"""Parser and plan tests for field ZIP restore (no prod writes)."""

from __future__ import annotations

import io
import json
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app import field_zip_restore as restore

ROOT = Path(__file__).resolve().parents[2]

LOST = ROOT / "tmp" / "lost_tasks"
MOSCOW = ZoneInfo("Europe/Moscow")


def _write_zip(files: dict[str, str | bytes]) -> Path:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, payload in files.items():
            data = payload.encode("utf-8") if isinstance(payload, str) else payload
            zf.writestr(name, data)
    buf.seek(0)
    path = ROOT / "tmp" / "lost_tasks_test_synthetic.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue())
    return path


class NormalizeKeyTests(unittest.TestCase):
    def test_strips_area_prefix(self) -> None:
        raw = "area:fa5cb9ac-c27a-466d-8e12-59b7c56417c1"
        self.assertEqual(
            restore.normalize_order_key(raw),
            "fa5cb9ac-c27a-466d-8e12-59b7c56417c1",
        )

    def test_plain_uuid(self) -> None:
        key = "ad75dbd2-1bab-433e-9b2f-fdfd46cafaf0"
        self.assertEqual(restore.normalize_order_key(key), key)

    def test_rejects_garbage(self) -> None:
        self.assertIsNone(restore.normalize_order_key("not-a-uuid"))


class EventAndPhotoTests(unittest.TestCase):
    def test_clear_when_no_disruption(self) -> None:
        item = restore.DrawSubmission(
            id="a",
            kind="EVENT_POINT",
            event_type="NO_DISRUPTION",
            created_at_ms=1,
            lat=55.0,
            lon=37.0,
            comment=None,
            photos=(),
        )
        self.assertTrue(restore.should_complete_as_clear([item]))
        self.assertEqual(restore.event_comment(item), "Разрытие отсутствует")

    def test_observed_when_disruption(self) -> None:
        item = restore.DrawSubmission(
            id="a",
            kind="EVENT_POINT",
            event_type="DISRUPTION",
            created_at_ms=1,
            lat=55.0,
            lon=37.0,
            comment=None,
            photos=(),
        )
        self.assertFalse(restore.should_complete_as_clear([item]))
        self.assertEqual(restore.event_comment(item), "Разрытие")

    def test_primary_photo_prefers_event(self) -> None:
        photos = (
            restore.ZipPhoto(slot="COMMUNICATION", zip_path="c.jpg"),
            restore.ZipPhoto(slot="EVENT", zip_path="e.jpg"),
        )
        self.assertEqual(restore.primary_photo(photos).zip_path, "e.jpg")

    def test_photo_uuid_stable(self) -> None:
        a = restore.photo_uuid_for("У0219455", "photos/draw/x.jpg")
        b = restore.photo_uuid_for("У0219455", "photos/draw/x.jpg")
        self.assertEqual(a, b)
        self.assertNotEqual(a, restore.photo_uuid_for("other", "photos/draw/x.jpg"))

    def test_taken_at_from_capture_filename(self) -> None:
        stamp = restore.taken_at_from_name(
            "photos/draw/фото_разрытия_capture_20260817_150533_601.jpg",
            None,
        )
        self.assertIsNotNone(stamp)
        local = stamp.astimezone(MOSCOW)
        self.assertEqual(local.strftime("%Y%m%d%H%M%S"), "20260817150533")


class RealZipParseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not LOST.is_dir():
            raise unittest.SkipTest("tmp/lost_tasks is missing")
        cls.archives = {
            path.name: restore.parse_zip(path) for path in sorted(LOST.glob("*.zip"))
        }

    def test_parses_five_archives(self) -> None:
        self.assertGreaterEqual(len(self.archives), 5)

    def test_no_disruption_order(self) -> None:
        archive = self.archives["У0219455.zip"]
        self.assertEqual(archive.kind, "field_order")
        self.assertEqual(archive.order_uuid, "ad75dbd2-1bab-433e-9b2f-fdfd46cafaf0")
        self.assertTrue(archive.as_clear)
        self.assertEqual(len(archive.submissions), 1)
        self.assertEqual(archive.submissions[0].event_type, "NO_DISRUPTION")
        self.assertGreaterEqual(len(archive.submissions[0].photos), 1)

    def test_disruption_orders(self) -> None:
        for name, key in (
            ("У0735112_3.zip", "4fd2137e-ba06-45b4-a345-564e7de2e056"),
            ("У0761707_1.zip", "6e7e1dfd-9fc2-4e0c-8a28-170d9606580f"),
        ):
            archive = self.archives[name]
            self.assertEqual(archive.kind, "field_order")
            self.assertEqual(archive.order_uuid, key)
            self.assertFalse(archive.as_clear)
            self.assertEqual(archive.submissions[0].event_type, "DISRUPTION")
            self.assertGreaterEqual(len(archive.submissions[0].photos), 5)

    def test_area_with_real_track(self) -> None:
        archive = self.archives["area_fa5cb9a.zip"]
        self.assertEqual(archive.kind, "area")
        self.assertEqual(archive.order_uuid, "fa5cb9ac-c27a-466d-8e12-59b7c56417c1")
        self.assertIsNotNone(archive.track)
        self.assertGreaterEqual(len(archive.track.points), 1000)
        self.assertFalse(restore.is_junk_track(archive))
        skip, _ = restore.should_skip_area_close(archive, "wip_field")
        self.assertFalse(skip)

    def test_junk_area_is_skipped(self) -> None:
        archive = self.archives["area_2408263.zip"]
        self.assertEqual(archive.kind, "area")
        self.assertEqual(archive.order_uuid, "2408263b-7664-426e-96ad-e9b7cedc16ac")
        self.assertTrue(restore.is_junk_track(archive))
        skip, reason = restore.should_skip_area_close(archive, "free")
        self.assertTrue(skip)
        self.assertIn("skip", reason.lower())

    def test_company_from_feature_attributes(self) -> None:
        archive = self.archives["У0219455.zip"]
        company = restore.company_from_features(archive.features)
        self.assertIsNotNone(company)
        self.assertIn("АВТОМОБИЛЬНЫЕ ДОРОГИ", company)


class PlanBuilderTests(unittest.TestCase):
    def test_field_clear_sql(self) -> None:
        archive = restore.parse_zip(LOST / "У0219455.zip")
        state = {
            "field": {
                "key": archive.order_uuid,
                "task_key": "d50c2032-e7a1-4680-8b14-8f198522d638",
            },
            "task": {"key": "d50c2032-e7a1-4680-8b14-8f198522d638", "field_observed": False},
            "in_clear": False,
            "report_tasks": [],
        }
        plan = restore.build_field_plan(archive, "ZhuchenkoAA", state)
        joined = "\n".join(plan.sql_statements)
        self.assertTrue(plan.will_write)
        self.assertIn("INSERT INTO mggt_field.photos", joined)
        self.assertIn("INSERT INTO mggt_field.reports", joined)
        self.assertIn("INSERT INTO crm.tasks_clear", joined)
        self.assertIn("DELETE FROM crm.tasks_field", joined)
        self.assertIn("field_observed = TRUE", joined)
        self.assertIn("field_disruption_absent", joined)
        self.assertIn(archive.submissions[0].id, joined)
        self.assertIn("d50c2032-e7a1-4680-8b14-8f198522d638", joined)
        self.assertGreaterEqual(len(plan.photos), 1)

    def test_field_disruption_does_not_touch_clear(self) -> None:
        archive = restore.parse_zip(LOST / "У0735112_3.zip")
        state = {
            "field": {"key": archive.order_uuid, "task_key": "b4629e73-857e-46d3-b9fd-7e7378015980"},
            "task": {"key": "b4629e73-857e-46d3-b9fd-7e7378015980"},
            "in_clear": False,
            "report_tasks": [],
        }
        plan = restore.build_field_plan(archive, "ZhuchenkoAA", state)
        joined = "\n".join(plan.sql_statements)
        self.assertNotIn("INSERT INTO crm.tasks_clear", joined)
        self.assertIn("DELETE FROM crm.tasks_field", joined)
        self.assertEqual(len(plan.photos), 5)

    def test_existing_report_still_closes_field(self) -> None:
        archive = restore.parse_zip(LOST / "У0219455.zip")
        state = {
            "field": {"key": archive.order_uuid, "task_key": "d50c2032-e7a1-4680-8b14-8f198522d638"},
            "task": {"key": "d50c2032-e7a1-4680-8b14-8f198522d638"},
            "in_clear": False,
            "report_tasks": [archive.submissions[0].id],
        }
        plan = restore.build_field_plan(archive, "ZhuchenkoAA", state)
        joined = "\n".join(plan.sql_statements)
        self.assertNotIn("INSERT INTO mggt_field.reports", joined)
        self.assertIn("INSERT INTO crm.tasks_clear", joined)

    def test_area_wip_field_writes_track_and_done(self) -> None:
        archive = restore.parse_zip(LOST / "area_fa5cb9a.zip")
        state = {
            "area": {"status": "wip_field", "executor": "ZhuchenkoAA"},
            "track_exists": False,
        }
        plan = restore.build_area_plan(archive, "ZhuchenkoAA", state)
        joined = "\n".join(plan.sql_statements)
        self.assertIn("INSERT INTO mggt_field.tracks", joined)
        self.assertIn("status = 'done'", joined)
        self.assertIn("wip_field", joined)

    def test_junk_area_offline_skip(self) -> None:
        archive = restore.parse_zip(LOST / "area_2408263.zip")
        state = {"area": {"status": "free"}, "track_exists": False}
        plan = restore.build_area_plan(archive, "ZhuchenkoAA", state)
        self.assertFalse(plan.will_write)
        self.assertIsNotNone(plan.skip_reason)


class SyntheticZipTests(unittest.TestCase):
    def test_parse_minimal_field_zip(self) -> None:
        key = "11111111-1111-1111-1111-111111111111"
        sid = "22222222-2222-2222-2222-222222222222"
        path = _write_zip(
            {
                "manifest.json": json.dumps(
                    {
                        "exportedAt": "2026-08-14T07:10:25Z",
                        "taskKey": key,
                        "orderNumber": "U-TEST",
                        "rayon": "Беговой",
                        "stats": {"drawSubmissions": 1, "photos": 1},
                    }
                ),
                "draw_submissions.json": json.dumps(
                    [
                        {
                            "id": sid,
                            "kind": "EVENT_POINT",
                            "eventType": "NO_DISRUPTION",
                            "createdAt": 1786691417534,
                            "points": [{"lat": 55.78, "lon": 37.56}],
                            "photos": [
                                {
                                    "slot": "EVENT",
                                    "zipPath": "photos/draw/capture_20260814_101012_1.jpg",
                                }
                            ],
                        }
                    ]
                ),
                "feature_edits.json": "[]",
                "photos/draw/capture_20260814_101012_1.jpg": b"jpeg-bytes",
            }
        )
        try:
            archive = restore.parse_zip(path)
            self.assertEqual(archive.kind, "field_order")
            self.assertTrue(archive.as_clear)
            self.assertEqual(archive.submissions[0].id, sid)
            stamp = restore.taken_at_from_name(archive.submissions[0].photos[0].zip_path, None)
            self.assertEqual(stamp.astimezone(MOSCOW), datetime(2026, 8, 14, 10, 10, 12, tzinfo=MOSCOW))
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
