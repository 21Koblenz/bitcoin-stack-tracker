from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components/bitcoin_stack_tracker"
HISTORY = (COMP / "history.py").read_text(encoding="utf-8")
STORAGE = (COMP / "storage.py").read_text(encoding="utf-8")
INIT = (COMP / "__init__.py").read_text(encoding="utf-8")
APP = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")
STYLE = (COMP / "frontend/static/style.css").read_text(encoding="utf-8")


def test_own_mempool_history_is_preferred_but_not_exclusive():
    assert "mempool_source_is_exclusive" not in HISTORY
    assert "own mempool instance preferred on overlap" in HISTORY
    assert "values.update(own_values)" in HISTORY
    assert '"exclusive_source": False' in HISTORY
    assert "HISTORY_STRATEGY_VERSION" in HISTORY


def test_public_long_history_fallbacks_are_tor_routed_and_visible():
    assert "community-api.coinmetrics.io/v4/timeseries/asset-metrics" in HISTORY
    assert "https://api.blockchain.info/charts/market-price" in HISTORY
    assert "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart" in HISTORY
    assert "tor_proxy_from_settings(settings)" in HISTORY
    assert "Coin Metrics Community" in INIT
    assert "community-api.coinmetrics.io" in INIT


def test_recent_prices_are_seeded_and_adaptively_compacted():
    assert "KRAKEN_OHLC_INTERVALS = (5, 15, 30, 60, 240, 1440)" in HISTORY
    assert "BITSTAMP_OHLC_STEPS = {120: 7200, 720: 43200}" in HISTORY
    assert "MARKET_OHLC_TIERS = (5, 15, 30, 60, 120, 240, 720, 1440)" in HISTORY
    assert '"interval": int(interval)' in HISTORY
    assert '"step": step' in HISTORY
    assert '"limit": BITSTAMP_OHLC_LIMIT' in HISTORY
    assert "BITSTAMP_OHLC_LIMIT = 1000" in HISTORY
    assert "KRAKEN_OHLC_LIMIT = 720" in HISTORY
    assert "_market_ohlc_interval_for_days" in HISTORY
    assert "async_merge_market_candles" in HISTORY
    assert "market_candles_for_days" in STORAGE
    assert "market_candles" in STORAGE
    for duration, minutes in (("hours=60", 5), ("hours=180", 15), ("days=15", 30), ("days=30", 60), ("days=60", 120), ("days=120", 240), ("days=500", 720), ("days=720", 1440)):
        assert f"timedelta({duration})" in STORAGE
        assert f"minutes = {minutes}" in STORAGE
    assert "if days <= 0 or days > 731" in STORAGE
    assert "Return already-adaptive samples without flattening all tiers to one grid" in STORAGE
    assert "requested time window to one uniform interval" in STORAGE


def test_frontend_accepts_intraday_iso_timestamps():
    assert "history.market_candles?.[currency]" in APP
    assert "function chartTimestamp(value)" in APP
    assert "rawPrice[nowIso] = livePrice" in APP
    assert "resampleSeriesUniform(rawPrice,effectiveInterval)" in APP
    assert "Date.parse(`${day}T00:00:00Z`)" not in APP.split("function renderChart()", 1)[1].split("function renderLedger()", 1)[0]


def test_reached_goal_ring_is_bitcoin_orange():
    assert ".goal-card.is-reached .goal-ring" in STYLE
    assert ".goal-ring-progress{stroke:var(--orange);stroke-linecap:round;" in STYLE
    assert ".goal-ring-progress{stroke:var(--orange)" in STYLE


def test_prior_overview_privacy_requests_are_carried_forward():
    assert 'fiatSecured:"Kaufkraft in Sicherheit gebracht"' in APP
    assert "function lifetimeFiatSecured(currency)" in APP
    assert 'if (state.discreet) {' in APP
    assert '#milestonesPanel' in APP
    assert '#goalsStructurePanel' in APP
