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


def test_sparse_1221_point_all_time_series_is_not_complete():
    import ast
    from datetime import date, datetime, timedelta, timezone

    tree = ast.parse(HISTORY)
    selected = []
    wanted_constants = {
        "LONG_HISTORY_REQUIRED_BEFORE_DAY",
        "FULL_HISTORY_MIN_DENSITY",
        "FULL_HISTORY_MAX_GAP_DAYS",
        "FULL_HISTORY_MAX_RECENT_LAG_DAYS",
    }
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if isinstance(target, ast.Name) and target.id in wanted_constants:
                selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == "_is_full_market_history":
            selected.append(node)
    ns = {"date": date, "datetime": datetime, "timedelta": timedelta, "timezone": timezone}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(COMP / "history.py"), "exec"), ns)
    is_full = ns["_is_full_market_history"]

    today = datetime.now(timezone.utc).date()
    start = date(2010, 7, 18)
    span = max((today - start).days, 1)
    # Mimic a provider-sampled all-time response: only 1,221 points spread over
    # the whole range, including recent data and the early Bitcoin price era.
    sparse = {}
    for index in range(1221):
        offset = round(index * span / 1220)
        sparse[(start + timedelta(days=offset)).isoformat()] = 1.0 + index
    assert len(sparse) == 1221
    assert is_full(sparse) is False


def test_dense_daily_all_time_series_is_complete():
    import ast
    from datetime import date, datetime, timedelta, timezone

    tree = ast.parse(HISTORY)
    selected = []
    wanted_constants = {
        "LONG_HISTORY_REQUIRED_BEFORE_DAY",
        "FULL_HISTORY_MIN_DENSITY",
        "FULL_HISTORY_MAX_GAP_DAYS",
        "FULL_HISTORY_MAX_RECENT_LAG_DAYS",
    }
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if isinstance(target, ast.Name) and target.id in wanted_constants:
                selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == "_is_full_market_history":
            selected.append(node)
    ns = {"date": date, "datetime": datetime, "timedelta": timedelta, "timezone": timezone}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(COMP / "history.py"), "exec"), ns)
    is_full = ns["_is_full_market_history"]

    today = datetime.now(timezone.utc).date()
    cursor = date(2010, 7, 18)
    dense = {}
    while cursor < today:
        dense[cursor.isoformat()] = 1.0
        cursor += timedelta(days=1)
    assert is_full(dense) is True
