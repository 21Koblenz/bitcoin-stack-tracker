from __future__ import annotations

from datetime import date, timedelta
import importlib.util
import math
from pathlib import Path

MODULE = Path(__file__).parents[1] / "custom_components" / "bitcoin_stack_tracker" / "buy_opportunity.py"
spec = importlib.util.spec_from_file_location("bst_turning_points", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def cyclical_history(days: int = 2200) -> tuple[dict[str, float], date]:
    start = date(2020, 1, 1)
    history: dict[str, float] = {}
    for i in range(days):
        trend = 12_000 * math.exp(math.log(6.0) * i / (days - 1))
        cycle = math.exp(0.24 * math.sin(i / 105.0) + 0.07 * math.sin(i / 21.0))
        history[(start + timedelta(days=i)).isoformat()] = trend * cycle
    return history, start + timedelta(days=days)


def test_four_turning_point_models_are_exposed_and_bounded():
    history, as_of = cyclical_history()
    result = mod.calculate_buy_opportunity(history, 50_000, as_of_day=as_of)
    turning = result["turning_points"]
    for key in ("bottom_zone", "bottom_confirmation", "top_zone", "top_confirmation"):
        assert turning[key] is not None
        assert 0 <= turning[key] <= 100
    assert turning["market_phase"] in {
        "bottoming_possible", "capitulation", "top_formation_possible", "overheating",
        "recovery", "cooling", "depressed", "expansion", "neutral",
    }
    assert "bottom/top declaration" in turning["notice"]


def test_extreme_drop_prefers_bottom_zone_and_extreme_rally_prefers_top_zone():
    history, as_of = cyclical_history()
    last = list(history.values())[-1]
    low = mod.calculate_buy_opportunity(history, last * 0.45, as_of_day=as_of)["turning_points"]
    high = mod.calculate_buy_opportunity(history, last * 2.0, as_of_day=as_of)["turning_points"]
    assert low["bottom_zone"] > low["top_zone"]
    assert high["top_zone"] > high["bottom_zone"]


def test_turning_point_settings_are_fully_modular_and_zero_can_disable_signal():
    settings = mod.normalize_buy_opportunity_settings({
        "turning_point_weights": {
            "bottom_zone": {"valuation": 0, "drawdown": 100},
            "top_confirmation": {"price_rejection": 100, "rsi_divergence": 0},
        },
        "model": {
            "turning_point_lookback_days": 120,
            "turning_point_separation_days": 10,
            "turning_zone_memory_days": 30,
            "divergence_price_tolerance_pct": 6.5,
            "volatility_fast_window_days": 21,
            "volatility_slow_window_days": 75,
            "turning_confirmation_threshold": 35,
        },
    }, ["EUR"])
    assert settings["turning_point_weights"]["bottom_zone"]["valuation"] == 0
    assert settings["turning_point_weights"]["bottom_zone"]["drawdown"] == 100
    assert settings["turning_point_weights"]["top_confirmation"]["price_rejection"] == 100
    assert settings["model"]["turning_zone_memory_days"] == 30
    assert settings["model"]["turning_confirmation_threshold"] == 35


def test_future_prices_do_not_change_historical_turning_point_results():
    history, _ = cyclical_history()
    dates = sorted(history)
    cutoff = dates[-240]
    current = history[cutoff]
    prior = {day: value for day, value in history.items() if day <= cutoff}
    baseline = mod.calculate_buy_opportunity(prior, current, as_of_day=cutoff)
    with_future = mod.calculate_buy_opportunity(history, current, as_of_day=cutoff)
    assert baseline["turning_points"] == with_future["turning_points"]
    assert with_future["data_quality"]["look_ahead"] is False


def test_turning_point_layer_adds_no_network_dependency():
    source = MODULE.read_text(encoding="utf-8")
    for forbidden in ("aiohttp", "requests", "urllib.request", "httpx", "socket"):
        assert forbidden not in source
    history, as_of = cyclical_history()
    result = mod.calculate_buy_opportunity(history, 50_000, as_of_day=as_of)
    assert result["network_policy"] == "price_history_only_no_new_outbound_connections"


def test_zone_memory_can_confirm_after_extreme_without_lookahead():
    history, as_of = cyclical_history()
    # Create a sharp local blow-off followed by a reversal. The confirmation day
    # only sees the earlier peak, never later prices.
    base = list(history.values())[-1]
    peak_day = as_of
    history[peak_day.isoformat()] = base * 1.8
    confirm_day = peak_day + timedelta(days=5)
    for offset in range(1, 5):
        history[(peak_day + timedelta(days=offset)).isoformat()] = base * (1.8 - 0.12 * offset)
    current = base * 1.25
    result = mod.calculate_buy_opportunity(history, current, as_of_day=confirm_day)
    turning = result["turning_points"]
    assert turning["top_zone_memory"] >= turning["top_zone"]
    assert turning["zone_memory_days"] == mod.DEFAULT_MODEL_SETTINGS["turning_zone_memory_days"]
