from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "custom_components" / "bitcoin_stack_tracker" / "reference_price.py"
spec = importlib.util.spec_from_file_location("bst_reference_price", MODULE)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class HistoricalReferencePriceTests(unittest.TestCase):
    def test_nearest_same_day_intraday_sample_wins(self):
        history = {
            "price_samples": {"EUR": {
                "2026-01-21T20:00:00+00:00": "79000",
                "2026-01-21T21:20:00+00:00": "80000",
                "2026-01-22T00:00:00+00:00": "81000",
            }},
            "prices": {"EUR": {"2026-01-21": "78000"}},
        }
        result = mod.historical_reference_price(history, "eur", "2026-01-21T21:21:21+00:00")
        self.assertTrue(result["available"])
        self.assertEqual(result["source"], "intraday")
        self.assertEqual(result["price"], Decimal("80000"))

    def test_exact_daily_fallback(self):
        history = {"prices": {"EUR": {"2026-01-21": "80000"}}}
        result = mod.historical_reference_price(history, "EUR", "2026-01-21T12:00:00+00:00")
        self.assertEqual(result["source"], "daily")
        self.assertEqual(result["price"], Decimal("80000"))

    def test_old_booking_never_uses_live_price(self):
        result = mod.historical_reference_price(
            {}, "EUR", "2026-01-21T12:00:00+00:00", live_price="99999",
            now=datetime(2026, 8, 14, 3, 0, tzinfo=timezone.utc),
        )
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "price_missing")

    def test_today_may_use_live_price(self):
        result = mod.historical_reference_price(
            {}, "EUR", "2026-08-14T02:00:00+00:00", live_price="70000",
            now=datetime(2026, 8, 14, 3, 0, tzinfo=timezone.utc),
        )
        self.assertTrue(result["available"])
        self.assertEqual(result["source"], "live")
        self.assertEqual(result["price"], Decimal("70000"))


if __name__ == "__main__":
    unittest.main()
