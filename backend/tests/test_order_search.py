"""Unit tests for order-group search helpers."""

from __future__ import annotations

import unittest

from app.crm.order_search import like_pattern, sanitize_search_query


class OrderSearchQueryTests(unittest.TestCase):
    def test_strips_like_wildcards(self) -> None:
        self.assertEqual(sanitize_search_query("  2409%0164_  "), "24090164")
        self.assertEqual(sanitize_search_query("БС-СТРОЙ"), "БС-СТРОЙ")

    def test_like_pattern_wraps_percent(self) -> None:
        self.assertEqual(like_pattern("24090164"), "%24090164%")

    def test_short_after_sanitize(self) -> None:
        self.assertEqual(sanitize_search_query("%_"), "")


if __name__ == "__main__":
    unittest.main()
