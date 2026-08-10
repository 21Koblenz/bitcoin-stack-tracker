from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
HISTORY = (COMP / "history.py").read_text(encoding="utf-8")
LIMITS = (COMP / "limits.py").read_text(encoding="utf-8")
APP = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")


def test_history_backfill_is_ordered_and_gap_filling():
    own = HISTORY.index("# 1) Own infrastructure first")
    configured = HISTORY.index("# 2) Then other explicitly configured")
    local_usd = HISTORY.index("# 3) Reuse an already cached BTC/USD")
    public = HISTORY.index("# 4) Deep public cascade")
    assert own < configured < local_usd < public
    assert 'for provider in ("Blockchain.com", "Coin Metrics", "CoinGecko")' in HISTORY
    assert 'full_range_end = yesterday' in HISTORY
    assert 'contributed = _fill_missing_days(values, candidate)' in HISTORY
    assert 'role="gap-fill + deep-backfill"' in HISTORY
    assert 'if _is_full_market_history(values):\n                    break' in HISTORY


def test_public_range_fetchers_have_explicit_end_boundaries():
    assert 'end_day: str | None = None' in HISTORY
    assert 'params["end_time"] = end_day' in HISTORY
    assert 'params["endPeriod"] = end_day' in HISTORY
    assert 'effective_end = date.fromisoformat(end_day)' in HISTORY


def test_cached_usd_can_backfill_eur_before_new_market_request():
    assert 'for day, price in dict(initial_prices.get("USD", {})).items()' in HISTORY
    assert '"local BTC/USD cache + ECB"' in HISTORY
    assert 'route="local cache + Tor FX"' in HISTORY


def test_history_manual_rate_limit_is_short_not_one_hour():
    assert '"sync_history": (6, 300)' in LIMITS
    assert '"sync_history": (2, 3600)' not in LIMITS


def test_history_ui_exposes_actual_source_ranges():
    assert 'sourceCascade:"Quellenkette"' in APP
    assert 'sourceCascade:"Source cascade"' in APP
    assert 'item.history_source_chain' in APP
    assert 'part.first_day' in APP and 'part.last_day' in APP


def test_full_history_rejects_sparse_all_time_sampling():
    assert 'FULL_HISTORY_MIN_DENSITY = 0.95' in HISTORY
    assert 'FULL_HISTORY_MAX_GAP_DAYS = 7' in HISTORY
    assert 'len(days) / span_days < FULL_HISTORY_MIN_DENSITY' in HISTORY
    assert '(current - previous).days <= FULL_HISTORY_MAX_GAP_DAYS' in HISTORY
    assert 'ordered-source-cascade-v9-dense-gap-fill' in HISTORY
