from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys
import unittest

PARSER_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "bitcoin_stack_tracker"
sys.path.insert(0, str(PARSER_DIR))

from csv_import import parse_transaction_upload  # noqa: E402


class PeachBitcoinCsvImportTests(unittest.TestCase):
    def parse(self, name: str, text: str):
        return parse_transaction_upload(text.encode("utf-8"), name)

    def test_peach_header_detection_and_purchase_accounting(self):
        result = self.parse(
            "renamed-export.csv",
            """Date,Trade ID,Type,Amount,Price,Bitcoin Price,Currency,Premium
16/10/2025,trade-1,bought,100000,107.50,107500,EUR,7.5
""",
        )
        self.assertEqual(result["source"], "peach")
        self.assertEqual(result["recognized"], 1)
        row = result["rows"][0]
        self.assertEqual(row["source"], "Peach Bitcoin")
        self.assertEqual(row["type"], "purchase")
        self.assertEqual(row["timestamp"], "2025-10-16T00:00:00+00:00")
        self.assertEqual(row["amount_btc"], "0.001")
        self.assertEqual(row["currency"], "EUR")
        self.assertEqual(Decimal(row["price"]), Decimal("100000"))
        self.assertEqual(Decimal(row["fee"]), Decimal("7.50"))
        self.assertEqual(Decimal(row["fiat_amount"]), Decimal("107.50"))
        self.assertTrue(row["valid"], row["warnings"])
        self.assertEqual(
            Decimal(row["amount_btc"]) * Decimal(row["price"]) + Decimal(row["fee"]),
            Decimal("107.50"),
        )

    def test_peach_amount_is_always_satoshis_and_accepts_thousands_separator(self):
        result = self.parse(
            "peach-bitcoin.csv",
            """Date;Trade ID;Type;Amount;Price;Bitcoin Price;Currency;Premium
16/10/2025;p-2;bought;1.000.000;1075.00;107500;EUR;7.5
""",
        )
        row = result["rows"][0]
        self.assertEqual(row["amount_btc"], "0.01")
        self.assertEqual(Decimal(row["price"]), Decimal("100000"))
        self.assertEqual(Decimal(row["fee"]), Decimal("75.00"))
        self.assertTrue(row["valid"], row["warnings"])

    def test_peach_trade_id_is_hashed_and_keeps_equal_trades_distinct(self):
        result = self.parse(
            "peach.csv",
            """Date,Trade ID,Type,Amount,Price,Bitcoin Price,Currency,Premium
16/10/2025,trade-a,bought,100000,107.50,107500,EUR,7.5
16/10/2025,trade-b,bought,100000,107.50,107500,EUR,7.5
""",
        )
        first, second = result["rows"]
        self.assertNotEqual(first["import_ref_hash"], second["import_ref_hash"])
        self.assertEqual(len(first["import_ref_hash"]), 64)
        self.assertNotIn("trade-a", str(first))
        self.assertNotIn("trade-b", str(second))

    def test_peach_missing_premium_requires_review(self):
        result = self.parse(
            "peach.csv",
            """Date,Trade ID,Type,Amount,Price,Bitcoin Price,Currency,Premium
16/10/2025,trade-3,bought,100000,107.50,107500,EUR,
""",
        )
        row = result["rows"][0]
        self.assertFalse(row["valid"])
        self.assertTrue(any("Premium" in warning for warning in row["warnings"]))

    def test_peach_sale_uses_actual_fiat_proceeds_without_forcing_premium_fee(self):
        result = self.parse(
            "peach.csv",
            """Date,Trade ID,Type,Amount,Price,Bitcoin Price,Currency,Premium
16/10/2025,trade-4,sold,100000,105.00,105000,EUR,5
""",
        )
        row = result["rows"][0]
        self.assertEqual(row["type"], "sale")
        self.assertEqual(row["amount_btc"], "0.001")
        self.assertEqual(Decimal(row["price"]), Decimal("105000"))
        self.assertEqual(Decimal(row["fee"]), Decimal("0"))
        self.assertTrue(row["valid"], row["warnings"])


if __name__ == "__main__":
    unittest.main()
