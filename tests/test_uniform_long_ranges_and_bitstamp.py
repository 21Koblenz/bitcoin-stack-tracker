from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
APP = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")
STYLE = (COMP / "frontend/static/style.css").read_text(encoding="utf-8")
HISTORY = (COMP / "history.py").read_text(encoding="utf-8")


def test_fixed_chart_resolution_by_selected_range():
    fn = APP.split("function chartIntervalMinutesForRange()", 1)[1].split("function resampleSeriesUniform", 1)[0]
    assert 'state.historyRange === "1") return 5' in fn
    assert 'state.historyRange === "30") return 60' in fn
    assert 'state.historyRange === "90") return 240' in fn
    assert 'state.historyRange === "ytd" || state.historyRange === "365") return 720' in fn
    assert "return 1440" in fn


def test_long_ranges_are_compacted_uniformly_across_the_entire_visible_window():
    assert "function longRangeUniformStepDays(values)" in APP
    assert "Math.ceil(spanDays / 520)" in APP
    assert "(gaps.length-1)*0.85" in APP
    assert "function resampleLongRangeUniform(values)" in APP
    chart = APP.split("function chartValues(currency)", 1)[1].split("function seriesChange", 1)[0]
    assert "resampleLongRangeUniform(rawPrice)" in chart


def test_ytd_and_one_year_never_go_blank_when_12h_provider_is_unavailable():
    chart = APP.split("function chartValues(currency)", 1)[1].split("function seriesChange", 1)[0]
    assert "const dailyFallback = history.prices?.[currency] || {}" in chart
    assert "usingExactIntraday ? {...exactMarket} : {...dailyFallback}" in chart
    assert 'interval === 720 && dailyFallbackCount >= 2' in APP
    assert 'chartDailyFallback' in APP


def test_bitstamp_redirects_are_fail_closed_and_same_provider_only():
    assert 'BITSTAMP_OHLC_HOSTS = {"bitstamp.net", "www.bitstamp.net"}' in HISTORY
    assert "def _validated_bitstamp_ohlc_redirect" in HISTORY
    assert 'parsed.scheme.lower() != "https"' in HISTORY
    assert 'host not in BITSTAMP_OHLC_HOSTS' in HISTORY
    assert 'not parsed.path.startswith("/api/v2/ohlc/")' in HISTORY
    assert 'response.status in {301, 302, 303, 307, 308}' in HISTORY
    assert '"allow_redirects": False' not in HISTORY  # routing layer still owns this globally


def test_partial_goal_progress_is_bitcoin_orange_not_only_completed_goals():
    assert 'class="goal-ring-progress"' in APP
    assert 'stroke-dasharray="${ringDash} ${ringGap}"' in APP
    assert '.goal-ring-progress{stroke:var(--orange)' in STYLE
    assert 'stroke-dasharray="100 100"' not in APP
