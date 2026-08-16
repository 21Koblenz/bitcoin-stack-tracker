from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
APP = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")
PANEL = (COMP / "frontend/panel.js").read_text(encoding="utf-8")
INIT = (COMP / "__init__.py").read_text(encoding="utf-8")
HISTORY = (COMP / "history.py").read_text(encoding="utf-8")
STORAGE = (COMP / "storage.py").read_text(encoding="utf-8")
INDEX = (COMP / "frontend/index.html").read_text(encoding="utf-8")


def test_intraday_chart_uses_either_exact_candles_or_whole_daily_fallback():
    chart = APP.split("function chartValues(currency, analytics = false)", 1)[1].split("function seriesChange", 1)[0]
    assert "history.market_candles?.[currency]" in chart
    assert "const usingExactIntraday = interval < 1440 && exactCount >= 2" in chart
    assert "const dailyFallback = history.prices?.[currency] || {}" in chart
    assert "const rawPrice = usingExactIntraday ? {...exactMarket} : {...dailyFallback}" in chart
    assert "price_samples" not in chart
    assert "{...exactMarket,...dailyFallback}" not in chart.replace(" ", "")


def test_provider_candles_are_stored_by_exact_interval():
    assert '"market_candles": {}' in STORAGE
    assert "async_merge_market_candles" in STORAGE
    assert "market_candles_for_days" in STORAGE
    assert "tiers[key] = ordered" in STORAGE
    assert "interval_minutes" in HISTORY
    assert "_fetch_exact_market_candles" in HISTORY
    assert "async_merge_market_candles" in HISTORY


def test_dashboard_requests_and_returns_exact_interval_tier():
    assert "history_interval=${chartIntervalMinutesForRange()}" in APP
    assert 'CONF_HISTORY_INTERVAL = "history_interval"' in INIT
    assert '"market_candles": limited_market_candles' in INIT
    assert '"market_interval_minutes": history_interval' in INIT


def test_user_can_force_refresh_selected_chart_prices():
    assert 'id="refreshChartPrices"' in INDEX
    assert "async function refreshChartPrices()" in APP
    assert "ensureIntradayHistory({force:true,interactive:true})" in APP
    assert "timeoutMs:180000" in APP


def test_native_panel_serializes_structured_home_assistant_errors():
    assert "function panelErrorText(error)" in PANEL
    assert "JSON.stringify(candidate)" in PANEL
    assert "reply.error = panelErrorText(error);" in PANEL
    assert "const errorText = error =>" in APP
    assert "JSON.stringify(candidate)" in APP


def test_manual_daily_sync_has_long_timeout_and_readable_error():
    assert 'service("sync_history",{config_entry_id:state.entryId},{timeoutMs:300000})' in APP
    assert "resultBox.textContent=errorText(error)" in APP
