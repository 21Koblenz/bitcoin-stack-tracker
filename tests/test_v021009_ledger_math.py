from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = ROOT / "custom_components" / "bitcoin_stack_tracker"
PKG = "bst_v021009_testpkg"

pkg = types.ModuleType(PKG)
pkg.__path__ = [str(PKG_DIR)]
sys.modules.setdefault(PKG, pkg)


def load(name: str):
    full = f"{PKG}.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, PKG_DIR / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


models = load("models")
fifo = load("fifo")
metrics = load("metrics")


def D(value) -> Decimal:
    return Decimal(str(value))


class LedgerFeatureMathTests(unittest.TestCase):
    def test_income_creates_fifo_lot_like_purchase(self):
        rows = [{
            "id": "income1", "type": "income", "timestamp": "2026-01-01T00:00:00+00:00",
            "depot_id": "main", "amount_btc": "0.5", "currency": "EUR", "price": "80000", "fee": "10",
        }]
        result = fifo.fifo_result(rows)
        self.assertEqual(result["total_btc"], D("0.5"))
        summary = fifo.currency_summary_from_result(result, "EUR")
        self.assertEqual(summary["invested"], D("40010"))
        self.assertEqual(summary["income_fees"], D("10"))

    def test_expense_realizes_gain_like_sale_but_stays_expense(self):
        rows = [
            {"id":"buy","type":"purchase","timestamp":"2026-01-01T00:00:00+00:00","depot_id":"main","amount_btc":"1","currency":"EUR","price":"100","fee":"0"},
            {"id":"spend","type":"expense","timestamp":"2026-02-01T00:00:00+00:00","depot_id":"main","amount_btc":"0.25","currency":"EUR","price":"200","fee":"0"},
        ]
        result = fifo.fifo_result(rows)
        self.assertEqual(result["total_btc"], D("0.75"))
        self.assertEqual(result["realized"]["EUR"], D("25"))
        self.assertIn("spend", result["expenses"])
        self.assertNotIn("spend", result["sales"])
        self.assertEqual(result["expenses"]["spend"]["realized_gain"], D("25"))

    def test_network_fee_reduces_stack_with_zero_fiat_proceeds(self):
        rows = [
            {"id":"buy","type":"purchase","timestamp":"2026-01-01T00:00:00+00:00","depot_id":"main","amount_btc":"1","currency":"EUR","price":"100","fee":"0"},
            {"id":"fee","type":"network_fee","timestamp":"2026-02-01T00:00:00+00:00","depot_id":"main","amount_btc":"0.1","currency":"EUR","price":"200","network":"onchain"},
        ]
        result = fifo.fifo_result(rows)
        self.assertEqual(result["total_btc"], D("0.9"))
        self.assertEqual(result["realized"]["EUR"], D("-10"))
        fee = result["transaction_fees"]["fee"]
        self.assertEqual(fee["gross_proceeds"], D("0"))
        self.assertEqual(fee["fee_value_fiat"], D("20"))
        self.assertEqual(fee["cost_basis"], D("10"))
        self.assertEqual(fee["realized_gain"], D("-10"))
        summary = fifo.currency_summary_from_result(result, "EUR")
        self.assertEqual(summary["invested"], D("90"))
        # Economic reconciliation at a live BTC price of 200: open gain 90 plus
        # realized -10 = total +80 versus the original 100 EUR acquisition.
        unrealized = D("0.9") * D("200") - summary["invested"]
        self.assertEqual(unrealized + summary["realized_gain"], D("80"))

    def test_attached_btc_fee_only_affects_stack_when_explicitly_marked(self):
        base = {"id":"buy","type":"purchase","timestamp":"2026-01-01T00:00:00+00:00","depot_id":"main","amount_btc":"1","currency":"EUR","price":"100","fee":"0","fee_btc":"0.01"}
        result_analytics_only = fifo.fifo_result([base])
        self.assertEqual(result_analytics_only["total_btc"], D("1"))

        stack_affecting = dict(base, fee_btc_affects_stack=True)
        result_stack = fifo.fifo_result([stack_affecting])
        self.assertEqual(result_stack["total_btc"], D("0.99"))
        self.assertEqual(result_stack["realized"]["EUR"], D("-1"))

    def test_dashboard_metrics_keep_sales_expenses_income_and_network_fees_separate(self):
        rows = [
            {"id":"buy","type":"purchase","timestamp":"2026-01-01T00:00:00+00:00","depot_id":"main","amount_btc":"1","currency":"EUR","price":"100","fee":"1"},
            {"id":"income","type":"income","timestamp":"2026-01-02T00:00:00+00:00","depot_id":"main","amount_btc":"0.1","currency":"EUR","price":"100","fee":"0"},
            {"id":"sale","type":"sale","timestamp":"2026-02-01T00:00:00+00:00","depot_id":"main","amount_btc":"0.2","currency":"EUR","price":"200","fee":"2"},
            {"id":"expense","type":"expense","timestamp":"2026-02-02T00:00:00+00:00","depot_id":"main","amount_btc":"0.1","currency":"EUR","price":"200","fee":"1"},
            {"id":"fee","type":"network_fee","timestamp":"2026-02-03T00:00:00+00:00","depot_id":"main","amount_btc":"0.01","currency":"EUR","price":"200","network":"lightning"},
        ]
        result = fifo.fifo_result(rows)
        dashboard = metrics.build_dashboard_metrics(rows, result, {"EUR": D("200")}, ["EUR"])
        activity = dashboard["currencies"]["EUR"]["activity"]
        self.assertEqual(activity["sales"]["btc"], D("0.2"))
        self.assertEqual(activity["expenses"]["btc"], D("0.1"))
        self.assertEqual(activity["income"]["btc"], D("0.1"))
        self.assertEqual(activity["network_fees"]["btc"], D("0.01"))
        self.assertEqual(activity["network_fees"]["lightning_btc"], D("0.01"))
        self.assertEqual(activity["network_fees"]["value"], D("2.00"))
        fees = dashboard["currencies"]["EUR"]["fees"]
        self.assertEqual(fees["network_fee_fiat"], D("2.00"))
        self.assertEqual(fees["total_fiat_equivalent"], D("6.00"))
        # Standalone network fees have no trading volume and therefore must not
        # inflate the volume-weighted fee ratio denominator/numerator.
        self.assertEqual(fees["total_fiat"], D("4"))


if __name__ == "__main__":
    unittest.main()
