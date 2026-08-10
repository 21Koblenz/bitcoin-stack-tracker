from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
APP = (COMP / "frontend/static/app-v021002-81aa3197.js").read_text(encoding="utf-8")
PANEL = (COMP / "frontend/panel-v021002-81aa3197.js").read_text(encoding="utf-8")
INDEX = (COMP / "frontend/index.html").read_text(encoding="utf-8")
CSS = (COMP / "frontend/static/style-v021002-81aa3197.css").read_text(encoding="utf-8")


def function_block(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def test_today_profit_loss_requests_previous_fifo_boundary():
    block = function_block(APP, "function historyDaysForRange()", "function chartIntervalMinutesForRange()")
    assert "return displayDays + 1;" in block
    assert 'state.historyRange === "1" ? 0 : 1' not in block


def test_load_data_does_not_block_on_live_network_refresh():
    block = function_block(APP, "async function loadData()", "async function ensureIntradayHistory")
    assert "void refreshNetworkStatus({silent:true});" in block
    assert "await refreshNetworkStatus({silent:true});" not in block


def test_heavy_views_are_rendered_only_for_active_tab():
    # Last function declaration wins in JavaScript, so inspect the final renderAll.
    block = APP.rsplit("function renderAll(){", 1)[1].split("function backupAgeLabel", 1)[0]
    assert "renderActiveTabContent(state.activeTab);" in block
    assert "renderLedger();" not in block
    assert "renderTax();" not in block
    assert "renderConnections();" not in block


def test_security_user_list_is_lazy_loaded():
    active = function_block(APP, "function renderActiveTabContent", "function renderAll()")
    assert 'selected === "security"' in active
    assert "api(`api/security/users?entry_id=" in active


def test_mobile_and_desktop_ledger_are_not_built_at_same_time():
    block = function_block(APP, "function renderLedger()", "function fifoPageButtons")
    assert "const compactLayout = compactTableLayout();" in block
    assert '$("#ledgerBody").innerHTML = compactLayout ? "" :' in block
    assert 'cards.innerHTML = !compactLayout ? "" :' in block


def test_fifo_sales_have_requested_columns_summary_and_paging():
    for key in (
        'data-i18n="sale">Verkauf',
        'data-i18n="purchasePriceThen">Kaufkurs damals',
        'data-i18n="fifoCostBasis">FIFO-Einstand',
        'data-i18n="salePrice">Verkaufskurs',
        'data-i18n="saleProceeds">Verkaufserlös',
        'data-i18n="gain">Gewinn/Verlust',
        'data-i18n="returnPercent">Rendite',
    ):
        assert key in INDEX
    assert 'id="fifoSaleSummary"' in INDEX
    assert 'id="fifoPagination"' in INDEX
    block = function_block(APP, "function renderTax()", "function networkRoute")
    assert "Number(state.ledgerPageSize)||25" in block
    assert "renderFifoPagination(allMatches.length,totalPages,pageStart,pageEnd);" in block
    assert "const compactLayout=compactTableLayout();" in block


def test_fifo_page_change_scrolls_its_own_view_to_top():
    block = function_block(APP, "function renderFifoPagination", "function renderFifoSaleSummary")
    assert "scrollFifoPageToStart();" in block
    helper = function_block(APP, "function scrollFifoPageToStart", "function renderFifoPagination")
    assert "scrollTo({top:0" in helper
    assert 'document.querySelector("#fifoCards")?.scrollIntoView' in helper


def test_log_keeps_chronological_order_but_opens_at_latest_entry():
    block = function_block(APP, "async function loadLogs()", "function renderNetworkStatus")
    assert '.map(row=>`${row.time||""}' in block
    assert "output.scrollTop=output.scrollHeight" in block
    assert ".reverse()" not in block


def test_menu_button_uses_home_assistant_custom_panel_event_path():
    menu = function_block(PANEL, "  _openHomeAssistantMenu()", "  _render()")
    assert 'this.dispatchEvent(new CustomEvent("hass-toggle-menu"' in menu
    assert 'bubbles: true' in menu
    assert 'composed: true' in menu
    # Do not reach into private HA shadow-DOM fields or Companion internals.
    assert 'home-assistant-main' not in menu
    assert '._drawerOpen' not in menu
    assert 'external.fireMessage' not in menu


def test_messagechannel_regression_stays_removed():
    assert "MessageChannel" not in PANEL
    assert "nativeBridgeReady" not in APP
    assert 'event.origin !== window.location.origin' in PANEL
    assert 'event.source !== this._frame.contentWindow' in PANEL


def test_fifo_fiat_values_hide_cleanly_in_fiat_free_mode():
    assert "body.fiat-free-mode .fifo-fiat-metric{display:none!important}" in CSS


def test_hidden_network_inventory_is_not_polled_globally():
    block = function_block(APP, "function startNetworkPolling()", "function renderSecurity")
    assert "},30000);" in block
    assert 'if(state.activeTab==="settings")' in block
    assert 'state.activeTab==="settings" ||' not in block
    prefix = block.split('if(state.activeTab==="settings")', 1)[0]
    assert "refreshConnectionInventory" not in prefix
    assert "loadTorRotationSettings" not in prefix


def test_cost_and_profit_loss_charts_keep_the_same_filled_visual_language():
    block = function_block(APP, "function chartSeries(mode,currency)", "function currentProfitMetrics")
    assert 'const pnl=(extra={})=>fiat("pnl",t("profitLossHistory"),values.totalProfitLoss,{allowNegative:true,...extra});' in block
    assert 'cost_pnl:[fiat("cost",t("openCostBasis"),values.costBasis,{step:true}),unrealized({secondary:true})]' in block
    assert 'fill:false' not in block
    render = function_block(APP, "function renderChart()", "function renderLedger")
    assert 'const areaBaseline = series[0].allowNegative' in render
    assert '? y(0,0)' in render


def test_intraday_fifo_state_is_replayed_after_every_booking():
    block = function_block(APP, "function chartValues(currency, analytics = false)", "function seriesChange")
    assert 'const metricEvents = fifoMetricEvents(currency)' in block
    assert 'basisEvents[item.key] = item.basis;' in block
    assert 'realizedEvents[item.key] = item.realized;' in block
    assert 'knownEvents[item.key] = item.knownBtc;' in block
    assert 'const latestLedgerChange = types =>' not in block
