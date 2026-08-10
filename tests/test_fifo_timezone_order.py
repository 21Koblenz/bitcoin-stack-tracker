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
