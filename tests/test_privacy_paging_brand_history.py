from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
INIT = (COMP / "__init__.py").read_text(encoding="utf-8")
INDEX = (COMP / "frontend/index.html").read_text(encoding="utf-8")
APP = (COMP / "frontend/static/app-v021010-f51973f8.js").read_text(encoding="utf-8")
CSS = (COMP / "frontend/static/style-v021010-c577172d.css").read_text(encoding="utf-8")


def test_discreet_switch_only_rerenders_visible_sensitive_tab():
    helper = APP.split("function renderDiscreetSensitiveViews()", 1)[1].split("function applyDiscreetMode", 1)[0]
    assert "renderActivePortfolioTab();" in helper
    assert "renderAll();" not in helper
    activate = APP.split("function activateTab", 1)[1].split("async function boot", 1)[0]
    assert 'renderActiveTabContent(selected)' in activate
    assert 'selected === "settings"' in activate


def test_dca_personal_year_purchase_count_is_masked_in_discreet_mode():
    assert 'const visiblePurchaseCount = state.discreet ? "***" : fmtNumber(rows.length,0);' in APP
    assert '${esc(visiblePurchaseCount)} ${esc(t("purchasesInRange"))}' in APP


def test_ledger_has_year_filter_and_pagination():
    assert 'id="ledgerPeriodFilter"' in INDEX
    assert 'id="ledgerPagination"' in INDEX
    assert "ledgerPageSize: 25" in APP
    assert "function renderLedgerPeriodOptions" in APP
    assert 'filter.startsWith("year:")' in APP
    assert "function renderLedgerPagination" in APP
    assert ".ledger-pagination" in CSS


def test_moscow_time_follows_selected_chart_currency_and_block_tip_is_minute_fresh():
    assert 'const currency = currentCurrency();' in APP
    assert 'const fiatPrice = Number(state.data?.prices?.[currency]);' in APP
    assert 'moscowUnit.textContent = `sats / ${currency}`' in APP
    assert 'Date.now() - bitcoinNetworkRefreshAt >= 60 * 1000' in APP
    assert '_HALVING_CACHE_TTL = timedelta(minutes=1)' in INIT


def test_custom_integration_ships_home_assistant_brand_assets():
    assert (COMP / "brand" / "icon.png").is_file()
    assert (COMP / "brand" / "logo.png").is_file()
    assert (COMP / "brand" / "icon.png").stat().st_size > 1000
    assert (COMP / "brand" / "logo.png").stat().st_size > 1000


def test_history_auto_sync_retries_incomplete_backfill_without_manual_button():
    assert '_HISTORY_AUTO_CHECK_INTERVAL = timedelta(hours=6)' in INIT
    assert '_HISTORY_COMPLETE_SYNC_INTERVAL = timedelta(hours=20)' in INIT
    helper = INIT.split("def _configure_history_timer", 1)[1].split("def _validate_positive_transaction", 1)[0]
    assert 'hass, _scheduled_sync, _HISTORY_AUTO_CHECK_INTERVAL' in helper
    assert 'incomplete = _history_bootstrap_incomplete(entry, runtime)' in helper
    assert 'or incomplete' in helper
    assert 'hass.async_create_task(_scheduled_sync(dt_util.utcnow()))' in helper
    assert 'runtime["history_auto_timer_active"] = True' in helper
    dashboard = INIT.split('"history": {', 1)[1].split('"currencies":', 1)[0]
    assert '"auto_sync_runtime_active"' in dashboard
    assert '"auto_sync_last_attempt"' in dashboard
