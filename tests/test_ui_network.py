from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
APP = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")
INDEX = (COMP / "frontend/index.html").read_text(encoding="utf-8")
INIT = (COMP / "__init__.py").read_text(encoding="utf-8")
HISTORY = (COMP / "history.py").read_text(encoding="utf-8")


def test_discreet_mode_hides_all_goal_surfaces_and_has_header_toggle():
    assert 'id="privacyButton"' in INDEX
    assert 'id="heroGoalCard"' in INDEX
    assert 'id="milestonesPanel"' in INDEX
    assert 'id="goalsStructurePanel"' in INDEX
    assert '["#heroGoalCard", "#milestonesPanel", "#goalsStructurePanel"]' in APP
    assert '$(`#goalCards`)' not in APP  # use fixed-id lookup, no dynamic exposure
    assert '$("#privacyButton").onclick=()=>applyDiscreetMode(!state.discreet);' in APP


def test_short_chart_auto_bootstraps_real_intraday_prices():
    assert 'async function ensureIntradayHistory({force=false,interactive=false} = {})' in APP
    assert 'api/history/intraday' in APP
    assert 'market_candles?.[currency]' in APP
    assert 'interval_minutes:interval' in APP
    assert 'enoughDensity' in APP
    assert 'enoughCoverage' in APP
    assert 'chartIntervalMinutesForRange()' in APP
    assert 'async def async_sync_intraday_history' in HISTORY
    assert 'async_merge_market_candles' in HISTORY
    assert "MARKET_OHLC_TIERS = (5, 15, 30, 60, 120, 240, 720, 1440)" in HISTORY
    assert 'proxy_url = tor_proxy_from_settings(settings)' in HISTORY


def test_cost_basis_is_step_projected_on_uniform_market_grid():
    chart = APP.split('function chartValues(currency)', 1)[1].split('function seriesChange', 1)[0]
    assert 'costBasis[day] = invested' not in chart
    assert 'projectStepSeries(basisEvents,grid)' in chart
    assert 'knownBtcOnGrid' in chart
    assert 'tracked * marketPrice - basis' in chart
    assert 'step:true' in APP


def test_tor_exit_ip_is_fetched_only_through_fail_closed_router():
    assert 'async def _panel_tor_exit_ip' in INIT
    assert 'proxy_url=DEFAULT_HISTORY_TOR_PROXY' in INIT
    assert 'https://check.torproject.org/api/ip' in INIT
    assert 'https://api.ipify.org?format=json' in INIT
    assert '"tor_exit_ip": tor_exit_ip' in INIT
    assert '"tor_exit_ip": None' not in INIT


def test_one_day_chart_is_a_true_rolling_24_hour_window():
    assert 'state.historyRange === "1"' in APP
    assert 'now - 24 * 60 * 60 * 1000' in APP
    assert 'chartTimestamp(day) >= cutoff' in APP


def test_overlay_opacity_changes_secondary_svg_series():
    assert 'id="overlayOpacityValue"' in INDEX
    assert 'min="0" max="100"' in INDEX
    assert 'stroke-opacity="${opacity.toFixed(2)}"' in APP
    assert 'bst_overlay_opacity' in APP
    assert 'overlayOpacityValue' in APP
