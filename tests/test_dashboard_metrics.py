from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]


def _load_modules():
    package_name = "bst_metrics_test_package"
    package = types.ModuleType(package_name)
    package.__path__ = []
    sys.modules[package_name] = package

    models = types.ModuleType(f"{package_name}.models")
    models.decimal_value = lambda value: Decimal(str(value or 0))
    sys.modules[models.__name__] = models

    fifo = types.ModuleType(f"{package_name}.fifo")
    fifo.__package__ = package_name
    fifo.__file__ = str(ROOT / "custom_components" / "bitcoin_stack_tracker" / "fifo.py")
    sys.modules[fifo.__name__] = fifo
    exec(compile(Path(fifo.__file__).read_text(), fifo.__file__, "exec"), fifo.__dict__)

    metrics = types.ModuleType(f"{package_name}.metrics")
    metrics.__package__ = package_name
    metrics.__file__ = str(ROOT / "custom_components" / "bitcoin_stack_tracker" / "metrics.py")
    sys.modules[metrics.__name__] = metrics
    exec(compile(Path(metrics.__file__).read_text(), metrics.__file__, "exec"), metrics.__dict__)
    return fifo, metrics


def entry(kind, ts, amount, *, price=None, fee=0, fee_btc=0, currency="EUR", depot="main", eid=None):
    row = {
        "id": eid or f"{kind}-{ts}",
        "type": kind,
        "timestamp": ts,
        "amount_btc": str(amount),
        "depot_id": depot,
        "note": "secret note must never enter metrics",
        "import_ref_hash": "a" * 64,
    }
    if kind != "stack":
        row.update({"currency": currency, "price": str(price), "fee": str(fee)})
    if fee_btc:
        row["fee_btc"] = str(fee_btc)
    return row


def test_metrics_are_compact_correct_and_privacy_preserving():
    fifo_mod, metrics_mod = _load_modules()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        entry("purchase", "2022-01-01T00:00:00+00:00", "1.0", price=10000, fee=10, fee_btc="0.00001", eid="p1"),
        entry("purchase", "2025-12-20T00:00:00+00:00", "0.5", price=20000, fee=20, eid="p2"),
        entry("sale", "2025-12-25T00:00:00+00:00", "0.2", price=30000, fee=30, eid="s1"),
    ]
    fifo = fifo_mod.fifo_result(rows, long_term_days=365, as_of=now)
    metrics = metrics_mod.build_dashboard_metrics(rows, fifo, {"EUR": Decimal("40000")}, ["EUR"], as_of=now)

    cur = metrics["currencies"]["EUR"]
    assert cur["net_invested_fiat"] == Decimal("14060")
    assert cur["fees"]["total_fiat"] == Decimal("60")
    assert cur["fees"]["btc_sats"] == Decimal("1000")
    assert cur["fees"]["purchase_ratio_percent"] == Decimal("0.1500")
    assert cur["fees"]["sale_ratio_percent"] == Decimal("0.500")
    assert cur["fees"]["btc_data_incomplete"] is False
    assert cur["profit"]["realized"] == Decimal("3968.0")
    assert cur["profit"]["unrealized"] is not None
    assert cur["profit"]["total"] == cur["profit"]["realized"] + cur["profit"]["unrealized"]
    assert cur["hodl_benchmark"]["complete"] is True
    assert cur["hodl_benchmark"]["benchmark_btc"] > 0
    assert cur["btc_cagr"]["percent"] is not None

    holding = metrics["holding"]
    assert holding["weighted_age_years"] > 0
    assert holding["oldest_open_lot_years"] > holding["weighted_age_years"]
    total_pct = sum((v["percent"] for v in holding["age_distribution"].values()), Decimal("0"))
    assert abs(total_pct - Decimal("100")) < Decimal("0.0000001")

    text = repr(metrics)
    assert "secret note" not in text
    assert "import_ref_hash" not in text
    assert "p1" not in text


def test_hodl_benchmark_refuses_hidden_fx_assumption():
    fifo_mod, metrics_mod = _load_modules()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        entry("purchase", "2025-01-01T00:00:00+00:00", "0.1", price=20000, currency="EUR", eid="eur"),
        entry("purchase", "2025-02-01T00:00:00+00:00", "0.1", price=22000, currency="USD", eid="usd"),
    ]
    fifo = fifo_mod.fifo_result(rows, long_term_days=365, as_of=now)
    metrics = metrics_mod.build_dashboard_metrics(rows, fifo, {"EUR": 40000, "USD": 45000}, ["EUR", "USD"], as_of=now)
    assert metrics["currencies"]["EUR"]["hodl_benchmark"]["complete"] is False
    assert metrics["currencies"]["USD"]["hodl_benchmark"]["complete"] is False


def test_stacking_speed_is_net_and_period_bounded():
    fifo_mod, metrics_mod = _load_modules()
    now = datetime(2026, 1, 31, tzinfo=timezone.utc)
    rows = [
        entry("purchase", "2026-01-10T00:00:00+00:00", "0.2", price=10000, eid="p"),
        entry("sale", "2026-01-20T00:00:00+00:00", "0.05", price=12000, eid="s"),
    ]
    fifo = fifo_mod.fifo_result(rows, as_of=now)
    metrics = metrics_mod.build_dashboard_metrics(rows, fifo, {"EUR": 12000}, ["EUR"], as_of=now)
    assert metrics["stacking_speed"]["30d"]["net_btc"] == Decimal("0.15")
    assert metrics["stacking_speed"]["30d"]["avg_sats_per_day"] == Decimal("500000")



def test_fee_ratios_are_volume_weighted_not_absolute_averages():
    fifo_mod, metrics_mod = _load_modules()
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    rows = [
        entry("purchase", "2025-01-01T00:00:00+00:00", "0.01", price=10000, fee=1, eid="small"),
        entry("purchase", "2025-02-01T00:00:00+00:00", "1.0", price=10000, fee=50, eid="large"),
        entry("sale", "2025-03-01T00:00:00+00:00", "0.10", price=12000, fee=6, eid="sale"),
    ]
    fifo = fifo_mod.fifo_result(rows, as_of=now)
    metrics = metrics_mod.build_dashboard_metrics(rows, fifo, {"EUR": 12000}, ["EUR"], as_of=now)
    fees = metrics["currencies"]["EUR"]["fees"]
    # Purchase gross volume = 100 + 10,000; fees = 51 -> weighted ratio.
    assert fees["purchase_ratio_percent"] == Decimal("51") / Decimal("10100") * Decimal("100")
    assert fees["sale_ratio_percent"] == Decimal("0.5")
    assert "avg_purchase_fiat" not in fees
    assert "avg_sale_fiat" not in fees


def test_legacy_coinfinity_onchain_fee_is_recovered_exactly_from_generated_note():
    fifo_mod, metrics_mod = _load_modules()
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    row = entry("purchase", "2025-01-01T00:00:00+00:00", "0.1", price=10000, fee=5, eid="legacy")
    row["note"] = "Coinfinity · On-Chain · Mining Fee: 1234 sats · Mining Fee: 0.12 EUR"
    fifo = fifo_mod.fifo_result([row], as_of=now)
    metrics = metrics_mod.build_dashboard_metrics([row], fifo, {"EUR": 12000}, ["EUR"], as_of=now)
    fees = metrics["currencies"]["EUR"]["fees"]
    assert fees["btc_sats"] == Decimal("1234")
    assert fees["btc_data_incomplete"] is False


def test_unknown_legacy_onchain_fee_is_not_reported_as_zero_with_false_certainty():
    fifo_mod, metrics_mod = _load_modules()
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    row = entry("purchase", "2025-01-01T00:00:00+00:00", "0.1", price=10000, fee=5, eid="legacy-pocket")
    row["note"] = "Onchain Pocket Bitcoin CSV-Import."
    fifo = fifo_mod.fifo_result([row], as_of=now)
    metrics = metrics_mod.build_dashboard_metrics([row], fifo, {"EUR": 12000}, ["EUR"], as_of=now)
    fees = metrics["currencies"]["EUR"]["fees"]
    assert fees["btc_sats"] == Decimal("0")
    assert fees["btc_data_incomplete"] is True


def test_priced_card_expense_counts_as_realized_disposal_not_fiat_return() -> None:
    fifo_mod, metrics_mod = _load_modules()
    now = datetime(2026, 1, 3, tzinfo=timezone.utc)
    rows = [
        entry("purchase", "2026-01-01T00:00:00+00:00", "0.01", price=50000, fee=0, eid="buy"),
        entry("expense", "2026-01-02T00:00:00+00:00", "0.00100371", price=60000, fee="0.22260", eid="card"),
    ]
    fifo = fifo_mod.fifo_result(rows, as_of=now)
    metrics = metrics_mod.build_dashboard_metrics(rows, fifo, {"EUR": 60000}, ["EUR"], as_of=now)
    cur = metrics["currencies"]["EUR"]
    assert cur["profit"]["realized"] == Decimal("9.81450000")
    # A card purchase consumes value but does not return fiat to the user.
    assert cur["sale_net_proceeds"] == Decimal("0")
    assert cur["net_invested_fiat"] == Decimal("500.00")
    # Its fiat fee still belongs in the total fee ratio.
    assert cur["fees"]["total_fiat"] == Decimal("0.22260")
