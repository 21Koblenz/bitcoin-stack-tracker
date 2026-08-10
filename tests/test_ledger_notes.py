from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "custom_components" / "bitcoin_stack_tracker" / "frontend"


def test_desktop_ledger_places_note_below_transaction_row():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    app = (FRONTEND / "static" / "app-v021002-81aa3197.js").read_text(encoding="utf-8")
    css = (FRONTEND / "static" / "style-v021002-81aa3197.css").read_text(encoding="utf-8")
    ledger_header = html.split('id="ledgerBody"', 1)[0].rsplit('<thead>', 1)[-1]
    assert '<th data-i18n="note">Notiz</th>' not in ledger_header
    assert 'ledger-note-row' in app
    assert 'class="ledger-note-date-spacer"' in app
    assert 'colspan="8"' in app
    assert 'ledger-note-block' in app
    assert 'ledger-detail-label' in app
    assert '.ledger-note-row td{' in css
    assert 'ledger-note-cell' not in app


def test_mobile_ledger_keeps_note_below_card():
    app = (FRONTEND / "static" / "app-v021002-81aa3197.js").read_text(encoding="utf-8")
    assert 'ledger-mobile-note' in app
    assert 'ledger-note-block' in app
    assert 'ledger-detail-label' in app
