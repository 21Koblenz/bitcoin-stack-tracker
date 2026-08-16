from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "custom_components/bitcoin_stack_tracker/frontend/static/app.js").read_text()
STYLE = (ROOT / "custom_components/bitcoin_stack_tracker/frontend/static/style.css").read_text()
INDEX = (ROOT / "custom_components/bitcoin_stack_tracker/frontend/index.html").read_text()
PANEL = (ROOT / "custom_components/bitcoin_stack_tracker/panel.py").read_text()


def test_tx_details_open_state_survives_rerender():
    assert "state.walletWatchOpenTxDetails = new Set();" in APP
    assert 'state.walletWatchOpenTxDetails.has(String(mon.id))?"open":""' in APP
    assert 'state.walletWatchOpenTxDetails.add(id)' in APP
    assert 'state.walletWatchOpenTxDetails.delete(id)' in APP
    assert 'if(details.open&&details.dataset.pendingSave!=="1")' in APP


def test_tx_direction_and_amount_have_explicit_layout_hook():
    assert 'class="sats-sentinel-tx-direction-cell"' in APP
    assert ".sats-sentinel-tx-direction-cell .sats-sentinel-direction-badge{margin-bottom:7px}" in STYLE
    assert ".sats-sentinel-tx-direction-cell>small{display:block" in STYLE


def test_summary_balance_and_address_count_are_separate_blocks():
    assert ".sats-sentinel-tx-summary strong{display:block" in STYLE
    assert ".sats-sentinel-tx-summary small{display:block;margin-top:6px" in STYLE


def test_sentinel_checkbox_groups_are_aligned():
    assert '#tab-walletwatch .form-grid>label:has(>input[type="checkbox"])' in STYLE
    assert "#walletWatchNotifyServices label{" in STYLE
    for text in [
        "Sats Sentinel aktiv", "TLS / SSL", "TLS-Zertifikat prüfen",
        "Konfigurierte öffentliche Mempool-Quelle über Tor nutzen",
        "Persistente HA-Meldung", "Eingänge alarmieren", "Ausgänge alarmieren",
        "HA-Event auslösen", "HA-Persistent-Meldung", "Ausgewählte Handy-Pushs",
        "ntfy / Webhooks",
    ]:
        assert text in INDEX


def test_stable_frontend_cache_bust_is_active():
    assert 'panel.js?v={VERSION}' in PANEL
    assert 'index.html?native=1&v={VERSION}' in PANEL
    assert '?v=0.21.0.11' in INDEX
    assert 'app-v021010-' not in INDEX



def test_sentinel_top_level_cards_are_collapsible_and_persist_per_portfolio():
    expected = {
        "status": "open",
        "journal": "open",
        "test": "collapsed",
        "settings": "collapsed",
        "targets": "open",
        "privacy": "collapsed",
    }
    for key, default in expected.items():
        assert f'data-sentinel-panel="{key}" data-sentinel-default="{default}"' in INDEX
    assert 'function walletWatchPanelStorageKey()' in APP
    assert 'bst_walletwatch_panel_state:${state.entryId||"default"}' in APP
    assert 'function walletWatchPanelPreferences()' in APP
    assert 'function initWalletWatchPanelToggles()' in APP
    assert 'localStorage.setItem(walletWatchPanelStorageKey(),JSON.stringify(prefs))' in APP
    assert '.sats-sentinel-panel-body' in APP
    assert '.sats-sentinel-panel-toggle' in APP
    assert '.sats-sentinel-panel-toggle{' in STYLE
