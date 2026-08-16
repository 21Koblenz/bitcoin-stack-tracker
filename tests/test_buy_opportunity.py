from __future__ import annotations

from datetime import date, timedelta
import importlib.util
import math
from pathlib import Path

MODULE = Path(__file__).parents[1] / "custom_components" / "bitcoin_stack_tracker" / "buy_opportunity.py"
spec = importlib.util.spec_from_file_location("bst_buy_opportunity", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def synthetic_history(days: int = 1800) -> tuple[dict[str, float], date]:
    start = date(2021, 9, 7)
    values: dict[str, float] = {}
    for index in range(days):
        trend = 20_000 * math.exp(math.log(5.0) * index / (days - 1))
        cycle = 1 + 0.22 * math.sin(index / 95) + 0.07 * math.sin(index / 27)
        values[(start + timedelta(days=index)).isoformat()] = round(trend * cycle, 2)
    return values, start + timedelta(days=days)


def test_score_is_monotonic_when_only_hypothetical_current_price_falls():
    history, as_of = synthetic_history()
    prices = [160_000, 140_000, 120_000, 100_000, 90_000, 80_000, 70_000, 60_000, 50_000, 40_000]
    scores = [
        mod.calculate_buy_opportunity(history, price, as_of_day=as_of)["score"]
        for price in prices
    ]
    assert all(score is not None for score in scores)
    assert scores == sorted(scores)
    assert scores[0] <= 15
    assert scores[-1] >= 90


def test_full_history_populates_all_component_families_and_diagnostics():
    history, as_of = synthetic_history()
    result = mod.calculate_buy_opportunity(history, 70_000, as_of_day=as_of)
    assert result["score"] is not None
    assert result["data_quality"]["available_components"] == 6
    assert result["data_quality"]["weight_coverage_pct"] == 100.0
    assert not result["data_quality"]["missing_components"]
    for key in ("long_term", "drawdown", "range", "deviation", "momentum", "cycle"):
        assert result["component_scores"][key] is not None
    for key in (
        "sma50", "sma200", "sma730", "sma1400", "mayer_multiple",
        "ath_drawdown_pct", "percentile_365d", "zscore_200d",
        "bollinger_percent_b_20d", "rsi_14", "return_30d_pct",
        "power_law_fair_value", "pi_cycle_ratio", "two_year_upper_ratio",
    ):
        assert result["indicators"][key] is not None


def test_profiles_change_weighting_but_keep_score_in_bounds():
    history, as_of = synthetic_history()
    results = {}
    for profile in ("balanced", "long_term", "dip", "cycle"):
        settings = mod.normalize_buy_opportunity_settings({"profile": profile}, ["EUR"])
        result = mod.calculate_buy_opportunity(history, 70_000, settings=settings, as_of_day=as_of)
        results[profile] = result["score"]
        assert 0 <= result["score"] <= 100
        assert result["profile"] == profile
    assert len(set(results.values())) >= 2


def test_custom_weights_are_normalized_over_available_components():
    history, as_of = synthetic_history()
    settings = {
        "profile": "custom",
        "currency": "EUR",
        "weights": {"long_term": 100, "drawdown": 0, "range": 0, "deviation": 0, "momentum": 0, "cycle": 0},
    }
    result = mod.calculate_buy_opportunity(history, 70_000, settings=settings, as_of_day=as_of)
    assert result["effective_weights"]["long_term"] == 100.0
    assert result["score"] == round(result["component_scores"]["long_term"])


def test_invalid_threshold_order_falls_back_to_safe_defaults_in_pure_normalizer():
    settings = mod.normalize_buy_opportunity_settings({
        "thresholds": {"interesting": 80, "cheap": 60, "very_cheap": 50, "extreme": 40}
    }, ["EUR"])
    assert settings["thresholds"] == mod.DEFAULT_THRESHOLDS


def test_displayed_integer_score_and_rating_use_same_threshold():
    history, as_of = synthetic_history()
    result = mod.calculate_buy_opportunity(history, 60_000, as_of_day=as_of)
    assert result["score"] >= result["thresholds"]["very_cheap"]
    assert result["rating"] in {"very_cheap", "extreme"}


def test_insufficient_history_is_unavailable_not_misleading():
    start = date(2026, 1, 1)
    history = {(start + timedelta(days=i)).isoformat(): 50_000 + i * 100 for i in range(10)}
    result = mod.calculate_buy_opportunity(history, 52_000, as_of_day=start + timedelta(days=10))
    assert result["score"] is None
    assert result["rating"] == "unavailable"
    assert result["reason"] == "insufficient_history"


def test_no_private_portfolio_inputs_or_personal_cost_basis_in_result():
    history, as_of = synthetic_history()
    result = mod.calculate_buy_opportunity(history, 70_000, as_of_day=as_of)
    serialized = repr(result).lower()
    for forbidden in ("average_buy_price", "cost_basis", "ledger", "portfolio_value", "invested"):
        assert forbidden not in serialized


def adaptive_regime_history(amplitude: float, days: int = 1800) -> tuple[dict[str, float], date]:
    start = date(2021, 1, 1)
    values: dict[str, float] = {}
    for index in range(days):
        trend = 20_000 * math.exp(math.log(4.0) * index / (days - 1))
        cycle = math.exp(
            amplitude * math.sin(index * 0.55)
            + amplitude * 0.45 * math.sin(index * 1.7)
        )
        values[(start + timedelta(days=index)).isoformat()] = trend * cycle
    return values, start + timedelta(days=days)


def test_same_percentage_drop_scores_higher_in_lower_volatility_regime():
    high_vol_history, high_as_of = adaptive_regime_history(0.25)
    low_vol_history, low_as_of = adaptive_regime_history(0.05)
    high_last = list(high_vol_history.values())[-1]
    low_last = list(low_vol_history.values())[-1]

    high = mod.calculate_buy_opportunity(
        high_vol_history, high_last * 0.90, as_of_day=high_as_of
    )
    low = mod.calculate_buy_opportunity(
        low_vol_history, low_last * 0.90, as_of_day=low_as_of
    )

    assert high["score"] < low["score"]
    assert high["indicators"]["volatility_365d_annualized_pct"] > low["indicators"]["volatility_365d_annualized_pct"]
    assert high["scoring_mode"] == "automatic_volatility_regime"
    assert low["scoring_mode"] == "automatic_volatility_regime"


def test_future_history_never_changes_historical_score():
    history, as_of = synthetic_history()
    cutoff = as_of - timedelta(days=300)
    prior = {day: price for day, price in history.items() if day <= cutoff.isoformat()}
    current = prior[cutoff.isoformat()]

    baseline = mod.calculate_buy_opportunity(prior, current, as_of_day=cutoff)
    with_future = mod.calculate_buy_opportunity(history, current, as_of_day=cutoff)

    assert baseline["score"] == with_future["score"]
    assert baseline["component_scores"] == with_future["component_scores"]
    assert with_future["data_quality"]["look_ahead"] is False


def test_adaptive_model_exposes_regime_diagnostics():
    history, as_of = synthetic_history()
    result = mod.calculate_buy_opportunity(history, 70_000, as_of_day=as_of)
    indicators = result["indicators"]
    assert result["score_version"] == "price-history-adaptive-v4-turning-points"
    assert indicators["adaptive_window_days"] == 1460
    assert indicators["volatility_365d_annualized_pct"] is not None
    assert indicators["volatility_reference_pct"] is not None
    assert indicators["volatility_regime_ratio"] is not None
    assert indicators["volatility_regime"] in {"low", "normal", "high"}


def test_modular_defaults_preserve_adaptive_v2_backtested_vector():
    history, as_of = synthetic_history()
    prices = [160_000, 140_000, 120_000, 100_000, 90_000, 80_000, 70_000, 60_000, 50_000, 40_000]
    scores = [mod.calculate_buy_opportunity(history, price, as_of_day=as_of)["score"] for price in prices]
    assert scores == [9, 9, 10, 25, 55, 72, 89, 96, 96, 96]
    settings = mod.normalize_buy_opportunity_settings({}, ["EUR"])
    assert settings["model"] == mod.DEFAULT_MODEL_SETTINGS
    assert settings["signal_weights"] == mod.DEFAULT_SIGNAL_WEIGHTS
    assert settings["turning_point_weights"] == mod.DEFAULT_TURNING_POINT_WEIGHTS


def test_all_model_windows_and_signal_weights_are_overridable_and_exposed():
    history, as_of = synthetic_history()
    settings = mod.normalize_buy_opportunity_settings({
        "profile": "custom",
        "model": {
            "adaptive_window_days": 900,
            "adaptive_min_reference_points": 120,
            "volatility_window_days": 180,
            "volatility_floor_pct": 7.5,
            "trend_base_days": 180,
            "rsi_period_days": 10,
            "momentum_short_days": 21,
            "momentum_long_days": 60,
        },
        "signal_weights": {
            "cycle": {"trend_cycle": 0, "pi_cycle": 0, "two_year_upper": 0, "power_law": 1},
        },
    }, ["EUR"])
    result = mod.calculate_buy_opportunity(history, 70_000, settings=settings, as_of_day=as_of)
    assert result["score"] is not None
    assert result["model_settings"]["adaptive_window_days"] == 900
    assert result["model_settings"]["volatility_window_days"] == 180
    assert result["model_settings"]["trend_base_days"] == 180
    assert result["signal_weights"]["cycle"]["power_law"] == 1
    assert result["signal_weights"]["cycle"]["trend_cycle"] == 0
    assert result["indicators"]["configured_periods"]["trend_base_days"] == 180


def test_model_safety_constraints_are_normalized():
    settings = mod.normalize_buy_opportunity_settings({
        "model": {
            "adaptive_window_days": 400,
            "adaptive_min_reference_points": 1000,
            "volatility_window_days": 60,
            "volatility_min_points": 500,
            "volatility_regime_low_ratio": 2.0,
            "volatility_regime_high_ratio": 1.0,
        }
    }, ["EUR"])
    assert settings["model"]["adaptive_min_reference_points"] == 400
    assert settings["model"]["volatility_min_points"] == 60
    assert settings["model"]["volatility_regime_low_ratio"] == 0.75
    assert settings["model"]["volatility_regime_high_ratio"] == 1.25


def test_historical_score_series_matches_point_in_time_calculation():
    history, as_of = synthetic_history(1800)
    normalized = mod.normalize_buy_opportunity_settings(None, ["EUR"])
    dated = mod._parse_history(history)
    scores = mod._main_score_series(dated, normalized)
    for index in (700, 1200, len(dated) - 1):
        day, price = dated[index]
        exact = mod.calculate_buy_opportunity(history, price, currency="EUR", settings=normalized, as_of_day=day)
        assert scores[index] is not None
        assert round(scores[index], 2) == exact["score_raw"]


def test_historical_market_assessment_is_causal_and_bounded():
    history, as_of = synthetic_history(1800)
    result = mod.calculate_buy_opportunity_history(
        history, history[max(history)], currency="EUR", as_of_day=as_of, max_points=120
    )
    assert 1 <= len(result["points"]) <= 120
    assert all(0 <= point["score"] <= 100 for point in result["points"])
    cutoff = result["points"][len(result["points"]) // 2]["date"]
    prefix = {day: price for day, price in history.items() if day <= cutoff}
    with_future = dict(history)
    for day in list(with_future):
        if day > cutoff:
            with_future[day] *= 100
    a = mod.calculate_buy_opportunity_history(prefix, prefix[cutoff], currency="EUR", as_of_day=cutoff, max_points=60)
    b = mod.calculate_buy_opportunity_history(with_future, with_future[cutoff], currency="EUR", as_of_day=cutoff, max_points=60)
    assert a["points"] == b["points"]


def test_historical_best_point_is_true_unsampled_causal_maximum_and_is_kept():
    history, as_of = synthetic_history(1800)
    result = mod.calculate_buy_opportunity_history(
        history, history[max(history)], currency="EUR", as_of_day=as_of, max_points=30
    )
    normalized = mod.normalize_buy_opportunity_settings(None, ["EUR"])
    dated = [(day, price) for day, price in mod._parse_history(history) if day <= as_of]
    scores = mod._main_score_series(dated, normalized)
    eligible = [i for i, score in enumerate(scores) if score is not None]
    expected_index = max(eligible, key=lambda i: float(scores[i]))
    best = result["best_point"]
    assert best is not None
    assert best["date"] == dated[expected_index][0].isoformat()
    assert best["score"] == round(float(scores[expected_index]), 2)
    assert any(point["date"] == best["date"] for point in result["points"])
    assert len(result["points"]) <= 30
    assert "bottom_confirmation_met" in best
    assert "market_phase" in best


def test_historical_four_year_marker_windows_keep_each_true_bucket_maximum():
    history, as_of = synthetic_history(4200)
    start_day = as_of - timedelta(days=3650)
    result = mod.calculate_buy_opportunity_history(
        history, history[max(history)], currency="EUR", as_of_day=as_of, start_day=start_day,
        max_points=60, marker_interval_years=4,
    )
    markers = result["marker_points"]
    assert result["marker_interval_years"] == 4
    assert len(markers) == 3
    assert [row["date"] for row in markers] == sorted(row["date"] for row in markers)
    assert all(any(point["date"] == marker["date"] for point in result["points"]) for marker in markers)
    assert len(result["points"]) <= 60
    assert all("bottom_confirmation_met" in marker for marker in markers)



def test_best_marker_can_be_confirmed_causally_after_the_best_score_day(monkeypatch):
    start = date(2024, 1, 1)
    history = {(start + timedelta(days=i)).isoformat(): 50_000.0 + i for i in range(80)}
    as_of = start + timedelta(days=79)
    marker_offset = 20

    def fake_scores(dated, settings):
        scores = [20.0] * len(dated)
        scores[marker_offset] = 98.0
        return scores

    def fake_detail(history_arg, price, *, currency="EUR", settings=None, as_of_day=None):
        day = as_of_day if isinstance(as_of_day, date) else date.fromisoformat(str(as_of_day)[:10])
        lag = (day - (start + timedelta(days=marker_offset))).days
        confirmation = 65.0 if lag >= 3 else 15.0
        return {
            "turning_points": {
                "market_phase": "stress",
                "bottom_zone_memory": 82.0,
                "bottom_confirmation": confirmation,
                "thresholds": {"zone": 70.0, "confirmation": 40.0},
            }
        }

    monkeypatch.setattr(mod, "_main_score_series", fake_scores)
    monkeypatch.setattr(mod, "calculate_buy_opportunity", fake_detail)
    result = mod.calculate_buy_opportunity_history(
        history,
        history[as_of.isoformat()],
        currency="EUR",
        as_of_day=as_of,
        max_points=80,
    )
    marker = result["best_point"]
    assert marker["date"] == (start + timedelta(days=marker_offset)).isoformat()
    assert marker["bottom_confirmation"] == 15.0
    assert marker["bottom_confirmation_met"] is True
    assert marker["bottom_confirmation_date"] == (start + timedelta(days=marker_offset + 3)).isoformat()
    assert marker["bottom_confirmation_lag_days"] == 3
    assert marker["bottom_confirmation_confirmed_zone"] == 82.0
    assert marker["bottom_confirmation_confirmed_score"] == 65.0


def test_each_four_year_best_marker_gets_its_own_causal_bottom_confirmation(monkeypatch):
    start = date(2014, 1, 1)
    days = 365 * 10 + 8
    history = {(start + timedelta(days=i)).isoformat(): 10_000.0 + i for i in range(days)}
    as_of = start + timedelta(days=days - 1)
    peak_offsets = [120, 365 * 4 + 140, 365 * 8 + 160]

    def fake_scores(dated, settings):
        scores = [10.0] * len(dated)
        for rank, offset in enumerate(peak_offsets):
            scores[offset] = 97.0 + rank
        return scores

    confirmation_days = {start + timedelta(days=offset + 4) for offset in peak_offsets}

    def fake_detail(history_arg, price, *, currency="EUR", settings=None, as_of_day=None):
        day = as_of_day if isinstance(as_of_day, date) else date.fromisoformat(str(as_of_day)[:10])
        return {
            "turning_points": {
                "market_phase": "stress",
                "bottom_zone_memory": 85.0,
                "bottom_confirmation": 70.0 if day in confirmation_days else 10.0,
                "thresholds": {"zone": 70.0, "confirmation": 40.0},
            }
        }

    monkeypatch.setattr(mod, "_main_score_series", fake_scores)
    monkeypatch.setattr(mod, "calculate_buy_opportunity", fake_detail)
    result = mod.calculate_buy_opportunity_history(
        history,
        history[as_of.isoformat()],
        currency="EUR",
        as_of_day=as_of,
        start_day=start,
        max_points=80,
        marker_interval_years=4,
    )
    markers = result["marker_points"]
    assert len(markers) == 3
    assert [m["date"] for m in markers] == [(start + timedelta(days=o)).isoformat() for o in peak_offsets]
    assert all(m["bottom_confirmation_met"] for m in markers)
    assert [m["bottom_confirmation_lag_days"] for m in markers] == [4, 4, 4]
    assert [m["bottom_confirmation_date"] for m in markers] == [
        (start + timedelta(days=o + 4)).isoformat() for o in peak_offsets
    ]
