from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
APP = (COMP / "frontend/static/app-v021006-733b783d.js").read_text(encoding="utf-8")
INDEX = (COMP / "frontend/index.html").read_text(encoding="utf-8")
INIT = (COMP / "__init__.py").read_text(encoding="utf-8")
FIFO = (COMP / "fifo.py").read_text(encoding="utf-8")
HISTORY = (COMP / "history.py").read_text(encoding="utf-8")


def test_fifo_matches_include_expenses_as_disposals_without_retyping_ledger_entry():
    assert '"disposition_type": "expense"' in FIFO
    assert '"disposition_type": "sale"' in FIFO
    assert 'if kind == "expense":' in FIFO
    assert 'expenses[str(item.get("id"))] = expense_summary' in FIFO


def test_fifo_dashboard_does_not_expose_internal_disposition_uuid():
    assert 'if key not in {"purchase_id", "sale_id", "disposition_id"}' in INIT
    assert 'row["disposition_index"] = disposition_indexes.get(outgoing_id)' in INIT
    assert 'row["disposition_type"]' not in INIT  # carried from safe FIFO row, not reconstructed from ledger


def test_fifo_ui_labels_sales_and_expenses_separately_and_counts_bookings_not_matches():
    assert 'data-i18n="dispositionType">Art' in INDEX
    assert 'FIFO ABGÄNGE' in INDEX
    assert 'dispositionLabel=match=>' in APP
    assert 't("dispositionExpense")' in APP
    assert 't("dispositionSale")' in APP
    assert 'const dispositionCount=new Set' in APP


def test_daily_fifo_history_treats_priced_expenses_as_disposals():
    assert 'if kind == "expense":' in HISTORY
    assert 'sale_currency=expense_currency' in HISTORY
    assert 'sale_price=expense_price' in HISTORY
    assert '"chart_schema": 5' in HISTORY
