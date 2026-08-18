"""Tests for public Excel upload storage."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.excel_upload.store import (
    ExcelUploadError,
    save_excel_upload,
    sanitize_original_name,
)

XLSX_BYTES = b"PK\x03\x04" + b"workbook-placeholder"
XLS_BYTES = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"workbook-placeholder"
MAX_BYTES = 10 * 1024 * 1024
STAMP = datetime(2026, 8, 18, 6, 5, 12, tzinfo=timezone.utc)


class SanitizeOriginalNameTests(unittest.TestCase):
    def test_keeps_cyrillic_stem_and_suffix(self) -> None:
        self.assertEqual(sanitize_original_name("заявки.xlsx"), ("заявки", ".xlsx"))

    def test_strips_path_components(self) -> None:
        self.assertEqual(
            sanitize_original_name("../../etc/passwd.xlsx"),
            ("passwd", ".xlsx"),
        )
        self.assertEqual(
            sanitize_original_name(r"C:\temp\report.xls"),
            ("report", ".xls"),
        )

    def test_rejects_non_excel_extension(self) -> None:
        with self.assertRaises(ExcelUploadError) as ctx:
            sanitize_original_name("notes.txt")
        self.assertIn(".xlsx", str(ctx.exception))

    def test_rejects_empty_name(self) -> None:
        with self.assertRaises(ExcelUploadError):
            sanitize_original_name("")
        with self.assertRaises(ExcelUploadError):
            sanitize_original_name(None)


class SaveExcelUploadTests(unittest.TestCase):
    def test_saves_xlsx_with_utc_timestamp(self) -> None:
        with TemporaryDirectory() as tmp:
            dest_dir = Path(tmp)
            saved = save_excel_upload(
                XLSX_BYTES,
                "заявки.xlsx",
                dest_dir,
                MAX_BYTES,
                now=STAMP,
            )
            self.assertEqual(saved.filename, "20260818_060512_заявки.xlsx")
            self.assertEqual(saved.size, len(XLSX_BYTES))
            self.assertEqual(saved.path.read_bytes(), XLSX_BYTES)
            self.assertFalse(list(dest_dir.glob(".tmp_*")))

    def test_saves_xls_with_ole_magic(self) -> None:
        with TemporaryDirectory() as tmp:
            saved = save_excel_upload(
                XLS_BYTES,
                "old.xls",
                Path(tmp),
                MAX_BYTES,
                now=STAMP,
            )
            self.assertEqual(saved.filename, "20260818_060512_old.xls")
            self.assertEqual(saved.path.read_bytes(), XLS_BYTES)

    def test_rejects_wrong_magic_bytes(self) -> None:
        with TemporaryDirectory() as tmp:
            dest_dir = Path(tmp)
            with self.assertRaises(ExcelUploadError) as ctx:
                save_excel_upload(b"not-an-excel", "fake.xlsx", dest_dir, MAX_BYTES, now=STAMP)
            self.assertIn(".xlsx", str(ctx.exception))
            self.assertEqual(list(dest_dir.iterdir()), [])

    def test_rejects_empty_and_oversized(self) -> None:
        with TemporaryDirectory() as tmp:
            dest_dir = Path(tmp)
            with self.assertRaises(ExcelUploadError):
                save_excel_upload(b"", "a.xlsx", dest_dir, MAX_BYTES, now=STAMP)
            with self.assertRaises(ExcelUploadError) as ctx:
                save_excel_upload(XLSX_BYTES + b"x" * 20, "a.xlsx", dest_dir, max_bytes=10, now=STAMP)
            self.assertIn("большой", str(ctx.exception))

    def test_does_not_overwrite_existing_file(self) -> None:
        with TemporaryDirectory() as tmp:
            dest_dir = Path(tmp)
            first = save_excel_upload(
                XLSX_BYTES,
                "report.xlsx",
                dest_dir,
                MAX_BYTES,
                now=STAMP,
            )
            second = save_excel_upload(
                XLSX_BYTES + b"2",
                "report.xlsx",
                dest_dir,
                MAX_BYTES,
                now=STAMP,
            )
            self.assertEqual(first.filename, "20260818_060512_report.xlsx")
            self.assertEqual(second.filename, "20260818_060512_report_2.xlsx")
            self.assertEqual(first.path.read_bytes(), XLSX_BYTES)
            self.assertEqual(second.path.read_bytes(), XLSX_BYTES + b"2")


if __name__ == "__main__":
    unittest.main()
