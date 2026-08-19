from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "bitcoin_stack_tracker"
RUNTIME = (COMPONENT / "market_assessment_runtime.py").read_text(encoding="utf-8")
BACKFILL = (COMPONENT / "market_assessment_backfill.py").read_text(encoding="utf-8")
INTRADAY = (COMPONENT / "market_assessment_intraday_cache.py").read_text(encoding="utf-8")


def test_market_reads_do_not_spawn_backfill():
    assert "async_market_assessment_backfill_loop" not in RUNTIME
    assert "throttled market assessment backfill" not in RUNTIME
    assert "_ensure_backfill" not in RUNTIME


def test_backfill_worker_is_background_only():
    assert "async_create_background_task" in BACKFILL
    assert "waiting_for_home_assistant" in BACKFILL
    assert "waiting_for_tor_gateway" in BACKFILL
    assert "BACKFILL_INITIAL_DELAY_SECONDS = 120" in BACKFILL


def test_market_assessment_uses_15_minute_cached_first_reconstruction():
    assert "MARKET_ASSESSMENT_CACHE_SECONDS = 15 * 60" in RUNTIME
    assert "_BUCKET_MINUTES = 15" in INTRADAY
    assert '"bucket_minutes": _BUCKET_MINUTES' in INTRADAY
    assert "BACKFILL_INTERVAL_MINUTES = 15" in BACKFILL
    assert "_cached_market_candles" in BACKFILL
    assert "local chart cache" in BACKFILL
    provider_start = BACKFILL.index("async def _download_90d_with_fallback")
    coinbase = BACKFILL.index("_download_coinbase_90d(", provider_start)
    bitstamp = BACKFILL.index("_download_bitstamp_90d(", provider_start)
    assert coinbase < bitstamp
    assert "Coinbase Exchange 15m candles via Tor" in BACKFILL
    assert "Bitstamp 15m OHLC via Tor" in BACKFILL
