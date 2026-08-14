from __future__ import annotations

import ast
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import random
import re
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"


def _load_fifo_metrics():
    package_name = "bst_v021006_audit_package"
    for name in list(sys.modules):
        if name == package_name or name.startswith(package_name + "."):
            del sys.modules[name]
    package = types.ModuleType(package_name)
    package.__path__ = []
    sys.modules[package_name] = package

    models = types.ModuleType(f"{package_name}.models")

    def decimal_value(value, default="0"):
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(default)

    def btc_string(value):
        return format(Decimal(value).quantize(Decimal("0.00000001")), "f")

    def money_string(value):
        return format(Decimal(value).quantize(Decimal("0.00000001")), "f")

    models.decimal_value = decimal_value
    models.btc_string = btc_string
    models.money_string = money_string
    sys.modules[models.__name__] = models

    fifo = types.ModuleType(f"{package_name}.fifo")
    fifo.__package__ = package_name
    fifo.__file__ = str(COMP / "fifo.py")
    sys.modules[fifo.__name__] = fifo
    exec(compile(Path(fifo.__file__).read_text(), fifo.__file__, "exec"), fifo.__dict__)

    metrics = types.ModuleType(f"{package_name}.metrics")
    metrics.__package__ = package_name
    metrics.__file__ = str(COMP / "metrics.py")
    sys.modules[metrics.__name__] = metrics
    exec(compile(Path(metrics.__file__).read_text(), metrics.__file__, "exec"), metrics.__dict__)
    return fifo, metrics, models


def _extract_functions(path: Path, names: set[str], namespace: dict):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    selected = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


def _entry(eid, kind, ts, amount, *, price=None, fee=0, currency="EUR", depot="main"):
    row = {
        "id": eid,
        "type": kind,
        "timestamp": ts,
        "amount_btc": str(amount),
        "depot_id": depot,
        "note": "audit-secret-note",
    }
    if kind in {"purchase", "sale"} or (kind == "expense" and price is not None):
        row.update({"currency": currency, "price": str(price), "fee": str(fee)})
    return row


def test_fifo_partial_lot_remainder_and_weighted_basis_are_exact():
    fifo, _, _ = _load_fifo_metrics()
    rows = [
        _entry("p1", "purchase", "2025-01-01T00:00:00Z", "0.10", price=10000, fee=10),
        _entry("p2", "purchase", "2025-01-02T00:00:00Z", "0.20", price=20000, fee=20),
        _entry("p3", "purchase", "2025-01-03T00:00:00Z", "0.30", price=30000, fee=30),
        _entry("x1", "expense", "2025-02-01T00:00:00Z", "0.45", price=60000, fee=9),
        _entry("s2", "sale", "2025-03-01T00:00:00Z", "0.10", price=70000, fee=5),
    ]
    result = fifo.fifo_result(rows, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))
    x1 = [m for m in result["matches"] if m.get("disposition_id") == "x1"]
    assert [(m["purchase_id"], m["amount_btc"]) for m in x1] == [
        ("p1", Decimal("0.10")),
        ("p2", Decimal("0.20")),
        ("p3", Decimal("0.15")),
    ]
    # Purchase fee is part of each lot's unit basis: p1=10,100/BTC,
    # p2=20,100/BTC, p3=30,100/BTC.
    expected_x1_basis = (
        Decimal("0.10") * Decimal("10100")
        + Decimal("0.20") * Decimal("20100")
        + Decimal("0.15") * Decimal("30100")
    )
    assert sum((m["cost_basis"] for m in x1), Decimal("0")) == expected_x1_basis
    assert sum((m["net_proceeds"] for m in x1), Decimal("0")) == Decimal("0.45") * Decimal("60000") - Decimal("9")

    # The next disposal must consume the untouched remainder of p3 first.
    s2 = [m for m in result["matches"] if m.get("disposition_id") == "s2"]
    assert [(m["purchase_id"], m["amount_btc"]) for m in s2] == [("p3", Decimal("0.10"))]
    open_p3 = next(lot for lot in result["open_lots"] if lot["entry_id"] == "p3")
    assert open_p3["remaining_btc"] == Decimal("0.05")


def test_cumulative_average_entry_comparison_uses_all_purchases_to_disposal_time():
    fifo, _, _ = _load_fifo_metrics()
    rows = [
        _entry("p1", "purchase", "2025-01-01T00:00:00Z", "0.10", price=10000, fee=10),
        _entry("p2", "purchase", "2025-02-01T00:00:00Z", "0.20", price=30000, fee=20),
        _entry("s1", "sale", "2025-03-01T00:00:00Z", "0.15", price=40000, fee=15),
        # A later purchase changes the cumulative average, while p1/p2 remain
        # part of it even though s1 already disposed of some BTC.
        _entry("p3", "purchase", "2025-04-01T00:00:00Z", "0.10", price=50000, fee=10),
        _entry("s2", "expense", "2025-05-01T00:00:00Z", "0.05", price=45000, fee=5),
        # A different fiat currency must never be silently converted into EUR.
        _entry("usd", "purchase", "2025-01-15T00:00:00Z", "1", price=20000, fee=100, currency="USD"),
    ]
    averages = fifo.cumulative_average_entry_price_by_disposition(rows)
    expected_s1 = (
        Decimal("0.10") * Decimal("10000") + Decimal("10")
        + Decimal("0.20") * Decimal("30000") + Decimal("20")
    ) / Decimal("0.30")
    expected_s2 = (
        Decimal("0.10") * Decimal("10000") + Decimal("10")
        + Decimal("0.20") * Decimal("30000") + Decimal("20")
        + Decimal("0.10") * Decimal("50000") + Decimal("10")
    ) / Decimal("0.40")
    assert averages["s1"] == expected_s1
    assert averages["s2"] == expected_s2


def test_average_entry_same_timestamp_includes_purchase_before_disposal():
    fifo, _, _ = _load_fifo_metrics()
    ts = "2026-01-01T12:00:00Z"
    rows = [
        _entry("sale", "sale", ts, "0.05", price=30000, fee=0),
        _entry("purchase", "purchase", ts, "0.10", price=20000, fee=0),
    ]
    averages = fifo.cumulative_average_entry_price_by_disposition(rows)
    assert averages["sale"] == Decimal("20000")


def test_dashboard_fifo_average_comparison_is_separate_from_fifo_gain_and_private():
    fifo, _, models = _load_fifo_metrics()
    rows = [
        _entry("p1", "purchase", "2025-01-01T00:00:00Z", "0.10", price=10000, fee=10),
        _entry("p2", "purchase", "2025-02-01T00:00:00Z", "0.20", price=30000, fee=20),
        _entry("s1", "sale", "2025-03-01T00:00:00Z", "0.15", price=40000, fee=15),
    ]
    exact = fifo.fifo_result(rows, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))
    namespace = {
        "Any": object,
        "Decimal": Decimal,
        "deepcopy": __import__("copy").deepcopy,
        "decimal_value": models.decimal_value,
        "cumulative_average_entry_price_by_disposition": fifo.cumulative_average_entry_price_by_disposition,
    }
    _extract_functions(COMP / "__init__.py", {"_dashboard_fifo_matches"}, namespace)
    output = namespace["_dashboard_fifo_matches"](exact, rows)
    assert len(output) == 2  # s1 consumes p1 and part of p2
    expected_avg = (
        Decimal("0.10") * Decimal("10000") + Decimal("10")
        + Decimal("0.20") * Decimal("30000") + Decimal("20")
    ) / Decimal("0.30")
    assert all(row["average_entry_price_to_date"] == expected_avg for row in output)
    assert all("purchase_id" not in row and "sale_id" not in row and "disposition_id" not in row for row in output)
    # Average comparison is deliberately distinct from the FIFO gain, and the
    # proportional comparison gains add up to the whole outgoing booking.
    average_gain = sum((row["average_entry_gain"] for row in output), Decimal("0"))
    expected_net = Decimal("0.15") * Decimal("40000") - Decimal("15")
    expected_average_basis = Decimal("0.15") * expected_avg
    assert abs(average_gain - (expected_net - expected_average_basis)) <= Decimal("1e-20")
    fifo_gain = sum((row["realized_gain"] for row in output), Decimal("0"))
    assert fifo_gain != average_gain


def test_fifo_same_timestamp_incoming_btc_precedes_outgoing_btc():
    fifo, _, _ = _load_fifo_metrics()
    ts = "2026-01-01T12:00:00+00:00"
    rows = [
        _entry("z-sale", "sale", ts, "0.1", price=10000),
        _entry("a-buy", "purchase", ts, "0.1", price=9000),
    ]
    result = fifo.fifo_result(rows, as_of=datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert result["oversold_btc"] == Decimal("0")
    assert result["matches"][0]["purchase_id"] == "a-buy"


def test_fee_metrics_use_disposition_volume_including_card_expenses():
    fifo, metrics, _ = _load_fifo_metrics()
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    rows = [
        _entry("p", "purchase", "2025-01-01T00:00:00Z", "1", price=10000, fee=100),
        _entry("s", "sale", "2025-02-01T00:00:00Z", "0.1", price=20000, fee=20),
        _entry("e", "expense", "2025-03-01T00:00:00Z", "0.05", price=30000, fee=15),
    ]
    exact = fifo.fifo_result(rows, as_of=now)
    values = metrics.build_dashboard_metrics(rows, exact, {"EUR": 40000}, ["EUR"], as_of=now)
    fees = values["currencies"]["EUR"]["fees"]
    assert fees["sale_ratio_percent"] == Decimal("1")  # literal sales only
    assert fees["disposition_fiat"] == Decimal("35")
    assert fees["disposition_gross_volume"] == Decimal("3500")
    assert fees["disposition_ratio_percent"] == Decimal("1")
    assert values["currencies"]["EUR"]["sale_net_proceeds"] == Decimal("1980")
    # Merchant/card spending is not fiat returned to the portfolio owner.
    assert values["currencies"]["EUR"]["net_invested_fiat"] == Decimal("8120")


def test_visual_age_bucket_uses_tropical_year_but_holding_rule_remains_exact_days():
    fifo, metrics, _ = _load_fifo_metrics()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    acquired = now - timedelta(days=365, hours=3)  # > 365 rule, < 365.2425 visual year
    rows = [_entry("p", "purchase", acquired.isoformat(), "1", price=10000)]
    exact = fifo.fifo_result(rows, long_term_days=365, as_of=now)
    assert exact["long_term_btc"] == Decimal("1")
    holding = metrics.build_dashboard_metrics(rows, exact, {"EUR": 10000}, ["EUR"], as_of=now)["holding"]
    assert holding["over_rule_btc"] == Decimal("1")
    assert holding["age_distribution"]["under_1y"]["btc"] == Decimal("1")
    assert holding["age_distribution"]["1_to_2y"]["btc"] == Decimal("0")


def test_daily_fifo_snapshot_matches_exact_fifo_on_randomized_ledger():
    fifo, _, models = _load_fifo_metrics()
    namespace = {
        "Any": object,
        "date": date,
        "datetime": datetime,
        "time": time,
        "timezone": timezone,
        "decimal_value": models.decimal_value,
    }
    _extract_functions(COMP / "history.py", {"_timestamp_value", "_daily_fifo_snapshots"}, namespace)
    daily = namespace["_daily_fifo_snapshots"]

    rng = random.Random(21007)
    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    rows = []
    balance = Decimal("0")
    for idx in range(180):
        ts = start + timedelta(hours=18 * idx + rng.randint(0, 5))
        if balance < Decimal("0.03") or rng.random() < 0.58:
            amount = Decimal(rng.randint(1, 25)) / Decimal("1000")
            if rng.random() < 0.12:
                kind = "stack"
                row = _entry(f"i{idx:03d}", kind, ts.isoformat(), amount)
            else:
                kind = "purchase"
                row = _entry(f"i{idx:03d}", kind, ts.isoformat(), amount, price=20000 + idx * 37, fee=Decimal("0.75"))
            balance += amount
        else:
            max_milli = max(1, int(balance * 1000))
            amount = Decimal(rng.randint(1, max_milli)) / Decimal("1000")
            if amount > balance:
                amount = balance
            kind = "expense" if rng.random() < 0.45 else "sale"
            if kind == "expense" and rng.random() < 0.15:
                row = _entry(f"i{idx:03d}", kind, ts.isoformat(), amount)
            else:
                row = _entry(f"i{idx:03d}", kind, ts.isoformat(), amount, price=24000 + idx * 41, fee=Decimal("0.50"))
            balance -= amount
        rows.append(row)

    days = sorted({(start + timedelta(days=d)).date().isoformat() for d in range(0, 145, 7)})
    snapshots = daily(rows, days, 365)
    for day_key in days:
        as_of = datetime.combine(date.fromisoformat(day_key), time.max, tzinfo=timezone.utc)
        active = []
        for row in rows:
            parsed = datetime.fromisoformat(str(row["timestamp"]).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed.astimezone(timezone.utc) <= as_of:
                active.append(row)
        exact = fifo.fifo_result(active, long_term_days=365, as_of=as_of)
        expected = fifo.currency_summary_from_result(exact, "EUR")
        actual = snapshots[day_key]
        assert actual["total_btc"] == expected["total_btc"]
        assert actual["long_term_btc"] == exact["long_term_btc"]
        assert actual["short_term_btc"] == exact["short_term_btc"]
        for key in (
            "known_btc", "invested", "realized_gain", "realized_long_term_gain",
            "realized_short_term_gain", "purchase_fees", "sale_fees",
        ):
            assert abs(actual["currencies"].get("EUR", {}).get(key, Decimal("0")) - expected[key]) <= Decimal("1e-18"), (day_key, key)


def test_import_duplicate_flags_keep_distinct_source_ids_and_use_fee_btc_in_fallback():
    _, _, models = _load_fifo_metrics()
    namespace = {
        "Any": object,
        "datetime": datetime,
        "timezone": timezone,
        "Decimal": Decimal,
        "Counter": Counter,
        "re": re,
        "DEFAULT_DEPOT_ID": "main",
        "decimal_value": models.decimal_value,
        "btc_string": models.btc_string,
        "money_string": models.money_string,
    }
    _extract_functions(
        COMP / "storage.py",
        {"_normalized_utc_timestamp", "_transaction_fingerprint", "_import_ref_hash", "_preview_import_item", "_import_duplicate_flags"},
        namespace,
    )
    flags = namespace["_import_duplicate_flags"]
    base = {
        "type": "purchase", "timestamp": "2026-01-01T12:00:00+01:00", "depot_id": "main",
        "amount_btc": "0.01", "currency": "EUR", "price": "50000", "fee": "1",
    }
    ref_a = "a" * 64
    ref_b = "b" * 64
    assert flags([], [{**base, "import_ref_hash": ref_a}, {**base, "import_ref_hash": ref_b}]) == [False, False]
    assert flags([], [{**base, "import_ref_hash": ref_a}, {**base, "import_ref_hash": ref_a}]) == [False, True]
    # No source ID: a different exact BTC fee is a different financial fingerprint.
    assert flags([{**base, "timestamp": "2026-01-01T11:00:00Z", "fee_btc": "0.000001"}], [{**base, "fee_btc": "0.000002"}]) == [False]


def test_privacy_boundary_keeps_import_hashes_out_but_exposes_manual_btc_fee_fields_to_local_ui():
    init = (COMP / "__init__.py").read_text(encoding="utf-8")
    app = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")
    sanitizer = init.split("def _dashboard_ledger_entries", 1)[1].split("def _dashboard_ledger_fifo", 1)[0]
    assert '"import_ref_hash"' not in sanitizer
    assert '"fee_btc"' in sanitizer
    assert '"fee_btc_affects_stack"' in sanitizer
    assert '"note"' in sanitizer and '"id"' in sanitizer
    assert 'result["entries"] = _dashboard_ledger_entries(result["entries"])' in init
    preview = app.split("async function previewCsvImport", 1)[1].split("async function confirmCsvImport", 1)[0]
    assert 'ensureDashboardSection("ledger")' not in preview
    assert 'api/import/duplicates' in app


def test_xirr_refuses_silent_cross_fiat_conversion():
    app = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")
    block = app.split("function xirrAnalysis(currency)", 1)[1].split("function cashflowAdjustedPortfolioChange", 1)[0]
    assert "entryCurrency!==selectedCurrency" in block
    assert 'reason:"fx_required"' in block


def test_mutation_oversold_guard_is_atomic_and_allows_legacy_repairs():
    storage = (COMP / "storage.py").read_text(encoding="utf-8")
    assert "async def _async_validate_fifo_change" in storage
    assert "_oversold_increased(before_cache, after_cache)" in storage
    assert "candidate = before + [deepcopy(item)]" in storage
    assert "fifo_cache = await self._async_validate_fifo_change(before, candidate)" in storage
    assert "fifo_cache = await self._async_validate_fifo_change(current, combined)" in storage
    assert "fifo_cache = await self._async_validate_fifo_change(before, entries)" in storage
    assert "fifo_cache = await self._async_validate_fifo_change(before_entries, candidate)" in storage


def test_sensitive_frontend_responses_are_no_store_and_csp_blocks_direct_network():
    init = (COMP / "__init__.py").read_text(encoding="utf-8")
    index = (COMP / "frontend/index.html").read_text(encoding="utf-8")
    assert 'response.headers["Cache-Control"] = "no-store, private, max-age=0"' in init
    assert 'response.headers["Pragma"] = "no-cache"' in init
    assert 'response.headers["Referrer-Policy"] = "no-referrer"' in init
    assert "connect-src 'none'" in index
    assert "default-src 'none'" in index
    assert "object-src 'none'" in index


def test_randomized_fifo_matches_independent_queue_reference():
    fifo, _, _ = _load_fifo_metrics()
    rng = random.Random(721007)
    rows = []
    queue = []
    expected_matches = []
    balance = Decimal("0")
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for idx in range(240):
        ts = (start + timedelta(hours=idx * 11)).isoformat()
        if balance <= Decimal("0.02") or rng.random() < 0.61:
            amount = Decimal(rng.randint(1, 20)) / Decimal("1000")
            price = Decimal(15000 + idx * 53)
            fee = Decimal(rng.randint(0, 250)) / Decimal("100")
            row = _entry(f"p{idx}", "purchase", ts, amount, price=price, fee=fee)
            queue.append({"id": row["id"], "remaining": amount, "unit_basis": (amount * price + fee) / amount})
            balance += amount
        else:
            amount = min(balance, Decimal(rng.randint(1, max(1, int(balance * 1000)))) / Decimal("1000"))
            kind = "expense" if rng.random() < 0.4 else "sale"
            price = Decimal(18000 + idx * 71)
            fee = Decimal(rng.randint(0, 200)) / Decimal("100")
            row = _entry(f"d{idx}", kind, ts, amount, price=price, fee=fee)
            remaining = amount
            for lot in queue:
                if remaining <= 0:
                    break
                if lot["remaining"] <= 0:
                    continue
                used = min(lot["remaining"], remaining)
                lot["remaining"] -= used
                remaining -= used
                fee_share = fee * used / amount
                expected_matches.append((row["id"], lot["id"], used, used * lot["unit_basis"], used * price - fee_share))
            assert remaining == 0
            balance -= amount
        rows.append(row)

    result = fifo.fifo_result(rows, as_of=datetime(2030, 1, 1, tzinfo=timezone.utc))
    actual = [
        (m["disposition_id"], m["purchase_id"], m["amount_btc"], m["cost_basis"], m["net_proceeds"])
        for m in result["matches"]
    ]
    assert len(actual) == len(expected_matches)
    for got, want in zip(actual, expected_matches, strict=True):
        assert got[:3] == want[:3]
        assert abs(got[3] - want[3]) <= Decimal("1e-20")
        assert abs(got[4] - want[4]) <= Decimal("1e-20")
    expected_open = {lot["id"]: lot["remaining"] for lot in queue if lot["remaining"] > 0}
    actual_open = {lot["entry_id"]: lot["remaining_btc"] for lot in result["open_lots"]}
    assert actual_open == expected_open


def test_hodl_benchmark_uses_same_external_cashflows_for_sale_and_card_expense():
    fifo, metrics, _ = _load_fifo_metrics()
    now = datetime(2026, 1, 10, tzinfo=timezone.utc)
    rows = [
        _entry("p", "purchase", "2025-01-01T00:00:00Z", "1", price=10000, fee=100),
        _entry("s", "sale", "2025-06-01T00:00:00Z", "0.2", price=20000, fee=40),
        _entry("e", "expense", "2025-07-01T00:00:00Z", "0.1", price=30000, fee=30),
    ]
    exact = fifo.fifo_result(rows, as_of=now)
    result = metrics.build_dashboard_metrics(rows, exact, {"EUR": 40000}, ["EUR"], as_of=now)
    benchmark = result["currencies"]["EUR"]["hodl_benchmark"]
    expected = Decimal("1.01") - Decimal("3960") / Decimal("20000") - Decimal("2970") / Decimal("30000")
    assert benchmark["complete"] is True and benchmark["valid"] is True
    assert benchmark["benchmark_btc"] == expected == Decimal("0.713")
    assert benchmark["actual_btc"] == Decimal("0.7")
    assert benchmark["difference_btc"] == Decimal("-0.013")


def test_metrics_same_timestamp_order_matches_fifo_incoming_before_outgoing():
    fifo, metrics, _ = _load_fifo_metrics()
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    ts = "2026-01-01T12:00:00Z"
    # Intentionally hand the metrics layer the outgoing row first.  Equal-time
    # ordering must still match FIFO/storage semantics: incoming BTC first.
    rows = [
        _entry("sale", "sale", ts, "0.05", price=10000, fee=0),
        _entry("purchase", "purchase", ts, "0.10", price=10000, fee=0),
    ]
    exact = fifo.fifo_result(rows, as_of=now)
    result = metrics.build_dashboard_metrics(rows, exact, {"EUR": 10000}, ["EUR"], as_of=now)
    benchmark = result["currencies"]["EUR"]["hodl_benchmark"]
    assert exact["oversold_btc"] == Decimal("0")
    assert exact["total_btc"] == Decimal("0.05")
    assert benchmark["valid"] is True
    assert benchmark["benchmark_btc"] == Decimal("0.05")


def test_future_ledger_timestamp_is_rejected_beyond_small_clock_skew():
    _, _, models = _load_fifo_metrics()
    namespace = {
        "Any": object,
        "datetime": datetime,
        "timedelta": timedelta,
        "timezone": timezone,
        "MAX_LEDGER_FUTURE_SKEW": timedelta(minutes=5),
    }
    _extract_functions(
        COMP / "storage.py",
        {"_normalized_utc_timestamp", "_validated_ledger_timestamp"},
        namespace,
    )
    validate = namespace["_validated_ledger_timestamp"]
    reference = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert validate(reference + timedelta(minutes=4), now=reference).startswith("2026-01-01T12:04:00")
    try:
        validate(reference + timedelta(minutes=6), now=reference)
    except ValueError as err:
        assert "future" in str(err).lower()
    else:
        raise AssertionError("future ledger timestamp was accepted")
