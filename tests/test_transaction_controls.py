from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PARSER_DIR = ROOT / "custom_components" / "bitcoin_stack_tracker"
FRONTEND = PARSER_DIR / "frontend"
sys.path.insert(0, str(PARSER_DIR))

from csv_import import parse_transaction_upload  # noqa: E402


def test_generic_csv_preview_keeps_fiat_control_amount() -> None:
    raw = (
        "type;date;btc;currency;price per btc;fiat amount;fee\n"
        "purchase;2026-08-08 05:00;0.001;EUR;50000;50.50;0.50\n"
    ).encode()
    result = parse_transaction_upload(raw, "control.csv")
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["amount_btc"] == "0.001"
    assert row["price"] == "50000"
    assert row["fee"] == "0.50"
    assert row["fiat_amount"] == "50.50"


def test_csv_export_includes_fiat_total_control_column() -> None:
    source = (PARSER_DIR / "export.py").read_text(encoding="utf-8")
    assert '"fiat_total"' in source
    assert '"fiat_total": _value(net)' in source


def test_frontend_has_three_way_transaction_calculator_and_csv_controls() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    js = (FRONTEND / "static" / "app-v021006-733b783d.js").read_text(encoding="utf-8")
    assert 'name="fiat_total"' in html
    assert 'data-i18n="fiatTotal"' in html
    assert 'data-field="fiat_total"' in js
    assert 'data-field="amount_unit"' in js
    assert "function transactionFiatTotal" in js
    assert "function transactionPriceFromTotal" in js
    assert "function transactionAmountFromTotal" in js
    assert "function transactionControlCheck" in js
    assert 'if (type === "purchase") return gross + charge;' in js
    assert '(type === "sale" || type === "expense") ? total + charge : total' in js
    assert 'toast(t("fiatControlBlocked"))' in js


def test_satoshi_input_formatting_never_strips_integer_trailing_zeros() -> None:
    js = (FRONTEND / "static" / "app-v021006-733b783d.js").read_text(encoding="utf-8")
    assert r'return digits <= 0 ? fixed : fixed.replace(/\.?0+$/, "");' in js
    assert 'Math.round(btc * SATS_PER_BTC)' in js
