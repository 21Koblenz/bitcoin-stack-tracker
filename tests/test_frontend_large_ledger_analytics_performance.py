from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "custom_components/bitcoin_stack_tracker/frontend/static/app-v021007-050b734c.js").read_text(encoding="utf-8")


def _block(start: str, end: str) -> str:
    return APP.split(start, 1)[1].split(end, 1)[0]


def test_overview_defers_expensive_performance_analytics_until_browser_is_idle():
    chart = _block("function renderChart()", "function ledgerTypeClass")
    assert "schedulePerformanceSummary(currency);" in chart
    assert "renderPerformanceSummary(currency);" not in chart
    scheduler = _block("function schedulePerformanceSummary(currency)", "function scheduleViewportSettledWork")
    assert "requestIdleCallback" in scheduler
    assert 'state.activeTab !== "overview"' in scheduler


def test_switching_tabs_cancels_pending_overview_analytics():
    block = _block("function activateTab", "async function boot")
    assert 'if (selected !== "overview") cancelScheduledPerformanceSummary();' in block


def test_dashboard_refresh_invalidates_derived_frontend_caches():
    block = _block("async function loadData()", "async function ensureIntradayHistory")
    assert "invalidateDerivedCaches();" in block
    chart_values = _block("function chartValues(currency, analytics = false)", "function analyticsValues")
    assert 'derivedCacheKey("chartValues"' in chart_values
    assert "derivedCache.set(cacheKey,result);" in chart_values


def test_market_price_lookup_is_binary_and_does_not_resort_for_every_trade():
    lookup = _block("function valueOnOrBeforePoints", "function valueOnOrBefore(series")
    assert "while (low <= high)" in lookup
    perf = _block("function performanceLedgerEvents", "function performancePricePoints")
    assert "const pricePoints = sortedNumericPoints(priceSeries);" in perf
    assert "valueOnOrBeforePoints(pricePoints,time)" in perf
    assert "valueOnOrBefore(priceSeries" not in perf


def test_intraday_fifo_metrics_use_incremental_totals_and_per_depot_cursor():
    block = _block("function fifoMetricEvents(currency)", "function chartValues")
    assert "cursorByDepot" in block
    assert "let realized = 0, basis = 0, knownBtc = 0;" in block
    assert "metricState" not in block
    assert "while (cursor < lots.length && remaining > 1e-15)" in block


def test_background_halving_refresh_never_rebuilds_hidden_overview_chart():
    block = _block("async function loadHalvings", "async function loadData")
    assert 'if (state.activeTab === "overview") renderChart();' in block

PERFORMANCE_MATH = (ROOT / "custom_components/bitcoin_stack_tracker/frontend/static/performance-math-v021006-733b783d.js").read_text(encoding="utf-8")


def test_xirr_normalizes_and_sorts_flows_once_per_solve():
    assert "function xnpvClean(rate, clean)" in PERFORMANCE_MATH
    solve = PERFORMANCE_MATH.split("function xirrSolveDetailed", 1)[1].split("function maximumDrawdown", 1)[0]
    assert "const value = xnpvClean(rate, clean);" in solve
    assert "const value = xnpv(rate, clean);" not in solve
