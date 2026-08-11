from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "custom_components/bitcoin_stack_tracker/frontend/static/app.js").read_text(encoding="utf-8")
INDEX = (ROOT / "custom_components/bitcoin_stack_tracker/frontend/index.html").read_text(encoding="utf-8")
INIT = (ROOT / "custom_components/bitcoin_stack_tracker/__init__.py").read_text(encoding="utf-8")
CSS = (ROOT / "custom_components/bitcoin_stack_tracker/frontend/static/style.css").read_text(encoding="utf-8")

def test_final_release_version_is_visible():
    assert 'const BUILD_VERSION = "0.21.0.6";' in APP

def test_fifo_summary_explicitly_names_both_methods():
    assert 'fifoAndAverageSummary:"Abgangsübersicht · FIFO + Ø-Kaufpreis"' in APP
    assert 'fifoLotMethod:"FIFO-Lot-Berechnung"' in APP
    assert 'Ø BIS ZUM ABGANG' in APP

def test_mobile_fifo_cards_have_explicit_average_section():
    assert 'class="fifo-average-mobile-heading"' in APP
    assert '.fifo-average-mobile-heading{grid-column:1/-1' in CSS
    for key in ("averageEntryToDate", "averageEntryBasis", "averageEntryGain", "averageEntryReturn"):
        assert f't("{key}")' in APP

def test_fifo_api_payload_attaches_historical_average_comparison():
    assert 'average_entry_by_disposition = cumulative_average_entry_price_by_disposition(entries)' in INIT
    assert 'row["average_entry_price_to_date"] = average_entry_price' in INIT
    assert 'row["average_entry_gain"] = average_gain' in INIT
    assert 'row["average_entry_return_percent"]' in INIT

def test_fifo_table_still_has_fifo_and_average_columns():
    for text in ("FIFO-Einstand", "FIFO-Gewinn/Verlust", "FIFO-Rendite", "Ø Einkauf bis dahin", "Ø-Vergleichseinstand", "Ø-Gewinn/Verlust", "Ø-Rendite"):
        assert text in INDEX
