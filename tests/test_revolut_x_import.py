from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


PARSER = Path(__file__).resolve().parents[1] / "custom_components" / "bitcoin_stack_tracker" / "csv_import.py"
spec = importlib.util.spec_from_file_location("bitcoin_stack_tracker_csv_import", PARSER)
assert spec and spec.loader
csv_import = importlib.util.module_from_spec(spec)
spec.loader.exec_module(csv_import)


class RevolutXImportTests(unittest.TestCase):
    def parse(self, body: str):
        return csv_import.parse_transaction_upload(body.encode("utf-8"), "crypto_account_statement_2026.csv")

    def test_detects_revolut_x_and_normalizes_buy_sell(self):
        result = self.parse(
            'Symbol,Type,Quantity,Price,Value,Fees,Date\n'
            'BTC,Buy,0.001,100000,100,0.09,"21 Jan 2026, 21:21:21"\n'
            'BTC,Sell,0.0005,120000,60,0.05,"22 Jan 2026, 10:11:12"\n'
        )
        self.assertEqual(result["source"], "revolut_x")
        self.assertEqual(result["source_label"], "Revolut X")
        self.assertEqual(result["recognized"], 2)
        self.assertEqual(result["valid"], 2)
        self.assertEqual(result["skipped"], 0)

        buy, sell = result["rows"]
        self.assertEqual(buy["type"], "purchase")
        self.assertEqual(buy["amount_btc"], "0.001")
        self.assertEqual(buy["currency"], "EUR")
        self.assertEqual(buy["price"], "100000")
        self.assertEqual(buy["fee"], "0.09")
        self.assertEqual(buy["fiat_amount"], "100.09")
        self.assertEqual(buy["timestamp"], "2026-01-21T21:21:21+00:00")

        self.assertEqual(sell["type"], "sale")
        self.assertEqual(sell["amount_btc"], "0.0005")
        self.assertEqual(sell["price"], "120000")
        self.assertEqual(sell["fee"], "0.05")
        self.assertEqual(sell["fiat_amount"], "59.95")

    def test_value_is_gross_and_fee_is_applied_once(self):
        result = self.parse(
            'Symbol,Type,Quantity,Price,Value,Fees,Date\n'
            'BTC,Buy,0.002,50000,100,1.25,"21 Jan 2026, 21:21:21"\n'
            'BTC,Sell,0.002,50000,100,1.25,"22 Jan 2026, 21:21:21"\n'
        )
        buy, sell = result["rows"]
        self.assertEqual(buy["fiat_amount"], "101.25")
        self.assertEqual(sell["fiat_amount"], "98.75")
        self.assertEqual(buy["import_hints"]["gross_trade_value"], "100")
        self.assertTrue(buy["import_hints"]["value_excludes_fee"])

    def test_accepts_revolut_x_month_first_ampm_date(self):
        result = self.parse(
            'Symbol,Type,Quantity,Price,Value,Fees,Date\n'
            'BTC,Buy,0.001,100000,100,0.09,"Jan 3, 2025, 6:18:28 PM"\n'
        )
        self.assertEqual(result["rows"][0]["timestamp"], "2025-01-03T18:18:28+00:00")
        self.assertTrue(result["rows"][0]["valid"])

    def test_skips_non_bitcoin_assets(self):
        result = self.parse(
            'Symbol,Type,Quantity,Price,Value,Fees,Date\n'
            'ETH,Buy,1,3000,3000,2,"21 Jan 2026, 21:21:21"\n'
            'BTC,Buy,0.001,100000,100,0.09,"21 Jan 2026, 21:21:21"\n'
        )
        self.assertEqual(result["recognized"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["rows"][0]["source"], "Revolut X")

    def test_uses_value_to_recover_missing_price(self):
        result = self.parse(
            'Symbol,Type,Quantity,Price,Value,Fees,Date\n'
            'BTC,Buy,0.002,,100,0.50,"21 Jan 2026, 21:21:21"\n'
        )
        row = result["rows"][0]
        self.assertEqual(row["price"], "50000")
        self.assertEqual(row["fiat_amount"], "100.50")
        self.assertTrue(row["valid"])


if __name__ == "__main__":
    unittest.main()
