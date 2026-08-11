from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]


def _load_fifo_module():
    package_name = "bst_test_package"
    package = types.ModuleType(package_name)
    package.__path__ = []
    sys.modules[package_name] = package

    models = types.ModuleType(f"{package_name}.models")
    models.decimal_value = lambda value: Decimal(str(value or 0))
    sys.modules[models.__name__] = models

    module = types.ModuleType(f"{package_name}.fifo")
    module.__package__ = package_name
    module.__file__ = str(ROOT / "custom_components" / "bitcoin_stack_tracker" / "fifo.py")
    sys.modules[module.__name__] = module
    source = Path(module.__file__).read_text(encoding="utf-8")
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def test_fifo_uses_real_utc_instants_across_offsets() -> None:
    fifo = _load_fifo_module()
    # 2026-01-01 00:15 +02:00 == 2025-12-31 22:15 UTC and therefore precedes
    # the sale at 23:00 UTC, even though its ISO string starts with "2026".
    result = fifo.fifo_result(
        [
            {
                "id": "sale",
                "type": "sale",
                "timestamp": "2025-12-31T23:00:00Z",
                "depot_id": "main",
                "amount_btc": "0.5",
                "currency": "EUR",
                "price": "200",
                "fee": "0",
            },
            {
                "id": "buy",
                "type": "purchase",
                "timestamp": "2026-01-01T00:15:00+02:00",
                "depot_id": "main",
                "amount_btc": "1",
                "currency": "EUR",
                "price": "100",
                "fee": "0",
            },
        ],
        as_of=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    assert result["oversold_btc"] == Decimal("0")
    assert result["matches"][0]["purchase_id"] == "buy"
    assert result["matches"][0]["sale_id"] == "sale"
    assert result["matches"][0]["realized_gain"] == Decimal("50")


def test_oversold_match_allocates_its_share_of_sale_fee() -> None:
    fifo = _load_fifo_module()
    result = fifo.fifo_result(
        [
            {
                "id": "buy",
                "type": "purchase",
                "timestamp": "2026-01-01T00:00:00Z",
                "depot_id": "main",
                "amount_btc": "0.5",
                "currency": "EUR",
                "price": "100",
                "fee": "0",
            },
            {
                "id": "sale",
                "type": "sale",
                "timestamp": "2026-01-02T00:00:00Z",
                "depot_id": "main",
                "amount_btc": "1",
                "currency": "EUR",
                "price": "200",
                "fee": "10",
            },
        ],
        as_of=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )
    matches = result["matches"]
    assert len(matches) == 2
    # 5 EUR fee belongs to each 0.5 BTC half of the sale.
    assert matches[0]["net_proceeds"] == Decimal("95.0")
    assert matches[1]["net_proceeds"] == Decimal("95.0")
    assert sum((match["net_proceeds"] for match in matches), Decimal("0")) == Decimal("190.0")



def test_fifo_cursor_restarts_from_first_lot_on_fresh_recalculation_with_historical_insert() -> None:
    fifo = _load_fifo_module()
    # A later recalculation may contain a newly imported historical purchase.
    # The optimization cursor must not persist across fifo_result() calls.
    baseline = fifo.fifo_result(
        [
            {
                "id": "buy-newer",
                "type": "purchase",
                "timestamp": "2026-01-02T00:00:00Z",
                "depot_id": "main",
                "amount_btc": "1",
                "currency": "EUR",
                "price": "200",
                "fee": "0",
            },
            {
                "id": "sale",
                "type": "sale",
                "timestamp": "2026-01-03T00:00:00Z",
                "depot_id": "main",
                "amount_btc": "0.5",
                "currency": "EUR",
                "price": "300",
                "fee": "0",
            },
        ],
        as_of=datetime(2026, 1, 4, tzinfo=timezone.utc),
    )
    assert baseline["matches"][0]["purchase_id"] == "buy-newer"

    recalculated = fifo.fifo_result(
        [
            {
                "id": "buy-newer",
                "type": "purchase",
                "timestamp": "2026-01-02T00:00:00Z",
                "depot_id": "main",
                "amount_btc": "1",
                "currency": "EUR",
                "price": "200",
                "fee": "0",
            },
            {
                "id": "sale",
                "type": "sale",
                "timestamp": "2026-01-03T00:00:00Z",
                "depot_id": "main",
                "amount_btc": "0.5",
                "currency": "EUR",
                "price": "300",
                "fee": "0",
            },
            {
                "id": "buy-historical",
                "type": "purchase",
                "timestamp": "2026-01-01T00:00:00Z",
                "depot_id": "main",
                "amount_btc": "1",
                "currency": "EUR",
                "price": "100",
                "fee": "0",
            },
        ],
        as_of=datetime(2026, 1, 4, tzinfo=timezone.utc),
    )
    assert recalculated["matches"][0]["purchase_id"] == "buy-historical"
    assert recalculated["matches"][0]["realized_gain"] == Decimal("100.0")


def test_historical_sale_before_first_lot_is_still_detected_as_oversold() -> None:
    fifo = _load_fifo_module()
    result = fifo.fifo_result(
        [
            {
                "id": "buy",
                "type": "purchase",
                "timestamp": "2026-01-02T00:00:00Z",
                "depot_id": "main",
                "amount_btc": "1",
                "currency": "EUR",
                "price": "100",
                "fee": "0",
            },
            {
                "id": "sale-before-buy",
                "type": "sale",
                "timestamp": "2026-01-01T00:00:00Z",
                "depot_id": "main",
                "amount_btc": "0.5",
                "currency": "EUR",
                "price": "200",
                "fee": "0",
            },
        ],
        as_of=datetime(2026, 1, 4, tzinfo=timezone.utc),
    )
    assert result["oversold_btc"] == Decimal("0.5")
    assert result["matches"][0]["purchase_id"] is None
    assert result["matches"][0]["status"] == "insufficient_stack"


def test_priced_expense_is_fifo_disposal_but_keeps_expense_type() -> None:
    fifo = _load_fifo_module()
    result = fifo.fifo_result(
        [
            {
                "id": "buy",
                "type": "purchase",
                "timestamp": "2026-01-01T00:00:00Z",
                "depot_id": "main",
                "amount_btc": "0.01",
                "currency": "EUR",
                "price": "50000",
                "fee": "0",
            },
            {
                "id": "card",
                "type": "expense",
                "timestamp": "2026-01-02T00:00:00Z",
                "depot_id": "main",
                "amount_btc": "0.00100371",
                "currency": "EUR",
                "price": "60000",
                "fee": "0.22260",
            },
        ],
        as_of=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )
    assert len(result["matches"]) == 1
    match = result["matches"][0]
    assert match["disposition_type"] == "expense"
    assert match["sale_id"] == "card"
    assert match["net_proceeds"] == Decimal("60.00000000")
    assert match["cost_basis"] == Decimal("50.18550000")
    assert match["realized_gain"] == Decimal("9.81450000")
    assert result["realized"]["EUR"] == Decimal("9.81450000")
    assert result["expenses"]["card"]["status"] == "resolved"
    assert result["total_btc"] == Decimal("0.00899629")


def test_unpriced_expense_consumes_fifo_without_inventing_proceeds() -> None:
    fifo = _load_fifo_module()
    result = fifo.fifo_result(
        [
            {
                "id": "buy",
                "type": "purchase",
                "timestamp": "2026-01-01T00:00:00Z",
                "depot_id": "main",
                "amount_btc": "1",
                "currency": "EUR",
                "price": "100",
                "fee": "0",
            },
            {
                "id": "spend",
                "type": "expense",
                "timestamp": "2026-01-02T00:00:00Z",
                "depot_id": "main",
                "amount_btc": "0.25",
                "currency": "",
                "price": "0",
                "fee": "0",
            },
        ],
        as_of=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )
    match = result["matches"][0]
    assert match["disposition_type"] == "expense"
    assert match["net_proceeds"] is None
    assert match["realized_gain"] is None
    assert match["status"] == "unknown_proceeds"
    assert result["realized"].get("EUR", Decimal("0")) == Decimal("0")
    assert result["total_btc"] == Decimal("0.75")


def test_three_sales_plus_nine_card_expenses_produce_twelve_fifo_disposals() -> None:
    fifo = _load_fifo_module()
    rows = [
        {
            "id": "buy",
            "type": "purchase",
            "timestamp": "2026-01-01T00:00:00Z",
            "depot_id": "main",
            "amount_btc": "1",
            "currency": "EUR",
            "price": "50000",
            "fee": "0",
        }
    ]
    for index in range(3):
        rows.append({
            "id": f"sale-{index}",
            "type": "sale",
            "timestamp": f"2026-01-{index + 2:02d}T10:00:00Z",
            "depot_id": "main",
            "amount_btc": "0.01",
            "currency": "EUR",
            "price": "60000",
            "fee": "0",
        })
    for index in range(9):
        rows.append({
            "id": f"card-{index}",
            "type": "expense",
            "timestamp": f"2026-01-{index + 5:02d}T12:00:00Z",
            "depot_id": "main",
            "amount_btc": "0.01",
            "currency": "EUR",
            "price": "60000",
            "fee": "0",
        })
    result = fifo.fifo_result(rows, as_of=datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert len(result["matches"]) == 12
    assert sum(match["disposition_type"] == "sale" for match in result["matches"]) == 3
    assert sum(match["disposition_type"] == "expense" for match in result["matches"]) == 9
    assert len({match["sale_id"] for match in result["matches"]}) == 12
    assert len(result["sales"]) == 3
    assert len(result["expenses"]) == 9
