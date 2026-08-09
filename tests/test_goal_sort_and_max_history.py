from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
APP = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")
HISTORY = (COMP / "history.py").read_text(encoding="utf-8")


def test_stacking_goals_are_sorted_smallest_to_largest_for_cards_and_editor():
    assert "function sortedStackingGoals" in APP
    helper = APP.split("function sortedStackingGoals", 1)[1].split("function renderGoalCards", 1)[0]
    assert "amount(left) - amount(right)" in helper
    cards = APP.split("function renderGoalCards()", 1)[1].split("function firstPortfolioActivityDay", 1)[0]
    assert "const goals = sortedStackingGoals();" in cards
    editor = APP.split("function renderGoalsEditor()", 1)[1].split("function renderTax()", 1)[0]
    assert "sortedStackingGoals().map" in editor


def test_full_history_requests_explicit_2010_start_and_does_not_accept_2013_as_complete():
    assert 'HISTORY_STRATEGY_VERSION = "ordered-source-cascade-v8-fx-fill"' in HISTORY
    assert 'ALL_TIME_PRICE_START_DAY = "2010-07-01"' in HISTORY
    assert 'LONG_HISTORY_REQUIRED_BEFORE_DAY = "2010-09-01"' in HISTORY
    assert '"start_time": start_day or ALL_TIME_PRICE_START_DAY' in HISTORY
    assert 'effective_start = start_day or ALL_TIME_PRICE_START_DAY' in HISTORY
    assert 'or not _is_full_market_history(dict(initial_prices.get(code, {})))' in HISTORY
    assert 'for provider in ("Blockchain.com", "Coin Metrics", "CoinGecko")' in HISTORY
    assert '_merge_older_prefix(values, candidate)' in HISTORY


def test_max_keeps_the_oldest_real_daily_boundary_point():
    block = APP.split("function resampleLongRangeUniform(values)", 1)[1].split("function sortedNumericPoints", 1)[0]
    assert 'state.historyRange === "max"' in block
    assert 'result[source[0].day] = source[0].value' in block
