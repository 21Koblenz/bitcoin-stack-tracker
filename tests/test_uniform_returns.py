from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
APP = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")
HISTORY = (COMP / "history.py").read_text(encoding="utf-8")
RUN = (ROOT / "bitcoin_stack_tracker_dashboard/run.sh").read_text(encoding="utf-8")


def test_each_range_uses_one_uniform_finest_practical_interval():
    assert "function chartIntervalMinutesForRange()" in APP
    assert 'state.historyRange === "1") return 5' in APP
    assert 'state.historyRange === "30" || state.historyRange === "month_start") return 60' in APP
    assert 'state.historyRange === "90") return 240' in APP
    assert 'state.historyRange === "ytd" || state.historyRange === "365") return 720' in APP
    assert "function resampleSeriesUniform" in APP
    assert "function resampleLongRangeUniform" in APP
    assert "const interval = chartIntervalMinutesForRange();" in APP
    assert "return (_market_ohlc_interval_for_days(history_days),)" in HISTORY
    assert "BITSTAMP_OHLC_LIMIT = 1000" in HISTORY


def test_portfolio_curve_is_derived_on_same_price_grid_as_market_curve():
    assert "function ledgerStackAndPortfolio(priceSeries)" in APP
    assert "portfolio[point.day] = stack * point.value" in APP
    assert "const {stackBtc,portfolio} = ledgerStackAndPortfolio(price);" in APP


def test_twr_and_xirr_use_exact_cashflow_splits_and_audited_math_module():
    assert "function performanceLedgerEvents(currency, priceSeries)" in APP
    assert "math.timeWeightedReturn" in APP
    assert "math.xirrSolveDetailed" in APP
    assert "function seriesValuationTimestamp(key)" in APP
    assert "new Date(startTime)" in APP
    assert "new Date(endTime)" in APP
    assert "`${start.day}T12:00:00Z`" not in APP
    assert "function cashflowAdjustedPortfolioChange(currency)" in APP


def test_profit_cards_use_cost_basis_and_do_not_invent_roi_from_recycled_capital():
    assert "function currentProfitMetrics(currency)" in APP
    assert "profit.unrealized/profit.invested*100" in APP
    assert "profit.total/profit.lifetimeCapital*100" not in APP
    assert "profit.realized/profit.lifetimeCapital*100" not in APP
    assert "cumulativePurchaseOutlay" in APP
    assert "cashflowAdjustedPortfolioChange(currency)" in APP
    assert 't("netStackChange")' in APP
    assert 't("endingBalance")' in APP


def test_tor_shutdown_gets_bounded_grace_period_without_false_warning():
    assert 'signal_pid_checked "${tor_pid}" TERM "Tor"' in RUN
    assert 'signal_pid_checked "${tor_pid}" KILL "Tor"' in RUN
    assert '/run/bitcoin-stack-tor/tor.pid' in RUN
    assert "Tor still visible after immediate bounded shutdown" not in RUN
    assert "finally reaped by s6" not in RUN
    assert 'bashio::log.info "Bundled Tor stopped"' in RUN
