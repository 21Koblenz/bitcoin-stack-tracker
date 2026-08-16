from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components/bitcoin_stack_tracker"
CSV_PATH = COMP / "csv_import.py"
APP_PATH = COMP / "frontend/static/app.js"
INDEX_PATH = COMP / "frontend/index.html"
SENSOR_PATH = COMP / "sensor.py"
INIT_PATH = COMP / "__init__.py"
DIAG_PATH = COMP / "diagnostics.py"
NETWORK_PATH = COMP / "network.py"
ADDON = ROOT / "bitcoin_stack_tracker_dashboard"


def load_csv():
    spec = spec_from_file_location("bst_csv_privacy_test", CSV_PATH)
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_european_small_decimal_is_not_read_as_one_btc():
    parser = load_csv()
    assert parser._number("0,001 BTC") == Decimal("0.001")


def test_goal_frontend_has_local_date_fallback_and_no_false_rounded_100():
    app = APP_PATH.read_text(encoding="utf-8")
    assert "function goalReachedAtFromEntries(goal)" in app
    assert "goal.goal_reached_at || goalReachedAtFromEntries(goal)" in app
    assert "currentlyReached ? 100 : Math.min(99.9, rawProgress)" in app
    assert 'goalReachedAt:"Ziel erreicht am"' in app


def test_goal_sensor_is_capped_and_exposes_reached_attributes():
    sensor = SENSOR_PATH.read_text(encoding="utf-8")
    assert 'min(total / target * Decimal("100"), Decimal("100"))' in sensor
    assert '"goal_reached_at": reached_at' in sensor
    assert '"goal_ever_reached": reached_at is not None' in sensor


def test_backup_accepts_expenses_and_does_not_match_users_by_display_name():
    init = INIT_PATH.read_text(encoding="utf-8")
    assert '"purchase", "income", "sale", "stack", "expense", "network_fee"' in init
    assert "current_by_name" not in init
    assert "backup_name" not in init


def test_diagnostics_are_structurally_redacted():
    diag = DIAG_PATH.read_text(encoding="utf-8")
    assert '"settings_summary"' in diag
    assert '"settings": settings' not in diag
    assert '"history_errors"' not in diag
    assert '"coordinator_errors"' not in diag
    assert '"url"' not in diag
    assert '"entity_id"' not in diag


def test_current_version_and_native_assets_match():
    manifest = (COMP / "manifest.json").read_text(encoding="utf-8")
    index = INDEX_PATH.read_text(encoding="utf-8")
    panel = (COMP / "panel.py").read_text(encoding="utf-8")
    assert '"version": "0.21.0.11"' in manifest
    assert "app.js" in index
    assert "style.css" in index
    assert "panel.js" in panel


def test_secret_and_portfolio_data_path_excludes_tor_addon():
    init = INIT_PATH.read_text(encoding="utf-8")
    panel = (COMP / "panel.py").read_text(encoding="utf-8")
    agent = (ADDON / "app/network_agent.py").read_text(encoding="utf-8")
    assert 'url = "/api/bitcoin_stack_tracker/panel/rpc"' in init
    assert "Secrets therefore travel directly" in panel
    assert "portfolio_access\": False" in agent
    assert not (ADDON / "app/server.py").exists()


def test_auto_lock_is_configurable_and_can_be_disabled():
    app = APP_PATH.read_text(encoding="utf-8")
    index = INDEX_PATH.read_text(encoding="utf-8")
    assert 'localStorage.getItem("bst_auto_lock_minutes")' in app
    assert "[0,5,15,30,60,120]" in app
    assert 'id="autoLockMinutes"' in index
    assert '<option value="0" data-i18n="disabled">' in index
    assert "performAutoLock" in app
    assert 'service("lock_vault"' in app


def test_single_ledger_delete_uses_dashboard_modal_not_browser_confirm():
    app = APP_PATH.read_text(encoding="utf-8")
    index = INDEX_PATH.read_text(encoding="utf-8")
    assert 'id="deleteEntryModal"' in index
    assert "openDeleteEntryDialog(button.dataset.id)" in app
    assert "async function confirmDeleteEntry" in app
    ledger_start = app.index("function renderLedger()")
    ledger_end = app.index("function renderDepots()", ledger_start)
    assert 'confirm(t("confirmDelete"))' not in app[ledger_start:ledger_end]


def test_owner_live_connection_inventory_exposes_routes_not_secret_payloads():
    app = APP_PATH.read_text(encoding="utf-8")
    init = INIT_PATH.read_text(encoding="utf-8")
    network = NETWORK_PATH.read_text(encoding="utf-8")
    assert '"connection_inventory": _connection_inventory' in init
    assert 'route == "api/core-network"' in init
    assert '"connections": [' in network
    assert "_record_connection_start" in network
    assert "_record_connection_end" in network
    assert "function renderConnections()" in app
    assert "api/core-network?entry_id=" in app
    assert "body_text/form" in init


def test_public_networking_is_fail_closed_in_core_and_tor_gateway():
    network = NETWORK_PATH.read_text(encoding="utf-8")
    run = (ADDON / "run.sh").read_text(encoding="utf-8")
    assert "ClearnetBlockedError" in network
    assert "public_direct_allowed\": False" in network
    assert "rdns=True" in network
    assert 'comment "BST_AGENT_NO_EGRESS"' in run
    assert 'comment "BST_BLOCK_IPV4"' in run


def test_release_does_not_ship_stale_versioned_frontend_bundles():
    frontend = COMP / "frontend"
    static = frontend / "static"
    assert (frontend / "panel.js").is_file()
    assert (static / "app.js").is_file()
    assert (static / "style.css").is_file()
    assert not list(frontend.glob("panel-v*.js"))
    assert not list(static.glob("app-v*.js"))
    assert not list(static.glob("style-v*.css"))
