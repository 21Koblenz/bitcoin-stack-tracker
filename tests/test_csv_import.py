from __future__ import annotations

from io import BytesIO
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

PARSER_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "bitcoin_stack_tracker"
APP = PARSER_DIR / "frontend"
sys.path.insert(0, str(PARSER_DIR))

from csv_import import _detect_source, parse_transaction_upload  # noqa: E402



class CsvImportTests(unittest.TestCase):
    def parse(self, name: str, text: str):
        return parse_transaction_upload(text.encode("utf-8"), name)

    def assert_single(self, result, source, kind, amount, currency, price):
        self.assertEqual(result["recognized"], 1)
        row = result["rows"][0]
        self.assertEqual(row["source"], source)
        self.assertEqual(row["type"], kind)
        self.assertEqual(row["amount_btc"], amount)
        self.assertEqual(row["currency"], currency)
        self.assertEqual(row["price"], price)
        self.assertTrue(row["valid"], row["warnings"])
        self.assertFalse(result["raw_file_retained"])

    def test_coinbase_with_metadata_preamble(self):
        result = self.parse("coinbase-report.csv", """Transactions report\nGenerated,2026-08-06\nTimestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,Spot Price at Transaction,Subtotal,Total (inclusive of fees and/or spread),Fees and/or Spread,Notes\n2026-08-01T12:00:00Z,Buy,BTC,0.01000000,EUR,60000,600,603,3,Sparplan\n""")
        self.assert_single(result, "Coinbase", "purchase", "0.01000000", "EUR", "60000")
        self.assertEqual(result["rows"][0]["fee"], "3")

    def test_kraken_trade_history(self):
        result = self.parse("kraken-trades.csv", """txid,ordertxid,pair,time,type,ordertype,price,cost,fee,vol\nt1,o1,XXBTZEUR,2026-08-01 12:00:00,buy,market,60000,600,1.5,0.01\n""")
        self.assert_single(result, "Kraken Trades", "purchase", "0.01", "EUR", "60000")

    def test_kraken_ledger_groups_two_asset_rows(self):
        result = self.parse("kraken-ledgers.csv", """txid,refid,time,type,subtype,aclass,asset,wallet,amount,fee,balance\na,r1,2026-08-01 12:00:00,trade,,currency,XXBT,spot,0.01000000,0,1\nb,r1,2026-08-01 12:00:00,trade,,currency,ZEUR,spot,-600.00,1.50,1000\n""")
        self.assert_single(result, "Kraken Ledger", "purchase", "0.01000000", "EUR", "60000")
        self.assertEqual(result["rows"][0]["fee"], "1.50")

    def test_binance_trade_history(self):
        result = self.parse("binance-trades.csv", """Date(UTC),Pair,Side,Price,Executed,Amount,Fee\n2026-08-01 12:00:00,BTCEUR,BUY,60000,0.01 BTC,600 EUR,1 EUR\n""")
        self.assert_single(result, "Binance Trade", "purchase", "0.01", "EUR", "60000")

    def test_binance_transaction_statement(self):
        result = self.parse("binance-transaction-history.csv", """User_ID,UTC_Time,Account,Operation,Coin,Change,Remark\n1,2026-08-01 12:00:00,Spot,Transaction Buy,BTC,0.01,order-1\n1,2026-08-01 12:00:00,Spot,Transaction Buy,EUR,-600,order-1\n""")
        self.assert_single(result, "Binance Statement", "purchase", "0.01", "EUR", "60000")

    def test_cointracking_universal_csv(self):
        result = self.parse("cointracking.csv", """Type,Buy,Cur.,Sell,Cur.,Fee,Cur.,Exchange,Trade-Group,Comment,Date,Tx-ID\nTrade,0.01,BTC,600,EUR,1.5,EUR,Kraken,,Test,01.08.2026 12:00:00,abc\n""")
        self.assert_single(result, "CoinTracking", "purchase", "0.01", "EUR", "60000")
        self.assertEqual(result["rows"][0]["fee"], "1.5")

    def test_cointracking_non_fiat_fee_requires_review(self):
        result = self.parse("cointracking.csv", """Type,Buy,Cur.,Sell,Cur.,Fee,Cur.,Exchange,Comment,Date,Tx-ID\nTrade,0.01,BTC,600,EUR,0.00001,BTC,Kraken,Test,01.08.2026 12:00:00,abc\n""")
        row = result["rows"][0]
        self.assertFalse(row["valid"])
        self.assertEqual(row["fee"], "0")
        self.assertTrue(any("Gebühr in BTC" in warning for warning in row["warnings"]))

    def test_named_broker_generic_formats(self):
        csv_text = """Type;Date;BTC Amount;Fiat Amount;Fiat Currency;Fee;Transaction ID\nBuy;01.08.2026 12:00;0,01;600;EUR;2;id-1\n"""
        cases = {
            "coinfinity-export.csv": "Coinfinity",
            "relai-orders.csv": "Relai",
            "pocket-export.csv": "Pocket Bitcoin",
            "getbittr-transactions.csv": "Bittr",
            "wavespace-orders.csv": "Wavespace",
        }
        for name, source in cases.items():
            with self.subTest(name=name):
                result = self.parse(name, csv_text)
                self.assert_single(result, source, "purchase", "0.01", "EUR", "60000")


    def test_pocket_current_trade_schema_skips_deposit_and_withdrawal(self):
        result = self.parse("download.csv", """Type,Buy Amount,Buy Cur.,Sell Amount,Sell Cur.,Fee Amount (optional),Fee Cur. (optional),Exchange (optional),Trade Group (optional),Comment (optional),Date
Deposit,600,EUR,,,,,Pocket,,,2026-08-01 11:59:00
Trade,0.01,BTC,600,EUR,1.5,EUR,Pocket,group-1,Savings plan,2026-08-01 12:00:00
Withdrawal,,,0.00999,BTC,0.00001,BTC,Pocket,group-1,Wallet transfer,2026-08-01 12:01:00
""")
        self.assert_single(result, "Pocket Bitcoin", "purchase", "0.00998", "EUR", "59850")
        self.assertEqual(result["skipped"], 2)
        row = result["rows"][0]
        self.assertEqual(row["fee"], "2.6970")
        total_cost = Decimal(row["amount_btc"]) * Decimal(row["price"]) + Decimal(row["fee"])
        self.assertEqual(total_cost, Decimal("600.00000"))
        self.assertEqual(row["note"], "Onchain Pocket Bitcoin CSV-Import.")
        self.assertEqual(row["optional_note_fields"]["memo"], "Savings plan")
        self.assertEqual(row["optional_note_fields"]["exchange"], "Pocket")
        self.assertEqual(row["optional_note_fields"]["trade_group"], "group-1")

    def test_pocket_cointracking_fiat_fee_is_included_in_sell_amount(self):
        result = self.parse("Pocket CoinTracking - 2025.csv", """Type,Buy Amount,Buy Cur.,Sell Amount,Sell Cur.,Fee Amount (optional),Fee Cur. (optional),Exchange (optional),Trade Group (optional),Comment (optional),Date
Trade,0.001,BTC,100,EUR,1.5,EUR,Pocket,,Pocket buy,2025-01-15 12:00:00
""")
        self.assert_single(result, "Pocket Bitcoin", "purchase", "0.001", "EUR", "98500")
        row = result["rows"][0]
        self.assertEqual(row["fee"], "1.5")
        total_cost = Decimal(row["amount_btc"]) * Decimal(row["price"]) + Decimal(row["fee"])
        self.assertEqual(total_cost, Decimal("100.0"))


    def test_pocket_cointracking_withdrawal_sell_amount_minus_fee_is_wallet_amount(self):
        result = self.parse("Pocket CoinTracking - 2025.csv", """Type,Buy Amount,Buy Cur.,Sell Amount,Sell Cur.,Fee Amount (optional),Fee Cur. (optional),Exchange (optional),Trade Group (optional),Comment (optional),Date
Trade,0.001,BTC,100,EUR,1.5,EUR,Pocket,group-42,Pocket buy,2025-01-15 12:00:00
Withdrawal,,,0.001,BTC,0.000001,BTC,Pocket,group-42,Wallet transfer,2025-01-15 12:01:00
""")
        self.assert_single(result, "Pocket Bitcoin", "purchase", "0.000999", "EUR", "98500")
        row = result["rows"][0]
        self.assertEqual(row["fee"], "1.5985")
        total_cost = Decimal(row["amount_btc"]) * Decimal(row["price"]) + Decimal(row["fee"])
        self.assertEqual(total_cost, Decimal("100.000000"))

    def test_pocket_cointracking_batches_all_trades_since_previous_withdrawal_across_midnight(self):
        # CoinTracking can be newest-first. Pocket batches the two purchases from
        # the evening into one withdrawal after midnight. A later purchase on the
        # new day must start a fresh batch and remain untouched until its own payout.
        result = self.parse("Pocket CoinTracking - 2025.csv", """Type,Buy Amount,Buy Cur.,Sell Amount,Sell Cur.,Fee Amount (optional),Fee Cur. (optional),Exchange (optional),Trade Group (optional),Comment (optional),Date
Trade,0.004,BTC,400,EUR,6,EUR,Pocket,,next-day buy,2025-01-16 10:00:00
Withdrawal,,,0.003,BTC,0.000003,BTC,Pocket,,batched wallet transfer,2025-01-16 02:24:31
Trade,0.002,BTC,200,EUR,3,EUR,Pocket,,evening buy 2,2025-01-15 23:30:00
Trade,0.001,BTC,100,EUR,1.5,EUR,Pocket,,evening buy 1,2025-01-15 20:00:00
""")
        self.assertEqual(len(result["rows"]), 3)
        by_memo = {row["optional_note_fields"]["memo"]: row for row in result["rows"]}

        first = by_memo["evening buy 1"]
        second = by_memo["evening buy 2"]
        later = by_memo["next-day buy"]

        self.assertEqual(first["amount_btc"], "0.000999")
        self.assertEqual(second["amount_btc"], "0.001998")
        self.assertEqual(later["amount_btc"], "0.004")
        self.assertEqual(first["fee"], "1.5985")
        self.assertEqual(second["fee"], "3.1970")
        self.assertEqual(later["fee"], "6")

        total_wallet_btc = Decimal(first["amount_btc"]) + Decimal(second["amount_btc"])
        self.assertEqual(total_wallet_btc, Decimal("0.002997"))
        total_cost = sum(
            Decimal(row["amount_btc"]) * Decimal(row["price"]) + Decimal(row["fee"])
            for row in result["rows"]
        )
        self.assertEqual(total_cost, Decimal("700.000000"))

    def test_pocket_cointracking_batch_withdrawal_at_0155_closes_only_prior_trades(self):
        result = self.parse("Pocket CoinTracking.csv", """Type,Buy Amount,Buy Cur.,Sell Amount,Sell Cur.,Fee Amount (optional),Fee Cur. (optional),Exchange (optional),Trade Group (optional),Comment (optional),Date
Trade,0.001,BTC,100,EUR,1,EUR,Pocket,,before midnight,2025-02-01 23:50:00
Trade,0.002,BTC,200,EUR,2,EUR,Pocket,,after midnight before payout,2025-02-02 01:15:00
Withdrawal,,,0.003,BTC,0.000003,BTC,Pocket,,wallet payout,2025-02-02 01:55:07
Trade,0.004,BTC,400,EUR,4,EUR,Pocket,,after payout,2025-02-02 03:00:00
""")
        by_memo = {row["optional_note_fields"]["memo"]: row for row in result["rows"]}
        self.assertEqual(by_memo["before midnight"]["amount_btc"], "0.000999")
        self.assertEqual(by_memo["after midnight before payout"]["amount_btc"], "0.001998")
        self.assertEqual(by_memo["after payout"]["amount_btc"], "0.004")

    def test_pocket_cointracking_unmatched_lightning_withdrawal_does_not_reset_onchain_batch(self):
        # CoinTracking does not reliably label Lightning vs. on-chain either.
        # An unrelated Lightning Withdrawal must not clear purchases that are
        # waiting for a later batched on-chain payout.
        result = self.parse("Pocket CoinTracking.csv", """Type,Buy Amount,Buy Cur.,Sell Amount,Sell Cur.,Fee Amount (optional),Fee Cur. (optional),Exchange (optional),Trade Group (optional),Comment (optional),Date
Trade,0.001,BTC,100,EUR,1.5,EUR,Pocket,,older pending buy,2025-02-01 20:00:00
Withdrawal,,,0.0004,BTC,0,BTC,Pocket,,unrelated payout,2025-02-01 21:00:00
Trade,0.002,BTC,200,EUR,3,EUR,Pocket,,later pending buy,2025-02-01 23:30:00
Withdrawal,,,0.003,BTC,0.000003,BTC,Pocket,,batched payout,2025-02-02 02:24:31
""")
        self.assertEqual(len(result["rows"]), 2)
        by_memo = {row["optional_note_fields"]["memo"]: row for row in result["rows"]}
        self.assertEqual(by_memo["older pending buy"]["amount_btc"], "0.000999")
        self.assertEqual(by_memo["later pending buy"]["amount_btc"], "0.001998")
        self.assertTrue(by_memo["older pending buy"]["valid"], by_memo["older pending buy"]["warnings"])
        self.assertTrue(by_memo["later pending buy"]["valid"], by_memo["later pending buy"]["warnings"])
        self.assertFalse(any("Sammelauszahlung" in warning for row in result["rows"] for warning in row["warnings"]))

    def test_pocket_cointracking_lightning_can_match_newer_trade_without_consuming_older_pending_trade(self):
        # A newer purchase can be paid immediately through Lightning while an
        # older purchase remains pending for a later on-chain batch.
        result = self.parse("Pocket CoinTracking.csv", """Type,Buy Amount,Buy Cur.,Sell Amount,Sell Cur.,Fee Amount (optional),Fee Cur. (optional),Exchange (optional),Trade Group (optional),Comment (optional),Date
Trade,0.001,BTC,100,EUR,1.5,EUR,Pocket,,older onchain buy,2025-02-01 20:00:00
Trade,0.0005,BTC,50,EUR,0.75,EUR,Pocket,,lightning buy,2025-02-01 21:00:00
Withdrawal,,,0.0005,BTC,0,BTC,Pocket,,lightning payout,2025-02-01 21:05:00
Trade,0.002,BTC,200,EUR,3,EUR,Pocket,,later onchain buy,2025-02-01 23:30:00
Withdrawal,,,0.003,BTC,0.000003,BTC,Pocket,,onchain batch,2025-02-02 01:55:07
""")
        self.assertEqual(len(result["rows"]), 3)
        by_memo = {row["optional_note_fields"]["memo"]: row for row in result["rows"]}
        self.assertEqual(by_memo["older onchain buy"]["amount_btc"], "0.000999")
        self.assertEqual(by_memo["lightning buy"]["amount_btc"], "0.0005")
        self.assertEqual(by_memo["later onchain buy"]["amount_btc"], "0.001998")
        self.assertEqual(by_memo["older onchain buy"]["note"], "Onchain Pocket Bitcoin CSV-Import.")
        self.assertEqual(by_memo["lightning buy"]["note"], "Lightning Pocket Bitcoin CSV-Import.")
        self.assertEqual(by_memo["later onchain buy"]["note"], "Onchain Pocket Bitcoin CSV-Import.")
        self.assertTrue(all(row["valid"] for row in result["rows"]))

    def test_pocket_current_trade_schema_supports_sale_and_btc_fee(self):
        result = self.parse("pocket-export.csv", """Type,Buy Amount,Buy Cur.,Sell Amount,Sell Cur.,Fee Amount (optional),Fee Cur. (optional),Exchange (optional),Trade Group (optional),Comment (optional),Date
Trade,620,EUR,0.01,XBT,0.00001,BTC,Pocket,,Sale,2026-08-02T10:00:00Z
""")
        self.assert_single(result, "Pocket Bitcoin", "sale", "0.01", "EUR", "62000")
        self.assertEqual(result["rows"][0]["fee"], "0.620")

    def test_pocket_native_dashboard_export_purchase(self):
        result = self.parse("renamed.csv", """type,date,reference,price.currency,price.amount,cost.currency,cost.amount,fee.currency,fee.amount,value.currency,value.amount
purchase,09/22/2021 04:07:37 AM,RF69 SATS 21,CHF,39135.44,CHF,-9.85,CHF,-0.15,BTC,0.00025169
withdrawal,09/22/2021 07:45:01 PM,,, ,,,BTC,-0.00000038,BTC,0.00025131
deposit,09/22/2021 04:07:16 AM,,,,,CHF,-0.00,CHF,10.00
""")
        self.assert_single(result, "Pocket Bitcoin", "purchase", "0.00025131", "CHF", "39135.44")
        self.assertEqual(result["skipped"], 2)
        row = result["rows"][0]
        self.assertEqual(row["fee"], "0.1648714672")
        self.assertEqual(row["note"], "Onchain Pocket Bitcoin CSV-Import.")
        self.assertEqual(row["optional_note_fields"]["memo"], "RF69 SATS 21")

    def test_pocket_native_batches_all_purchases_since_previous_withdrawal_across_midnight(self):
        # Native Pocket exports may be newest-first. Two purchases are paid out
        # together after midnight; a later purchase on the same calendar day must
        # start the next batch and must not be consumed by the earlier Withdrawal.
        result = self.parse("Pocket - 2025.csv", """type,date,reference,price.currency,price.amount,cost.currency,cost.amount,fee.currency,fee.amount,value.currency,value.amount
purchase,01/16/2025 10:00:00 AM,next-day buy,EUR,98500,EUR,-394,EUR,-6,BTC,0.004
withdrawal,01/16/2025 02:24:31 AM,,,,,,BTC,-0.000003,BTC,0.002997
purchase,01/15/2025 11:30:00 PM,evening buy 2,EUR,98500,EUR,-197,EUR,-3,BTC,0.002
purchase,01/15/2025 08:00:00 PM,evening buy 1,EUR,98500,EUR,-98.5,EUR,-1.5,BTC,0.001
""")
        self.assertEqual(len(result["rows"]), 3)
        by_memo = {row["optional_note_fields"]["memo"]: row for row in result["rows"]}

        first = by_memo["evening buy 1"]
        second = by_memo["evening buy 2"]
        later = by_memo["next-day buy"]

        self.assertEqual(first["amount_btc"], "0.000999")
        self.assertEqual(second["amount_btc"], "0.001998")
        self.assertEqual(later["amount_btc"], "0.004")
        self.assertEqual(first["fee"], "1.598500")
        self.assertEqual(second["fee"], "3.197000")
        self.assertEqual(later["fee"], "6")

        total_wallet_btc = Decimal(first["amount_btc"]) + Decimal(second["amount_btc"])
        self.assertEqual(total_wallet_btc, Decimal("0.002997"))
        total_cost = sum(
            Decimal(row["amount_btc"]) * Decimal(row["price"]) + Decimal(row["fee"])
            for row in result["rows"]
        )
        self.assertEqual(total_cost, Decimal("700.000000"))

    def test_pocket_native_withdrawal_at_0155_closes_only_prior_purchases(self):
        result = self.parse("Pocket.csv", """type,date,reference,price.currency,price.amount,cost.currency,cost.amount,fee.currency,fee.amount,value.currency,value.amount
purchase,02/01/2025 11:50:00 PM,before midnight,EUR,99000,EUR,-99,EUR,-1,BTC,0.001
purchase,02/02/2025 01:15:00 AM,after midnight before payout,EUR,99000,EUR,-198,EUR,-2,BTC,0.002
withdrawal,02/02/2025 01:55:07 AM,,,,,,BTC,-0.000003,BTC,0.002997
purchase,02/02/2025 03:00:00 AM,after payout,EUR,99000,EUR,-396,EUR,-4,BTC,0.004
""")
        by_memo = {row["optional_note_fields"]["memo"]: row for row in result["rows"]}
        self.assertEqual(by_memo["before midnight"]["amount_btc"], "0.000999")
        self.assertEqual(by_memo["after midnight before payout"]["amount_btc"], "0.001998")
        self.assertEqual(by_memo["after payout"]["amount_btc"], "0.004")

    def test_pocket_native_unmatched_lightning_withdrawal_does_not_reset_onchain_batch(self):
        # Pocket's native CSV does not identify Lightning vs. on-chain. An
        # unrelated Lightning Withdrawal with another numeric reference must not
        # clear the purchases waiting for a later batched on-chain payout.
        result = self.parse("Pocket.csv", """type,date,reference,price.currency,price.amount,cost.currency,cost.amount,fee.currency,fee.amount,value.currency,value.amount
purchase,02/01/2025 08:00:00 PM,100001,EUR,98500,EUR,-98.5,EUR,-1.5,BTC,0.001
withdrawal,02/01/2025 09:00:00 PM,900001,,,,,BTC,0,BTC,0.0004
purchase,02/01/2025 11:30:00 PM,100002,EUR,98500,EUR,-197,EUR,-3,BTC,0.002
withdrawal,02/02/2025 02:24:31 AM,700001,,,,,BTC,-0.000003,BTC,0.002997
""")
        self.assertEqual(len(result["rows"]), 2)
        by_ref = {row["optional_note_fields"]["memo"]: row for row in result["rows"]}
        self.assertEqual(by_ref["100001"]["amount_btc"], "0.000999")
        self.assertEqual(by_ref["100002"]["amount_btc"], "0.001998")
        self.assertTrue(by_ref["100001"]["valid"], by_ref["100001"]["warnings"])
        self.assertTrue(by_ref["100002"]["valid"], by_ref["100002"]["warnings"])

    def test_pocket_native_lightning_can_match_newer_trade_without_consuming_older_pending_trade(self):
        # An immediate Lightning payout may belong to a newer trade while an older
        # purchase is still waiting for a later on-chain batch. Match the unique
        # BTC amount window and remove only that purchase from the pending set.
        result = self.parse("Pocket.csv", """type,date,reference,price.currency,price.amount,cost.currency,cost.amount,fee.currency,fee.amount,value.currency,value.amount
purchase,02/01/2025 08:00:00 PM,200001,EUR,100000,EUR,-99,EUR,-1,BTC,0.001
purchase,02/01/2025 09:00:00 PM,200002,EUR,100000,EUR,-49.5,EUR,-0.5,BTC,0.0005
withdrawal,02/01/2025 09:05:00 PM,900002,,,,,BTC,0,BTC,0.0005
purchase,02/01/2025 11:30:00 PM,200003,EUR,100000,EUR,-198,EUR,-2,BTC,0.002
withdrawal,02/02/2025 01:55:07 AM,700002,,,,,BTC,-0.000003,BTC,0.002997
""")
        self.assertEqual(len(result["rows"]), 3)
        by_ref = {row["optional_note_fields"]["memo"]: row for row in result["rows"]}
        self.assertEqual(by_ref["200001"]["amount_btc"], "0.000999")
        self.assertEqual(by_ref["200002"]["amount_btc"], "0.0005")
        self.assertEqual(by_ref["200003"]["amount_btc"], "0.001998")
        self.assertEqual(by_ref["200001"]["note"], "Onchain Pocket Bitcoin CSV-Import.")
        self.assertEqual(by_ref["200002"]["note"], "Lightning Pocket Bitcoin CSV-Import.")
        self.assertEqual(by_ref["200003"]["note"], "Onchain Pocket Bitcoin CSV-Import.")
        self.assertTrue(all(row["valid"] for row in result["rows"]))

    def test_pocket_transport_note_stays_neutral_when_no_withdrawal_can_be_classified(self):
        result = self.parse("Pocket.csv", """type,date,reference,price.currency,price.amount,cost.currency,cost.amount,fee.currency,fee.amount,value.currency,value.amount
purchase,02/01/2025 08:00:00 PM,300001,EUR,100000,EUR,-99,EUR,-1,BTC,0.001
withdrawal,02/01/2025 08:05:00 PM,900003,,,,,BTC,0,BTC,0.0004
""")
        self.assertEqual(result["rows"][0]["note"], "Pocket Bitcoin CSV-Import")

    def test_pocket_native_header_is_detected_without_filename(self):
        headers = [
            "type", "date", "reference", "price.currency", "price.amount",
            "cost.currency", "cost.amount", "fee.currency", "fee.amount",
            "value.currency", "value.amount",
        ]
        self.assertEqual(_detect_source("download.csv", headers, []), "pocket")

    def test_pocket_native_future_sale_shape(self):
        result = self.parse("Pocket.csv", """type,date,reference,price.currency,price.amount,cost.currency,cost.amount,fee.currency,fee.amount,value.currency,value.amount
sale,2026-08-02T10:00:00Z,,EUR,62000,BTC,-0.01,EUR,-1.25,EUR,620
""")
        self.assert_single(result, "Pocket Bitcoin", "sale", "0.01", "EUR", "62000")
        self.assertEqual(result["rows"][0]["fee"], "1.25")

    def test_unknown_common_format_is_editable_preview(self):
        result = self.parse("other-broker.csv", """Action,Created At,Bitcoin Amount,Local Currency,Total,Commission,Reference\nPurchase,2026-08-01T12:00:00Z,0.01,CHF,550,2.5,x1\n""")
        self.assert_single(result, "Generischer CSV-Import", "purchase", "0.01", "CHF", "55000")

    def test_coinfinity_literal_btc_column_and_german_headers(self):
        result = self.parse("coinfinity-activities.csv", """Datum;Aktivität;BTC;EUR;BTC Kurs;Gebühr;Referenz
01.08.2026 12:00;Bitcoin-Kauf;0,01;600;60000;2;cf-1
""")
        self.assert_single(result, "Coinfinity", "purchase", "0.01", "EUR", "60000")
        self.assertEqual(result["rows"][0]["fee"], "2")

    def test_coinfinity_literal_xbt_column(self):
        result = self.parse("coinfinity-export.csv", """Date,Activity,XBT,EUR,Exchange Rate,Fee
2026-08-01 12:00:00,Purchase,0.01,600,60000,2
""")
        self.assert_single(result, "Coinfinity", "purchase", "0.01", "EUR", "60000")

    def test_coinfinity_current_onchain_schema_uses_satoshis_and_total_fee(self):
        result = self.parse("activities.csv", """Order ID;Type;Date;Amount EUR;Amount Crypto;Crypto;Rate EUR;Mining Fee Crypto;Mining Fee EUR;Service Fee EUR;Total Fee EUR;Address;Transaction;LN Invoice;Transaction type
cf-1;Buy;2026-08-01 12:00:00;600;1000000;BTC;60000;500;0,30;2,00;2,30;bc1qexample;abcdef0123456789abcdef0123456789;;On-Chain
""")
        self.assert_single(result, "Coinfinity", "purchase", "0.01", "EUR", "60000")
        row = result["rows"][0]
        self.assertEqual(row["fee"], "2.30")
        self.assertIn("On-Chain", row["note"])
        self.assertIn("Mining Fee: 500 sats", row["note"])
        self.assertIn("Service Fee: 2 EUR", row["note"])
        self.assertNotIn("bc1qexample", row["note"])
        self.assertNotIn("abcdef0123456789", row["note"])
        self.assertEqual(row["optional_note_fields"]["order_id"], "cf-1")
        self.assertEqual(row["optional_note_fields"]["address"], "bc1qexample")
        self.assertEqual(row["optional_note_fields"]["transaction_id"], "abcdef0123456789abcdef0123456789")

    def test_coinfinity_current_lightning_schema(self):
        result = self.parse("download.csv", """Order ID,Type,Date,Amount EUR,Amount Crypto,Crypto,Rate EUR,Mining Fee Crypto,Mining Fee EUR,Service Fee EUR,Total Fee EUR,Address,Transaction,LN Invoice,Transaction type
cf-ln-1,Purchase,2026-08-02T08:30:00Z,60,100000,XBT,60000,0,0,0.75,0.75,,,lnbc1exampleinvoice,Lightning
""")
        self.assert_single(result, "Coinfinity", "purchase", "0.001", "EUR", "60000")
        row = result["rows"][0]
        self.assertEqual(row["fee"], "0.75")
        self.assertIn("Lightning", row["note"])
        self.assertNotIn("lnbc1exampleinvoice", row["note"])
        self.assertNotIn("LN-Invoice", row["note"])
        self.assertEqual(row["optional_note_fields"]["ln_invoice"], "lnbc1exampleinvoice")
        self.assertEqual(row["optional_note_fields"]["order_id"], "cf-ln-1")

    def test_coinfinity_sensitive_identifiers_are_optional_not_default_note(self):
        result = self.parse("activities.csv", """Order ID;Type;Date;Amount EUR;Amount Crypto;Crypto;Rate EUR;Mining Fee Crypto;Mining Fee EUR;Service Fee EUR;Total Fee EUR;Address;Transaction;LN Invoice;Transaction type
cf-private;Buy;2026-08-01 12:00:00;600;1000000;BTC;60000;500;0,30;2,00;2,30;bc1q-private-address;private-txid;lnbc-private-invoice;Lightning
""")
        row = result["rows"][0]
        for secret in ("bc1q-private-address", "private-txid", "lnbc-private-invoice", "cf-private"):
            self.assertNotIn(secret, row["note"])
        self.assertEqual(row["optional_note_fields"], {
            "order_id": "cf-private",
            "address": "bc1q-private-address",
            "transaction_id": "private-txid",
            "ln_invoice": "lnbc-private-invoice",
        })
        self.assertIn("Lightning", row["note"])

    def test_coinfinity_current_sale_schema(self):
        result = self.parse("activities.csv", """Order ID,Type,Date,Amount EUR,Amount Crypto,Crypto,Rate EUR,Mining Fee Crypto,Mining Fee EUR,Service Fee EUR,Total Fee EUR,Address,Transaction,LN Invoice,Transaction type
cf-sell-1,Sell,2026-08-03 09:00:00,620,1000000,BTC,62000,0,0,1.50,1.50,,,tx-sale,,Onchain
""")
        self.assert_single(result, "Coinfinity", "sale", "0.01", "EUR", "62000")

    def test_wavespace_purchase_schema_exposes_private_fields_only_as_optional(self):
        result = self.parse("export.csv", """Type Category,Executes At,Transaction ID,Transaction Type,From Currency,From Amount,To Currency,To Amount,Memo
Trade,2026-08-04T10:15:00Z,private-wave-id,Buy,EUR,600,BTC,0.01,bc1q-private-address
""")
        self.assert_single(result, "Wavespace", "purchase", "0.01", "EUR", "60000")
        row = result["rows"][0]
        self.assertNotIn("private-wave-id", row["note"])
        self.assertNotIn("bc1q-private-address", row["note"])
        self.assertEqual(row["optional_note_fields"]["transaction_id"], "TRADE: private-wave-id")
        self.assertEqual(row["optional_note_fields"]["memo"], "TRADE: bc1q-private-address")
        self.assertEqual(row["optional_note_fields"]["transaction_type"], "Buy")
        self.assertEqual(row["note"], "Wavespace CSV-Import")

    def test_wavespace_sale_accepts_xbt(self):
        result = self.parse("wavespace.csv", """Type Category,Executes At,Transaction ID,Transaction Type,From Currency,From Amount,To Currency,To Amount,Memo
Trade,2026-08-04 11:00:00,secret-id,Sell,XBT,0.01,EUR,620,private memo
""")
        self.assert_single(result, "Wavespace", "sale", "0.01", "EUR", "62000")
        row = result["rows"][0]
        self.assertNotIn("secret-id", row["note"])
        self.assertNotIn("private memo", row["note"])
        self.assertEqual(row["optional_note_fields"]["transaction_id"], "TRADE: secret-id")
        self.assertEqual(row["optional_note_fields"]["memo"], "TRADE: private memo")

    def test_wavespace_satoshi_unit_and_transfer_filter(self):
        result = self.parse("wavespace.csv", """Type Category,Executes At,Transaction ID,Transaction Type,From Currency,From Amount,To Currency,To Amount,Memo
Trade,2026-08-04 12:00:00,id-buy,Buy,EUR,600,SATS,1000000,hidden
Transfer,2026-08-04 12:05:00,id-transfer,Send,BTC,0.01,BTC,0.01,bc1q-hidden
""")
        self.assert_single(result, "Wavespace", "purchase", "0.01", "EUR", "60000")
        self.assertEqual(result["skipped"], 1)
        row = result["rows"][0]
        self.assertNotIn("id-transfer", repr(row["optional_note_fields"]))
        self.assertNotIn("bc1q-hidden", repr(row["optional_note_fields"]))

    def test_wavespace_multirow_purchase_uses_withdrawal_wallet_amount(self):
        result = self.parse("wavespace.csv", """Type Category,Executes At,Transaction ID,Transaction Type,From Currency,From Amount,To Currency,To Amount,Memo
DEPOSIT,2026-08-04 12:00:00,private-deposit,Deposit,EUR,602,,,bank reference
FEE,2026-08-04 12:00:01,private-fee-1,Exchange fee,EUR,2,,,private fee memo
BUY,2026-08-04 12:00:02,private-buy,Buy,EUR,600,BTC,0.01,private order
FEE,2026-08-04 12:00:03,private-fee-2,Network fee,BTC,0.00001,,,private network memo
WITHDRAWAL,2026-08-04 12:00:04,private-withdrawal,Withdrawal,BTC,0.00999,,,bc1q-private-wallet
TRANSACTION,2026-08-04 12:00:05,private-chain,Transaction,BTC,0.00999,,,private txid
""")
        self.assert_single(result, "Wavespace", "purchase", "0.00999", "EUR", "60000")
        row = result["rows"][0]
        self.assertEqual(row["fee"], "2.600")
        self.assertIn("Wechselgebühr: 2 EUR", row["note"])
        self.assertIn("Netzwerkgebühr: 0.00001 BTC", row["note"])
        self.assertIn("Wallet-Eingang: 0.00999 BTC", row["note"])
        self.assertIn("Bruttokauf: 0.01 BTC", row["note"])
        self.assertEqual(result["skipped"], 0)
        optional = row["optional_note_fields"]
        self.assertIn("DEPOSIT: private-deposit", optional["transaction_id"])
        self.assertIn("TRANSACTION: private-chain", optional["transaction_id"])
        self.assertIn("DEPOSIT: bank reference", optional["memo"])
        self.assertIn("WITHDRAWAL: bc1q-private-wallet", optional["memo"])
        self.assertIn("TRANSACTION: private txid", optional["memo"])
        for secret in ("private-deposit", "private-chain", "bc1q-private-wallet", "private txid"):
            self.assertNotIn(secret, row["note"])

    def test_wavespace_fee_memo_overrides_misleading_amount_columns(self):
        result = self.parse("wavespace.csv", """Type Category,Executes At,Transaction ID,Transaction Type,From Currency,From Amount,To Currency,To Amount,Memo
DEPOSIT,2026-08-04 12:00:00,id-d,Deposit,EUR,600.1,,,bank reference
FEE,2026-08-04 12:00:01,id-f1,Trading Fee,EUR,1,,,Trading Fee for 1 EUR to BTC 0.1 EUR
BUY,2026-08-04 12:00:02,id-b,Buy,EUR,600,BTC,0.01,order
FEE,2026-08-04 12:00:03,id-f2,Network Fee,BTC,0.00002,,,Bitcoin Network Fee 1000 SATS
WITHDRAWAL,2026-08-04 12:00:04,id-w,Withdrawal,BTC,0.00999,,,wallet
""")
        self.assert_single(result, "Wavespace", "purchase", "0.00999", "EUR", "60000")
        row = result["rows"][0]
        self.assertEqual(row["fee"], "0.700")
        self.assertIn("Wechselgebühr aus Memo: 0.1 EUR", row["note"])
        self.assertIn("Netzwerkgebühr aus Memo: 0.00001 BTC", row["note"])
        self.assertNotIn("Wechselgebühr aus Memo: 1 EUR", row["note"])
        self.assertIn("Wallet-Eingang: 0.00999 BTC", row["note"])

    def test_wavespace_multirow_purchase_supports_newest_first_order(self):
        result = self.parse("wavespace.csv", """Type Category,Executes At,Transaction ID,Transaction Type,From Currency,From Amount,To Currency,To Amount,Memo
WITHDRAWAL,2026-08-04 12:00:04,id-w,Withdrawal,BTC,0.00999,,,hidden
FEE,2026-08-04 12:00:03,id-f2,Network fee,BTC,0.00001,,,hidden
BUY,2026-08-04 12:00:02,id-b,Buy,EUR,600,XBT,0.01,hidden
FEE,2026-08-04 12:00:01,id-f1,Exchange fee,EUR,2,,,hidden
DEPOSIT,2026-08-04 12:00:00,id-d,Deposit,EUR,602,,,hidden
""")
        self.assert_single(result, "Wavespace", "purchase", "0.00999", "EUR", "60000")
        self.assertEqual(result["rows"][0]["fee"], "2.600")

    def test_wavespace_semantic_grouping_handles_variable_rows_and_card_sales(self):
        result = self.parse("wavespace.csv", """Type Category,Executes At,Transaction ID,Transaction Type,From Currency,From Amount,To Currency,To Amount,Memo
FEE,2026-08-04 09:00:00,unrelated-fee,APPLICATION_FEE,BTC,0.000001,BTC,0.000001,Lightning deposit fee 0.000001 BTC
DEPOSIT,2026-08-04 09:00:01,unrelated-deposit,LIGHTNING_DEPOSIT,BTC,0.01,BTC,0.01,unrelated
DEPOSIT,2026-08-04 10:00:00,sepa-a,SEPA_PAYIN_DEPOSIT,EUR,600.1,EUR,600.1,bank
FEE,2026-08-04 10:00:02,fee-a,APPLICATION_FEE,EUR,1,EUR,1,Trading Fee for 1 EUR to BTC 0.1 EUR
BUY,2026-08-04 10:00:03,buy-a,CURRENCY_SWAP,EUR,600,BTC,0.01,swap
WITHDRAWAL,2026-08-04 10:00:04,withdraw-a,LIGHTNING_WITHDRAW,BTC,0.01,BTC,0.01,lightning
FEE,2026-08-04 11:00:01,card-fee,APPLICATION_FEE,BTC,0.000001,BTC,0.000001,Card fee 0.000001 BTC
TRANSACTION,2026-08-04 11:00:02,card-a,CARD_AUTHORIZATION,BTC,0.001,EUR,60,card purchase
FEE,2026-08-04 11:59:59,fee-b,APPLICATION_FEE,EUR,0.05,EUR,0.05,Trading Fee 0.05 EUR
BUY,2026-08-04 12:00:00,buy-b,CURRENCY_SWAP,EUR,300,BTC,0.005,swap without payout
""")
        self.assertEqual(result["recognized"], 3)
        purchases = [row for row in result["rows"] if row["type"] == "purchase"]
        sales = [row for row in result["rows"] if row["type"] == "sale"]
        self.assertEqual(len(purchases), 2)
        self.assertEqual(len(sales), 1)
        self.assertEqual(purchases[0]["amount_btc"], "0.01")
        self.assertEqual(purchases[0]["fee"], "0.1")
        self.assertIn("Wallet-Menge aus Withdrawal", purchases[0]["note"])
        self.assertEqual(purchases[1]["amount_btc"], "0.005")
        self.assertEqual(purchases[1]["fee"], "0.05")
        self.assertIn("BTC-Menge aus Currency Swap", purchases[1]["note"])
        self.assertEqual(sales[0]["amount_btc"], "0.001")
        self.assertEqual(sales[0]["price"], "60000")
        self.assertEqual(sales[0]["fee"], "0.060")
        self.assertIn("Kartentransaktion", sales[0]["note"])
        self.assertNotIn("unrelated-fee", repr(result["rows"]))

    def test_wavespace_standalone_withdrawal_does_not_replace_purchase_amount(self):
        result = self.parse("wavespace.csv", """Type Category,Executes At,Transaction ID,Transaction Type,From Currency,From Amount,To Currency,To Amount,Memo
FEE,2026-08-04 10:00:00,app-a,APPLICATION_FEE,EUR,1,EUR,1,Trading Fee 0.1 EUR
BUY,2026-08-04 10:00:01,buy-a,CURRENCY_SWAP,EUR,600,BTC,0.01,buy
FEE,2026-08-04 10:00:02,net-a,NETWORK_FEE,BTC,0.00001,BTC,0.00001,Bitcoin Network Fee 1000 SATS
WITHDRAWAL,2026-08-04 10:00:03,withdraw-a,ON_CHAIN_WITHDRAW,BTC,0.00999,BTC,0.00999,wallet
FEE,2026-08-04 10:00:04,net-standalone,NETWORK_FEE,BTC,0.0001,BTC,0.0001,Bitcoin Network Fee 10000 SATS
WITHDRAWAL,2026-08-04 10:00:05,withdraw-standalone,ON_CHAIN_WITHDRAW,BTC,0.1,BTC,0.1,other wallet
BUY,2026-08-04 11:00:00,buy-b,CURRENCY_SWAP,EUR,1200,BTC,0.02,buy without withdrawal
""")
        self.assertEqual(result["recognized"], 2)
        first, second = result["rows"]
        self.assertEqual(first["amount_btc"], "0.00999")
        self.assertEqual(first["fee"], "0.700")
        self.assertNotIn("0.0001 BTC", first["note"])
        self.assertEqual(second["amount_btc"], "0.02")
        self.assertEqual(second["fee"], "0")

    def test_wavespace_currency_swap_sale_is_not_confused_with_payout(self):
        result = self.parse("wavespace.csv", """Type Category,Executes At,Transaction ID,Transaction Type,From Currency,From Amount,To Currency,To Amount,Memo
FEE,2026-08-04 12:00:00,sale-fee,APPLICATION_FEE,BTC,0.00001,BTC,0.00001,Trading Fee 0.00001 BTC
SELL,2026-08-04 12:00:01,sale,CURRENCY_SWAP,BTC,0.01,EUR,620,sale
WITHDRAWAL,2026-08-04 12:30:00,payout,SEPA_PAYOUT,EUR,620,EUR,620,bank payout
""")
        self.assert_single(result, "Wavespace", "sale", "0.01", "EUR", "62000")
        row = result["rows"][0]
        self.assertEqual(row["fee"], "0.620")
        self.assertIn("Bitcoin-Verkauf", row["note"])
        self.assertNotIn("payout", repr(row["optional_note_fields"]))

    def test_wavespace_card_creation_fees_are_compatible_sales(self):
        result = self.parse("wavespace.csv", """Type Category,Executes At,Transaction ID,Transaction Type,From Currency,From Amount,To Currency,To Amount,Memo
FEE,2026-08-04 08:00:00,card-create-1,APPLICATION_FEE,BTC,0.00002,BTC,0.00002,Application Fee for Card Creation
FEE,2026-08-05 08:00:00,card-create-2,APPLICATION_FEE,BTC,0.00003,BTC,0.00003,Application Fee for Card Creation
TRANSACTION,2026-08-05 09:00:00,card-pay-1,CARD_AUTHORIZATION,BTC,0.001,EUR,60,Card payment
""")
        self.assertEqual(result["recognized"], 3)
        card_fees = [row for row in result["rows"] if row.get("import_hints", {}).get("wavespace_kind") == "card_creation"]
        card_payments = [row for row in result["rows"] if row.get("import_hints", {}).get("wavespace_kind") == "card_transaction"]
        self.assertEqual(len(card_fees), 2)
        self.assertEqual(len(card_payments), 1)
        self.assertTrue(all(row["type"] == "sale" for row in card_fees))
        self.assertEqual([row["amount_btc"] for row in card_fees], ["0.00002", "0.00003"])
        self.assertEqual([row["import_hints"]["card_price_eur"] for row in card_fees], ["2.99", "29.99"])
        self.assertTrue(all(row["currency"] == "EUR" and float(row["price"]) > 0 for row in card_fees))
        self.assertEqual(card_payments[0]["amount_btc"], "0.001")

    def test_wavespace_nine_card_payments_and_two_card_creation_sales(self):
        rows = [
            "Type Category,Executes At,Transaction ID,Transaction Type,From Currency,From Amount,To Currency,To Amount,Memo",
            "FEE,2026-08-01 08:00:00,create-1,APPLICATION_FEE,BTC,0.00002,BTC,0.00002,Application Fee for Card Creation",
            "FEE,2026-08-02 08:00:00,create-2,APPLICATION_FEE,BTC,0.00003,BTC,0.00003,Application Fee for Card Creation",
        ]
        for index in range(9):
            rows.append(
                f"TRANSACTION,2026-08-{index + 3:02d} 12:00:00,card-{index},CARD_AUTHORIZATION,BTC,0.001,EUR,60,Card payment {index + 1}"
            )
        result = self.parse("wavespace.csv", "\n".join(rows) + "\n")
        self.assertEqual(result["recognized"], 11)
        self.assertEqual(sum(row["type"] == "sale" for row in result["rows"]), 11)
        self.assertEqual(sum(row.get("import_hints", {}).get("wavespace_kind") == "card_transaction" for row in result["rows"]), 9)
        self.assertEqual(sum(row.get("import_hints", {}).get("wavespace_kind") == "card_creation" for row in result["rows"]), 2)

    def test_delete_all_ui_uses_two_step_dashboard_modal_and_compat_fallback(self):
        static = APP / "static"
        script = (static / "app-v021000-197f97c6.js").read_text(encoding="utf-8")
        html = (APP / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="deleteAllEntries"', html)
        self.assertIn('id="deleteAllModal"', html)
        self.assertIn('id="deleteAllAcknowledge"', html)
        self.assertNotIn('confirm(t("deleteAllBackupConfirm"))', script)
        self.assertIn('renderDeleteAllDialog(1)', script)
        self.assertIn('renderDeleteAllDialog(2)', script)
        self.assertIn('service("delete_all_entries"', script)
        self.assertIn('service("delete_entry"', script)

    def test_wavespace_wavecard_topup_is_not_counted_as_a_sale(self):
        result = self.parse("wavespace.csv", """Type Category,Executes At,Transaction ID,Transaction Type,From Currency,From Amount,To Currency,To Amount,Memo
SELL,2026-08-04 10:00:00,topup,CURRENCY_SWAP,BTC,0.002,EUR,120,Wavecard topup
TRANSACTION,2026-08-04 11:00:00,pos,CARD_AUTHORIZATION,BTC,0.001,EUR,60,POSPurchase Card Authorization at REWE application fee of 0.00000148 BTC
""")
        self.assertEqual(result["recognized"], 1)
        row = result["rows"][0]
        self.assertEqual(row["type"], "sale")
        self.assertEqual(row["note"], "Wavespace · Kartentransaktion REWE")
        self.assertEqual(row["import_hints"]["wavespace_kind"], "card_transaction")
        self.assertEqual(row["import_hints"]["localized_note_en"], "Wavespace · Card transaction REWE")

    def test_wavespace_atm_and_pos_memos_supply_location_and_fee(self):
        result = self.parse("wavespace.csv", """Type Category,Executes At,Transaction ID,Transaction Type,From Currency,From Amount,To Currency,To Amount,Memo
TRANSACTION,2026-08-04 10:00:00,atm,CARD_AUTHORIZATION,BTC,0.001,EUR,60,ATMWithdrawal Card Authorization at SPARKASSE application fee of 0.00003943 BTC
TRANSACTION,2026-08-04 11:00:00,pos,CARD_AUTHORIZATION,BTC,0.001,EUR,60,POSPurchase Card Authorization at REWE application fee of 0.00000148 BTC
""")
        self.assertEqual(result["recognized"], 2)
        atm, pos = result["rows"]
        self.assertEqual(atm["note"], "Wavespace · Bargeldabhebung SPARKASSE")
        self.assertEqual(atm["fee"], "2.36580")
        self.assertEqual(atm["import_hints"]["wavespace_kind"], "atm_withdrawal")
        self.assertEqual(pos["note"], "Wavespace · Kartentransaktion REWE")
        self.assertEqual(pos["fee"], "0.08880")
        self.assertEqual(pos["import_hints"]["merchant"], "REWE")


    def test_wavespace_card_usage_can_come_from_application_fee_memo(self):
        result = self.parse("wavespace.csv", """Type Category,Executes At,Transaction ID,Transaction Type,From Currency,From Amount,To Currency,To Amount,Memo
FEE,2026-08-04 10:00:00,fee-pos,APPLICATION_FEE,BTC,0.00000148,BTC,0.00000148,POSPurchase Card Authorization at REWE  application fee of  0.00000148 BTC
TRANSACTION,2026-08-04 10:00:02,card-pos,CARD_AUTHORIZATION,BTC,0.001,EUR,60,Card authorization
FEE,2026-08-04 11:00:00,fee-atm,APPLICATION_FEE,BTC,0.00003943,BTC,0.00003943,ATMWithdrawal Card Authorization at SPARKASSE application fee of 0.00003943 BTC
TRANSACTION,2026-08-04 11:00:02,card-atm,CARD_AUTHORIZATION,BTC,0.002,EUR,120,Card authorization
""")
        self.assertEqual(result["recognized"], 2)
        self.assertTrue(all(row["type"] == "sale" for row in result["rows"]))
        pos = next(row for row in result["rows"] if "REWE" in row["note"])
        atm = next(row for row in result["rows"] if "SPARKASSE" in row["note"])
        self.assertEqual(pos["note"], "Wavespace · Kartentransaktion REWE")
        self.assertEqual(pos["import_hints"]["wavespace_kind"], "card_transaction")
        self.assertEqual(pos["import_hints"]["merchant"], "REWE")
        self.assertEqual(atm["note"], "Wavespace · Bargeldabhebung SPARKASSE")
        self.assertEqual(atm["import_hints"]["wavespace_kind"], "atm_withdrawal")
        self.assertEqual(atm["import_hints"]["merchant"], "SPARKASSE")

    def test_wavespace_paywave_parenthesized_merchant_is_clean_compact_note(self):
        result = self.parse("wavespace.csv", """Type Category,Executes At,Transaction ID,Transaction Type,From Currency,From Amount,To Currency,To Amount,Memo
TRANSACTION,2026-08-04 12:00:00,card-paywave,CARD_AUTHORIZATION,BTC,0.001,EUR,60,payWaveLowValuePurchase Card Authorization at (REWE ) application fee of  0.00000371 BTC
""")
        self.assert_single(result, "Wavespace", "sale", "0.001", "EUR", "60000")
        row = result["rows"][0]
        self.assertEqual(row["note"], "Wavespace · Kartentransaktion REWE")
        self.assertEqual(row["fee"], "0.22260")
        self.assertEqual(row["import_hints"]["localized_note_en"], "Wavespace · Card transaction REWE")
        self.assertEqual(row["import_hints"]["merchant"], "REWE")
        self.assertNotIn("application fee", row["note"].lower())

    def test_csv_scroller_initializes_after_modal_and_import_button_is_not_silent(self):
        static = APP / "static"
        script = (static / "app-v021000-197f97c6.js").read_text(encoding="utf-8")
        html = (APP / "index.html").read_text(encoding="utf-8")
        style = (static / "style-v021000-197f97c6.css").read_text(encoding="utf-8")
        self.assertIn("queueCsvHorizontalScrollUpdate", script)
        self.assertIn('modal.classList.remove("hidden")', script)
        self.assertIn("requestAnimationFrame(()=>requestAnimationFrame(updateCsvHorizontalScroll))", script)
        self.assertIn('id="csvScrollLeft"', html)
        self.assertIn('id="csvScrollRight"', html)
        self.assertIn('id="csvImportActionStatus"', html)
        self.assertIn("timeoutMs:120000", script)
        self.assertIn("csvImportFailed", script)
        self.assertNotIn("button.disabled = selected === 0", script)
        self.assertIn("::-webkit-slider-thumb", style)
        self.assertIn("width:42px", style)

    def test_card_creation_rows_expose_local_price_hint(self):
        result = self.parse("wavespace.csv", """Type Category,Executes At,Transaction ID,Transaction Type,From Currency,From Amount,To Currency,To Amount,Memo
FEE,2026-08-04 08:00:00,card-create-1,APPLICATION_FEE,BTC,0.00005,BTC,0.00005,Application Fee for Card Creation
FEE,2026-08-05 08:00:00,card-create-2,APPLICATION_FEE,BTC,0.0005,BTC,0.0005,Application Fee for Card Creation
""")
        self.assertEqual(result["recognized"], 2)
        self.assertTrue(all(row["type"] == "sale" for row in result["rows"]))
        self.assertTrue(all(row["currency"] == "EUR" and float(row["price"]) > 0 for row in result["rows"]))
        self.assertTrue(all(row["import_hints"]["wavespace_kind"] == "card_creation" for row in result["rows"]))
        static = APP / "static"
        script = (static / "app-v021000-197f97c6.js").read_text(encoding="utf-8")
        self.assertIn("localImportPrice", script)
        self.assertIn("2.99", script)
        self.assertIn("29.99", script)


    def test_goal_reached_timestamp_is_rendered_and_progress_is_capped(self):
        static = APP / "static"
        script = (static / "app-v021000-197f97c6.js").read_text(encoding="utf-8")
        style = (static / "style-v021000-197f97c6.css").read_text(encoding="utf-8")
        self.assertIn("goal.goal_reached_at", script)
        self.assertIn("goalReachedAt", script)
        self.assertIn("currentlyReached ? 100 : Math.min(99.9, rawProgress)", script)
        self.assertIn("fmtNumber(displayProgress,1)", script)
        self.assertIn("goal-reached", style)
        self.assertIn('row.type="sale"', script)

    def test_generic_btc_unit_column(self):
        result = self.parse("broker.csv", """Date,Action,Amount,Unit,Fiat Amount,Fiat Currency,Rate
2026-08-01,Buy,0.01,BTC,600,EUR,60000
""")
        self.assert_single(result, "Generischer CSV-Import", "purchase", "0.01", "EUR", "60000")

    def test_signed_btc_and_fiat_infer_purchase(self):
        result = self.parse("coinfinity-export.csv", """Date,BTC,EUR,Rate
2026-08-01,0.01,-600,60000
""")
        self.assert_single(result, "Coinfinity", "purchase", "0.01", "EUR", "60000")

    def test_kraken_trade_accepts_xbt_and_btc_pairs(self):
        for pair in ("XBTEUR", "BTCEUR", "XXBTZEUR"):
            with self.subTest(pair=pair):
                result = self.parse("kraken-trades.csv", f"""txid,ordertxid,pair,time,type,ordertype,price,cost,fee,vol
t1,o1,{pair},2026-08-01 12:00:00,buy,market,60000,600,1.5,0.01
""")
                self.assert_single(result, "Kraken Trades", "purchase", "0.01", "EUR", "60000")

    def test_optional_note_fields_are_disabled_by_default_in_ui(self):
        static = APP / "static"
        script = (static / "app-v021000-197f97c6.js").read_text(encoding="utf-8")
        html = (APP / "index.html").read_text(encoding="utf-8")
        style = (static / "style-v021000-197f97c6.css").read_text(encoding="utf-8")
        self.assertIn("result.optional_note_selection = [];", script)
        self.assertIn('id="csvOptionalFields"', html)
        self.assertIn('data-i18n="optionalFieldsTitle"', html)
        self.assertIn("overflow-y:auto", style)
        self.assertIn("min-height:100dvh", style)
        self.assertIn("grid-template-columns:1fr", style)
        self.assertIn("min-width:2050px", style)
        self.assertIn("font-size:16px", style)
        self.assertIn("min-width:1720px", style)
        self.assertIn("font-size:14px", style)
        self.assertIn("import-horizontal-control", style)
        self.assertIn('id="csvHorizontalScroll"', html)

    def test_zip_upload_is_read_in_memory(self):
        data = BytesIO()
        with ZipFile(data, "w", ZIP_DEFLATED) as archive:
            archive.writestr("relai.csv", "Type,Date,BTC Amount,Fiat Amount,Fiat Currency\nBuy,2026-08-01,0.01,600,EUR\n")
        result = parse_transaction_upload(data.getvalue(), "relai-export.zip")
        self.assertEqual(result["recognized"], 1)
        self.assertEqual(result["filename"], "relai.csv")
        self.assertFalse(result["raw_file_retained"])

    def test_altcoin_rows_are_skipped(self):
        result = self.parse("coinbase.csv", """Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,Spot Price at Transaction\n2026-08-01T12:00:00Z,Buy,ETH,1,EUR,3000\n2026-08-02T12:00:00Z,Buy,BTC,0.01,EUR,60000\n""")
        self.assertEqual(result["recognized"], 1)
        self.assertEqual(result["skipped"], 1)


if __name__ == "__main__":
    unittest.main()
