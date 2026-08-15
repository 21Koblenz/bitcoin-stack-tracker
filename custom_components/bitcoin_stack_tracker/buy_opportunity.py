"""Adaptive price-history-only Bitcoin buy-opportunity scoring.

The score is intentionally independent from the private portfolio ledger. It uses
only public BTC prices already cached by Bitcoin Stack Tracker plus the current
market price. A higher score means that Bitcoin is cheap relative to its own
recent volatility and market regime; it is not a probability, forecast, or
investment recommendation.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import deque
from datetime import date
import math
from statistics import fmean, pstdev
from typing import Any, Iterable, Mapping

SCORE_VERSION = "price-history-adaptive-v4-turning-points"
MIN_HISTORY_POINTS = 365
ADAPTIVE_WINDOW_DAYS = 1460
ADAPTIVE_MIN_REFERENCE_POINTS = 180
GENESIS_DATE = date(2009, 1, 3)

# Backtested defaults. Every material model parameter can be overridden through
# settings, while these values remain the safe reset point.
DEFAULT_MODEL_SETTINGS: dict[str, float | int] = {
    "minimum_history_points": 365,
    "adaptive_window_days": 1460,
    "adaptive_min_reference_points": 180,
    "volatility_window_days": 365,
    "volatility_min_points": 90,
    "volatility_floor_pct": 5.0,
    "drawdown_window_days": 365,
    "drawdown_min_points": 180,
    "regime_high_min_points": 365,
    "percentile_window_days": 365,
    "percentile_min_points": 180,
    "short_deviation_days": 20,
    "trend_short_days": 50,
    "pi_short_days": 111,
    "trend_base_days": 200,
    "pi_long_days": 350,
    "trend_mid_days": 365,
    "trend_long_days": 730,
    "trend_cycle_days": 1400,
    "rsi_period_days": 14,
    "momentum_short_days": 30,
    "momentum_long_days": 90,
    "two_year_multiplier": 5.0,
    "power_law_min_points": 365,
    "volatility_regime_low_ratio": 0.75,
    "volatility_regime_high_ratio": 1.25,
    "turning_point_lookback_days": 180,
    "turning_point_separation_days": 14,
    "turning_zone_memory_days": 45,
    "divergence_price_tolerance_pct": 8.0,
    "volatility_fast_window_days": 30,
    "volatility_slow_window_days": 90,
    "volatility_cooling_lookback_days": 45,
    "exhaustion_short_days": 7,
    "confirmation_zone_gate": 0.65,
    "turning_zone_threshold": 75.0,
    "turning_confirmation_threshold": 40.0,
    "turning_extreme_threshold": 85.0,
}

MODEL_SETTING_LIMITS: dict[str, tuple[float, float, bool]] = {
    "minimum_history_points": (90, 3650, True),
    "adaptive_window_days": (365, 3650, True),
    "adaptive_min_reference_points": (60, 1460, True),
    "volatility_window_days": (30, 1460, True),
    "volatility_min_points": (20, 730, True),
    "volatility_floor_pct": (1.0, 100.0, False),
    "drawdown_window_days": (30, 3650, True),
    "drawdown_min_points": (20, 1460, True),
    "regime_high_min_points": (60, 1460, True),
    "percentile_window_days": (30, 3650, True),
    "percentile_min_points": (20, 1460, True),
    "short_deviation_days": (5, 365, True),
    "trend_short_days": (10, 730, True),
    "pi_short_days": (20, 730, True),
    "trend_base_days": (30, 1460, True),
    "pi_long_days": (50, 1460, True),
    "trend_mid_days": (60, 1460, True),
    "trend_long_days": (120, 2500, True),
    "trend_cycle_days": (365, 3650, True),
    "rsi_period_days": (5, 60, True),
    "momentum_short_days": (7, 180, True),
    "momentum_long_days": (14, 365, True),
    "two_year_multiplier": (1.0, 10.0, False),
    "power_law_min_points": (180, 1460, True),
    "volatility_regime_low_ratio": (0.25, 1.0, False),
    "volatility_regime_high_ratio": (1.0, 4.0, False),
    "turning_point_lookback_days": (30, 730, True),
    "turning_point_separation_days": (3, 90, True),
    "turning_zone_memory_days": (5, 180, True),
    "divergence_price_tolerance_pct": (1.0, 30.0, False),
    "volatility_fast_window_days": (7, 180, True),
    "volatility_slow_window_days": (30, 365, True),
    "volatility_cooling_lookback_days": (10, 180, True),
    "exhaustion_short_days": (3, 30, True),
    "confirmation_zone_gate": (0.0, 1.0, False),
    "turning_zone_threshold": (50.0, 95.0, False),
    "turning_confirmation_threshold": (25.0, 95.0, False),
    "turning_extreme_threshold": (60.0, 99.0, False),
}

DEFAULT_SIGNAL_WEIGHTS: dict[str, dict[str, float]] = {
    # These reproduce adaptive-v2's effective internal weighting. Optional
    # signals such as power_law are exposed but default to zero.
    "long_term": {"trend_base": 2.0, "trend_long": 1.0, "trend_cycle": 0.0, "power_law": 0.0},
    "drawdown": {"drawdown_local": 2.0, "drawdown_regime": 1.0},
    "range": {"price_percentile": 1.0, "trend_mid": 1.0},
    "deviation": {"short_z": 1.0, "trend_short": 1.0},
    "momentum": {"momentum_short": 1.0, "momentum_long": 1.0, "rsi": 1.0},
    "cycle": {"trend_cycle": 1.0, "pi_cycle": 1.0, "two_year_upper": 1.0, "power_law": 0.0},
}

# Turning-point models are deliberately separate from the main valuation score.
# Zone = extreme valuation/market regime. Confirmation = evidence that the
# directional move is losing force. They are assessments, never trade signals.
DEFAULT_TURNING_POINT_WEIGHTS: dict[str, dict[str, float]] = {
    "bottom_zone": {
        "valuation": 25.0, "drawdown": 20.0, "duration": 10.0,
        "range": 15.0, "momentum_stress": 15.0, "volatility_stress": 15.0,
    },
    "bottom_confirmation": {
        "rsi_divergence": 25.0, "return_divergence": 15.0,
        "volatility_cooling": 5.0, "trend_reclaim": 15.0,
        "selling_exhaustion": 20.0, "price_rebound": 20.0,
    },
    "top_zone": {
        "valuation": 25.0, "trend_extension": 20.0, "range": 10.0,
        "momentum_heat": 15.0, "pi_cycle": 10.0,
        "acceleration": 15.0, "near_high": 5.0,
    },
    "top_confirmation": {
        "rsi_divergence": 20.0, "return_divergence": 10.0,
        "volatility_cooling": 5.0, "trend_loss": 15.0,
        "buying_exhaustion": 15.0, "price_rejection": 35.0,
    },
}

TURNING_POINT_MODEL_KEYS = tuple(DEFAULT_TURNING_POINT_WEIGHTS)

COMPONENT_KEYS = (
    "long_term",
    "drawdown",
    "range",
    "deviation",
    "momentum",
    "cycle",
)

DEFAULT_WEIGHTS: dict[str, float] = {
    "long_term": 25.0,
    "drawdown": 20.0,
    "range": 15.0,
    "deviation": 15.0,
    "momentum": 10.0,
    "cycle": 15.0,
}

PROFILE_WEIGHTS: dict[str, dict[str, float]] = {
    "balanced": dict(DEFAULT_WEIGHTS),
    "long_term": {
        "long_term": 35.0,
        "drawdown": 15.0,
        "range": 15.0,
        "deviation": 10.0,
        "momentum": 5.0,
        "cycle": 20.0,
    },
    "dip": {
        "long_term": 15.0,
        "drawdown": 30.0,
        "range": 15.0,
        "deviation": 20.0,
        "momentum": 15.0,
        "cycle": 5.0,
    },
    "cycle": {
        "long_term": 25.0,
        "drawdown": 10.0,
        "range": 10.0,
        "deviation": 10.0,
        "momentum": 5.0,
        "cycle": 40.0,
    },
}

DEFAULT_THRESHOLDS: dict[str, float] = {
    "very_expensive_max": 20.0,
    "expensive_max": 35.0,
    "interesting": 50.0,
    "cheap": 65.0,
    "very_cheap": 80.0,
    "extreme": 90.0,
}


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _positive(value: Any) -> float | None:
    result = _finite(value)
    return result if result is not None and result > 0 else None


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _piecewise(value: float | None, points: Iterable[tuple[float, float]]) -> float | None:
    """Linearly interpolate a bounded score through an ordered point curve."""
    if value is None or not math.isfinite(value):
        return None
    curve = sorted((float(x), float(y)) for x, y in points)
    if not curve:
        return None
    if value <= curve[0][0]:
        return _clamp(curve[0][1])
    if value >= curve[-1][0]:
        return _clamp(curve[-1][1])
    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if x0 <= value <= x1:
            if x1 == x0:
                return _clamp(y1)
            ratio = (value - x0) / (x1 - x0)
            return _clamp(y0 + (y1 - y0) * ratio)
    return None


def _mean(values: list[float], length: int) -> float | None:
    if len(values) < length:
        return None
    return fmean(values[-length:])


def _std(values: list[float], length: int) -> float | None:
    if len(values) < length:
        return None
    window = values[-length:]
    if len(window) < 2:
        return None
    result = pstdev(window)
    return result if result > 0 else 0.0


def _percent_change(current: float, previous: float | None) -> float | None:
    if previous is None or previous <= 0:
        return None
    return (current / previous - 1.0) * 100.0


def _ratio(current: float, base: float | None) -> float | None:
    if base is None or base <= 0:
        return None
    return current / base


def _distance_pct(current: float, base: float | None) -> float | None:
    return _percent_change(current, base)


def _percentile_rank(current: float, values: list[float], length: int) -> float | None:
    if len(values) < min(length, MIN_HISTORY_POINTS):
        return None
    window = values[-length:] if len(values) >= length else values
    ordered = sorted(window)
    if not ordered:
        return None
    return 100.0 * bisect_right(ordered, current) / len(ordered)


def _rsi_wilder(values: list[float], period: int = 14) -> float | None:
    series = _rsi_series(values, period)
    return series[-1] if series else None


def _annualized_volatility(values: list[float], length: int = 30) -> float | None:
    if len(values) < length + 1:
        return None
    window = values[-(length + 1):]
    returns = [math.log(right / left) for left, right in zip(window, window[1:]) if left > 0 and right > 0]
    if len(returns) < 2:
        return None
    return pstdev(returns) * math.sqrt(365.0) * 100.0


def _rolling_mean_series(values: list[float], window: int, min_points: int | None = None) -> list[float | None]:
    minimum = window if min_points is None else max(1, int(min_points))
    prefix = [0.0]
    for value in values:
        prefix.append(prefix[-1] + value)
    out: list[float | None] = [None] * len(values)
    for index in range(len(values)):
        start = max(0, index - window + 1)
        count = index - start + 1
        if count >= minimum:
            out[index] = (prefix[index + 1] - prefix[start]) / count
    return out


def _rolling_std_series(values: list[float], window: int, min_points: int | None = None) -> list[float | None]:
    minimum = window if min_points is None else max(2, int(min_points))
    prefix = [0.0]
    prefix_sq = [0.0]
    for value in values:
        prefix.append(prefix[-1] + value)
        prefix_sq.append(prefix_sq[-1] + value * value)
    out: list[float | None] = [None] * len(values)
    for index in range(len(values)):
        start = max(0, index - window + 1)
        count = index - start + 1
        if count < minimum:
            continue
        total = prefix[index + 1] - prefix[start]
        total_sq = prefix_sq[index + 1] - prefix_sq[start]
        mean = total / count
        variance = max(0.0, total_sq / count - mean * mean)
        out[index] = math.sqrt(variance)
    return out


def _rolling_max_series(values: list[float], window: int, min_points: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    q: deque[int] = deque()
    for index, value in enumerate(values):
        while q and q[0] <= index - window:
            q.popleft()
        while q and values[q[-1]] <= value:
            q.pop()
        q.append(index)
        start = max(0, index - window + 1)
        if index - start + 1 >= min_points:
            out[index] = values[q[0]]
    return out


def _rolling_volatility_series(values: list[float], window: int = 365, min_points: int = 90) -> list[float | None]:
    if not values:
        return []
    log_returns: list[float] = [0.0]
    for left, right in zip(values, values[1:]):
        log_returns.append(math.log(right / left) if left > 0 and right > 0 else 0.0)
    prefix = [0.0]
    prefix_sq = [0.0]
    for value in log_returns:
        prefix.append(prefix[-1] + value)
        prefix_sq.append(prefix_sq[-1] + value * value)
    out: list[float | None] = [None] * len(values)
    for index in range(1, len(values)):
        start = max(1, index - window + 1)
        count = index - start + 1
        if count < min_points:
            continue
        total = prefix[index + 1] - prefix[start]
        total_sq = prefix_sq[index + 1] - prefix_sq[start]
        mean = total / count
        variance = max(0.0, total_sq / count - mean * mean)
        out[index] = math.sqrt(variance) * math.sqrt(365.0)
    return out


def _rsi_series(values: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    changes = [values[index] - values[index - 1] for index in range(1, len(values))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = fmean(gains[:period])
    avg_loss = fmean(losses[:period])

    def value(gain: float, loss: float) -> float:
        if loss == 0:
            return 100.0 if gain > 0 else 50.0
        rs = gain / loss
        return 100.0 - (100.0 / (1.0 + rs))

    out[period] = value(avg_gain, avg_loss)
    for change_index in range(period, len(changes)):
        gain = gains[change_index]
        loss = losses[change_index]
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        out[change_index + 1] = value(avg_gain, avg_loss)
    return out


def _cheapness_percentile(
    series: list[float | None],
    current_index: int,
    window: int = ADAPTIVE_WINDOW_DAYS,
    min_reference: int = ADAPTIVE_MIN_REFERENCE_POINTS,
) -> float | None:
    """Return 0..100 where unusually low values score as cheaper.

    Only values strictly before current_index are used, making the method causal and
    safe for historical backtests without look-ahead bias.
    """
    if current_index < 0 or current_index >= len(series):
        return None
    current = series[current_index]
    if current is None or not math.isfinite(current):
        return None
    start = max(0, current_index - window)
    history = [
        float(value)
        for value in series[start:current_index]
        if value is not None and math.isfinite(value)
    ]
    if len(history) < min_reference:
        return None
    return 100.0 * sum(value >= current for value in history) / len(history)


def _rolling_percentile_current(current: float, prior_values: list[float], window: int, min_points: int) -> float | None:
    history = prior_values[-window:] if len(prior_values) > window else prior_values
    history = [value for value in history if math.isfinite(value)]
    if len(history) < min_points:
        return None
    return 100.0 * sum(value <= current for value in history) / len(history)


def _average_available(values: Iterable[float | None]) -> float | None:
    usable = [float(value) for value in values if value is not None and math.isfinite(value)]
    if not usable:
        return None
    return fmean(usable)


def _weighted_average_available(values: Mapping[str, float | None], weights: Mapping[str, Any]) -> float | None:
    usable: list[tuple[float, float]] = []
    for key, value in values.items():
        weight = _finite(weights.get(key))
        if value is None or not math.isfinite(float(value)) or weight is None or weight <= 0:
            continue
        usable.append((float(value), float(weight)))
    total_weight = sum(weight for _, weight in usable)
    if total_weight <= 0:
        return None
    return sum(value * weight for value, weight in usable) / total_weight


def _safe_normalized_log_ratio(price: float, base: float | None, volatility: float | None, volatility_floor: float = 0.05) -> float | None:
    if base is None or base <= 0 or volatility is None or volatility <= 0:
        return None
    return math.log(price / base) / max(volatility, volatility_floor)


def _standardized_return(current: float, previous: float | None, volatility: float | None, days: int, volatility_floor: float = 0.05) -> float | None:
    if previous is None or previous <= 0 or volatility is None or volatility <= 0 or days <= 0:
        return None
    expected_sigma = max(volatility, volatility_floor) * math.sqrt(days / 365.0)
    if expected_sigma <= 0:
        return None
    return math.log(current / previous) / expected_sigma



def _highness_percentile(
    series: list[float | None], current_index: int, window: int, min_reference: int
) -> float | None:
    cheap = _cheapness_percentile(series, current_index, window, min_reference)
    return None if cheap is None else 100.0 - cheap


def _days_since_rolling_high_series(values: list[float], window: int) -> list[float | None]:
    """Age of the highest price in a trailing window, in days/observations."""
    out: list[float | None] = [None] * len(values)
    q: deque[int] = deque()
    for index, value in enumerate(values):
        while q and q[0] < index - window + 1:
            q.popleft()
        while q and values[q[-1]] <= value:
            q.pop()
        q.append(index)
        if q:
            out[index] = float(index - q[0])
    return out


def _divergence_score(
    prices: list[float],
    indicator: list[float | None],
    index: int,
    *,
    lookback: int,
    separation: int,
    tolerance_pct: float,
    direction: str,
) -> float | None:
    """Causal price/indicator divergence against a prior swing extreme."""
    end = index - max(1, separation)
    start = max(0, index - max(lookback, separation + 1))
    if end <= start or indicator[index] is None:
        return None
    candidates = [i for i in range(start, end + 1) if indicator[i] is not None]
    if not candidates:
        return None
    if direction == "bottom":
        reference = min(candidates, key=lambda i: prices[i])
        tolerance = max(0.01, tolerance_pct / 100.0)
        ratio = prices[index] / prices[reference]
        if ratio > 1.0 + tolerance:
            return 0.0
        price_score = _piecewise(ratio, [(0.70, 100), (1.00, 100), (1.0 + tolerance, 0)]) or 0.0
        delta = float(indicator[index]) - float(indicator[reference])
        indicator_score = _piecewise(delta, [(-5, 0), (0, 10), (5, 55), (15, 100)]) or 0.0
    else:
        reference = max(candidates, key=lambda i: prices[i])
        tolerance = max(0.01, tolerance_pct / 100.0)
        ratio = prices[index] / prices[reference]
        if ratio < 1.0 - tolerance:
            return 0.0
        price_score = _piecewise(ratio, [(1.0 - tolerance, 0), (1.00, 100), (1.30, 100)]) or 0.0
        delta = float(indicator[reference]) - float(indicator[index])
        indicator_score = _piecewise(delta, [(-5, 0), (0, 10), (5, 55), (15, 100)]) or 0.0
    return _clamp((price_score * 0.4) + (indicator_score * 0.6))


def _trend_transition_score(
    prices: list[float],
    ma_fast: list[float | None],
    ma_slow: list[float | None],
    index: int,
    *,
    direction: str,
    lookback: int = 30,
) -> float | None:
    current_fast = ma_fast[index]
    current_slow = ma_slow[index]
    if current_fast is None:
        return None
    start = max(0, index - lookback)
    if direction == "bottom":
        was_other_side = any(ma_fast[i] is not None and prices[i] < float(ma_fast[i]) for i in range(start, index))
        if not was_other_side:
            return 0.0
        score = 50.0 if prices[index] >= current_fast else 0.0
        if current_slow is not None and prices[index] >= current_slow:
            score += 50.0
        return score
    was_other_side = any(ma_fast[i] is not None and prices[i] > float(ma_fast[i]) for i in range(start, index))
    if not was_other_side:
        return 0.0
    score = 50.0 if prices[index] <= current_fast else 0.0
    if current_slow is not None and prices[index] <= current_slow:
        score += 50.0
    return score


def _volatility_cooling_score(
    fast_vol: list[float | None], slow_vol: list[float | None], index: int, lookback: int
) -> float | None:
    current_fast = fast_vol[index]
    current_slow = slow_vol[index]
    if current_fast is None or current_slow is None or current_slow <= 0:
        return None
    start = max(0, index - lookback)
    prior = [float(v) for v in fast_vol[start:index] if v is not None and math.isfinite(float(v))]
    if not prior:
        return None
    peak = max(prior)
    if peak <= 0:
        return 0.0
    peak_ratio = peak / current_slow
    cooling = max(0.0, 1.0 - current_fast / peak)
    return _clamp((_piecewise(peak_ratio, [(0.8, 0), (1.2, 35), (1.6, 75), (2.2, 100)]) or 0.0) * min(1.0, cooling / 0.35))


def _market_phase(
    overall_score: float | None,
    bottom_zone: float | None,
    bottom_confirmation: float | None,
    top_zone: float | None,
    top_confirmation: float | None,
    model: Mapping[str, Any],
) -> str:
    zone = float(model["turning_zone_threshold"])
    confirm = float(model["turning_confirmation_threshold"])
    extreme = float(model["turning_extreme_threshold"])
    bz, bc = bottom_zone or 0.0, bottom_confirmation or 0.0
    tz, tc = top_zone or 0.0, top_confirmation or 0.0
    overall = overall_score if overall_score is not None else 50.0
    if bz >= zone and bc >= confirm:
        return "bottoming_possible"
    if bz >= extreme:
        return "capitulation"
    if tz >= zone and tc >= confirm:
        return "top_formation_possible"
    if tz >= extreme:
        return "overheating"
    if bc >= confirm and overall >= 50.0:
        return "recovery"
    if tc >= confirm and overall < 50.0:
        return "cooling"
    if bz >= zone or overall >= zone:
        return "depressed"
    if tz >= zone or overall <= 100.0 - zone:
        return "expansion"
    return "neutral"

def _power_law_fit(dated_values: list[tuple[date, float]], as_of: date, min_points: int = 365) -> dict[str, float | None]:
    """Fit ln(price)=intercept+slope*ln(days since genesis) with stdlib only."""
    xs: list[float] = []
    ys: list[float] = []
    for day, price in dated_values:
        elapsed = (day - GENESIS_DATE).days
        if elapsed <= 0 or price <= 0:
            continue
        xs.append(math.log(float(elapsed)))
        ys.append(math.log(price))
    if len(xs) < max(2, int(min_points)):
        return {"fair_value": None, "ratio": None, "residual_z": None, "slope": None, "intercept": None}
    mean_x = fmean(xs)
    mean_y = fmean(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator <= 0:
        return {"fair_value": None, "ratio": None, "residual_z": None, "slope": None, "intercept": None}
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
    intercept = mean_y - slope * mean_x
    as_of_elapsed = (as_of - GENESIS_DATE).days
    if as_of_elapsed <= 0:
        return {"fair_value": None, "ratio": None, "residual_z": None, "slope": slope, "intercept": intercept}
    fair = math.exp(intercept + slope * math.log(float(as_of_elapsed)))
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    residual_std = pstdev(residuals) if len(residuals) >= 2 else 0.0
    last_price = dated_values[-1][1] if dated_values else None
    ratio = last_price / fair if last_price and fair > 0 else None
    residual_z = math.log(ratio) / residual_std if ratio and ratio > 0 and residual_std > 0 else None
    return {"fair_value": fair, "ratio": ratio, "residual_z": residual_z, "slope": slope, "intercept": intercept}


def _parse_history(history: Mapping[str, Any]) -> list[tuple[date, float]]:
    parsed: list[tuple[date, float]] = []
    for raw_day, raw_price in history.items():
        price = _positive(raw_price)
        if price is None:
            continue
        try:
            day = date.fromisoformat(str(raw_day)[:10])
        except ValueError:
            continue
        parsed.append((day, price))
    parsed.sort(key=lambda item: item[0])
    deduped: dict[date, float] = {}
    for day, price in parsed:
        deduped[day] = price
    return sorted(deduped.items())


def normalize_buy_opportunity_settings(
    settings: Mapping[str, Any] | None,
    currencies: Iterable[str] | None = None,
) -> dict[str, Any]:
    raw = dict(settings or {})
    profile = str(raw.get("profile") or "balanced").lower()
    if profile not in {*PROFILE_WEIGHTS, "custom"}:
        profile = "balanced"

    allowed_currencies = [str(item).upper() for item in (currencies or []) if str(item).strip()]
    currency = str(raw.get("currency") or (allowed_currencies[0] if allowed_currencies else "EUR")).upper()
    if allowed_currencies and currency not in allowed_currencies:
        currency = allowed_currencies[0]

    base_weights = PROFILE_WEIGHTS.get(profile, DEFAULT_WEIGHTS)
    raw_weights = raw.get("weights") if isinstance(raw.get("weights"), Mapping) else {}
    weights: dict[str, float] = {}
    for key in COMPONENT_KEYS:
        candidate = _finite(raw_weights.get(key)) if isinstance(raw_weights, Mapping) else None
        if profile != "custom" and candidate is None:
            candidate = base_weights[key]
        if candidate is None:
            candidate = DEFAULT_WEIGHTS[key]
        weights[key] = _clamp(candidate, 0.0, 100.0)
    if sum(weights.values()) <= 0:
        weights = dict(DEFAULT_WEIGHTS)
        profile = "balanced"

    raw_thresholds = raw.get("thresholds") if isinstance(raw.get("thresholds"), Mapping) else {}
    thresholds: dict[str, float] = {}
    for key, default in DEFAULT_THRESHOLDS.items():
        candidate = _finite(raw_thresholds.get(key)) if isinstance(raw_thresholds, Mapping) else None
        thresholds[key] = _clamp(candidate if candidate is not None else default, 1.0, 99.0)
    ordered = [
        thresholds["very_expensive_max"], thresholds["expensive_max"],
        thresholds["interesting"], thresholds["cheap"],
        thresholds["very_cheap"], thresholds["extreme"],
    ]
    if not all(left < right for left, right in zip(ordered, ordered[1:])):
        thresholds = dict(DEFAULT_THRESHOLDS)

    raw_model = raw.get("model") if isinstance(raw.get("model"), Mapping) else {}
    model: dict[str, float | int] = {}
    for key, default in DEFAULT_MODEL_SETTINGS.items():
        low, high, integer = MODEL_SETTING_LIMITS[key]
        candidate = _finite(raw_model.get(key)) if isinstance(raw_model, Mapping) else None
        value = float(default if candidate is None else candidate)
        value = max(low, min(high, value))
        model[key] = int(round(value)) if integer else round(value, 6)
    # Keep paired constraints coherent rather than silently producing impossible
    # reference windows.
    model["adaptive_min_reference_points"] = min(int(model["adaptive_min_reference_points"]), int(model["adaptive_window_days"]))
    model["volatility_min_points"] = min(int(model["volatility_min_points"]), int(model["volatility_window_days"]))
    model["drawdown_min_points"] = min(int(model["drawdown_min_points"]), int(model["drawdown_window_days"]))
    model["regime_high_min_points"] = min(int(model["regime_high_min_points"]), int(model["adaptive_window_days"]))
    model["percentile_min_points"] = min(int(model["percentile_min_points"]), int(model["percentile_window_days"]))
    if float(model["volatility_regime_low_ratio"]) >= float(model["volatility_regime_high_ratio"]):
        model["volatility_regime_low_ratio"] = DEFAULT_MODEL_SETTINGS["volatility_regime_low_ratio"]
        model["volatility_regime_high_ratio"] = DEFAULT_MODEL_SETTINGS["volatility_regime_high_ratio"]
    model["turning_point_separation_days"] = min(
        int(model["turning_point_separation_days"]), max(3, int(model["turning_point_lookback_days"]) - 1)
    )
    if int(model["volatility_fast_window_days"]) >= int(model["volatility_slow_window_days"]):
        model["volatility_fast_window_days"] = DEFAULT_MODEL_SETTINGS["volatility_fast_window_days"]
        model["volatility_slow_window_days"] = DEFAULT_MODEL_SETTINGS["volatility_slow_window_days"]
    if float(model["turning_zone_threshold"]) >= float(model["turning_extreme_threshold"]):
        model["turning_zone_threshold"] = DEFAULT_MODEL_SETTINGS["turning_zone_threshold"]
        model["turning_extreme_threshold"] = DEFAULT_MODEL_SETTINGS["turning_extreme_threshold"]

    raw_signal_weights = raw.get("signal_weights") if isinstance(raw.get("signal_weights"), Mapping) else {}
    signal_weights: dict[str, dict[str, float]] = {}
    for component, defaults in DEFAULT_SIGNAL_WEIGHTS.items():
        raw_component = raw_signal_weights.get(component) if isinstance(raw_signal_weights.get(component), Mapping) else {}
        normalized_component: dict[str, float] = {}
        for key, default in defaults.items():
            candidate = _finite(raw_component.get(key)) if isinstance(raw_component, Mapping) else None
            normalized_component[key] = _clamp(default if candidate is None else candidate, 0.0, 100.0)
        if sum(normalized_component.values()) <= 0:
            normalized_component = dict(defaults)
        signal_weights[component] = normalized_component

    raw_turning_weights = raw.get("turning_point_weights") if isinstance(raw.get("turning_point_weights"), Mapping) else {}
    turning_point_weights: dict[str, dict[str, float]] = {}
    for model_name, defaults in DEFAULT_TURNING_POINT_WEIGHTS.items():
        raw_model_weights = raw_turning_weights.get(model_name) if isinstance(raw_turning_weights.get(model_name), Mapping) else {}
        normalized_model_weights: dict[str, float] = {}
        for key, default in defaults.items():
            candidate = _finite(raw_model_weights.get(key)) if isinstance(raw_model_weights, Mapping) else None
            normalized_model_weights[key] = _clamp(default if candidate is None else candidate, 0.0, 100.0)
        if sum(normalized_model_weights.values()) <= 0:
            normalized_model_weights = dict(defaults)
        turning_point_weights[model_name] = normalized_model_weights

    return {
        "profile": profile,
        "currency": currency,
        "weights": weights,
        "signal_weights": signal_weights,
        "turning_point_weights": turning_point_weights,
        "thresholds": thresholds,
        "model": model,
        "score_version": SCORE_VERSION,
        "adaptive_window_days": model["adaptive_window_days"],
        "adaptive_mode": "automatic_volatility_regime",
    }

def _rating(score: float, thresholds: Mapping[str, float]) -> str:
    if score >= thresholds["extreme"]:
        return "extreme"
    if score >= thresholds["very_cheap"]:
        return "very_cheap"
    if score >= thresholds["cheap"]:
        return "cheap"
    if score >= thresholds["interesting"]:
        return "interesting"
    if score < thresholds["very_expensive_max"]:
        return "very_expensive"
    if score < thresholds["expensive_max"]:
        return "expensive"
    return "neutral"


def calculate_buy_opportunity(
    history: Mapping[str, Any],
    current_price: Any,
    *,
    currency: str = "EUR",
    settings: Mapping[str, Any] | None = None,
    as_of_day: str | date | None = None,
) -> dict[str, Any]:
    """Calculate an adaptive 0..100 buy-opportunity score from public prices only."""
    current = _positive(current_price)
    normalized = normalize_buy_opportunity_settings(settings, [currency])
    if current is None:
        return {
            "score": None,
            "rating": "unavailable",
            "currency": str(currency).upper(),
            "current_price": None,
            "score_version": SCORE_VERSION,
            "settings": normalized,
            "reason": "current_price_unavailable",
        }

    if isinstance(as_of_day, date):
        today = as_of_day
    elif as_of_day:
        try:
            today = date.fromisoformat(str(as_of_day)[:10])
        except ValueError:
            today = date.today()
    else:
        today = date.today()

    historical = _parse_history(history)
    prior_history = [(day, price) for day, price in historical if day <= today]
    if prior_history and prior_history[-1][0] == today:
        prior_history[-1] = (today, current)
    else:
        prior_history.append((today, current))
    seen: dict[date, float] = {}
    for day, price in prior_history:
        if day <= today:
            seen[day] = price
    dated_values = sorted(seen.items())
    values = [price for _, price in dated_values]

    model = normalized["model"]
    minimum_history_points = int(model["minimum_history_points"])
    if len(values) < minimum_history_points:
        return {
            "score": None,
            "rating": "unavailable",
            "currency": str(currency).upper(),
            "current_price": current,
            "score_version": SCORE_VERSION,
            "settings": normalized,
            "history_points": len(values),
            "minimum_history_points": minimum_history_points,
            "reason": "insufficient_history",
        }

    index = len(values) - 1
    p_short_dev = int(model["short_deviation_days"])
    p_short = int(model["trend_short_days"])
    p_pi_short = int(model["pi_short_days"])
    p_base = int(model["trend_base_days"])
    p_pi_long = int(model["pi_long_days"])
    p_mid = int(model["trend_mid_days"])
    p_long = int(model["trend_long_days"])
    p_cycle = int(model["trend_cycle_days"])
    p_vol = int(model["volatility_window_days"])
    p_vol_min = int(model["volatility_min_points"])
    p_drawdown = int(model["drawdown_window_days"])
    p_drawdown_min = int(model["drawdown_min_points"])
    p_adaptive = int(model["adaptive_window_days"])
    p_adaptive_min = int(model["adaptive_min_reference_points"])
    p_regime_min = int(model["regime_high_min_points"])
    p_percentile = int(model["percentile_window_days"])
    p_percentile_min = int(model["percentile_min_points"])
    p_rsi = int(model["rsi_period_days"])
    p_mom_short = int(model["momentum_short_days"])
    p_mom_long = int(model["momentum_long_days"])
    volatility_floor = float(model["volatility_floor_pct"]) / 100.0

    ma20_s = _rolling_mean_series(values, p_short_dev)
    ma50_s = _rolling_mean_series(values, p_short)
    ma111_s = _rolling_mean_series(values, p_pi_short)
    ma200_s = _rolling_mean_series(values, p_base)
    ma350_s = _rolling_mean_series(values, p_pi_long)
    ma365_s = _rolling_mean_series(values, p_mid)
    ma730_s = _rolling_mean_series(values, p_long)
    ma1400_s = _rolling_mean_series(values, p_cycle)
    vol365_s = _rolling_volatility_series(values, p_vol, min_points=p_vol_min)
    high365_s = _rolling_max_series(values, p_drawdown, min_points=p_drawdown_min)
    regime_high_s = _rolling_max_series(values, p_adaptive, min_points=p_regime_min)
    rsi_s = _rsi_series(values, p_rsi)

    log_values = [math.log(value) for value in values]
    log_mean20_s = _rolling_mean_series(log_values, p_short_dev)
    log_std20_s = _rolling_std_series(log_values, p_short_dev)

    trend200_s: list[float | None] = [None] * len(values)
    trend730_s: list[float | None] = [None] * len(values)
    trend1400_s: list[float | None] = [None] * len(values)
    ma365_dev_s: list[float | None] = [None] * len(values)
    ma50_dev_s: list[float | None] = [None] * len(values)
    dd365_norm_s: list[float | None] = [None] * len(values)
    dd_regime_norm_s: list[float | None] = [None] * len(values)
    mom30_s: list[float | None] = [None] * len(values)
    mom90_s: list[float | None] = [None] * len(values)
    z20_s: list[float | None] = [None] * len(values)
    pi_cycle_s: list[float | None] = [None] * len(values)
    two_year_upper_s: list[float | None] = [None] * len(values)

    for i, price in enumerate(values):
        # Score each day against volatility known before that day. This avoids
        # letting an unusually large current move inflate its own denominator and
        # preserves monotonicity when only the hypothetical current price changes.
        vol = vol365_s[i - 1] if i > 0 else None
        trend200_s[i] = _safe_normalized_log_ratio(price, ma200_s[i], vol, volatility_floor)
        trend730_s[i] = _safe_normalized_log_ratio(price, ma730_s[i], vol, volatility_floor)
        trend1400_s[i] = _safe_normalized_log_ratio(price, ma1400_s[i], vol, volatility_floor)
        ma365_dev_s[i] = _safe_normalized_log_ratio(price, ma365_s[i], vol, volatility_floor)
        ma50_dev_s[i] = _safe_normalized_log_ratio(price, ma50_s[i], vol, volatility_floor)
        high365 = high365_s[i]
        if high365 is not None and high365 > 0 and vol is not None and vol > 0:
            dd365_norm_s[i] = math.log(price / high365) / max(vol, volatility_floor)
        regime_high = regime_high_s[i]
        if regime_high is not None and regime_high > 0 and vol is not None and vol > 0:
            dd_regime_norm_s[i] = math.log(price / regime_high) / max(vol, volatility_floor)
        mom30_s[i] = _standardized_return(price, values[i - p_mom_short] if i >= p_mom_short else None, vol, p_mom_short, volatility_floor)
        mom90_s[i] = _standardized_return(price, values[i - p_mom_long] if i >= p_mom_long else None, vol, p_mom_long, volatility_floor)
        if log_mean20_s[i] is not None and log_std20_s[i] is not None and log_std20_s[i] > 0:
            z20_s[i] = (log_values[i] - log_mean20_s[i]) / log_std20_s[i]
        ma111 = ma111_s[i]
        ma350 = ma350_s[i]
        if ma111 is not None and ma350 is not None and ma350 > 0:
            pi_cycle_s[i] = ma111 / (2.0 * ma350)
        ma730 = ma730_s[i]
        if ma730 is not None and ma730 > 0:
            two_year_upper_s[i] = price / (float(model["two_year_multiplier"]) * ma730)

    trend200_score = _cheapness_percentile(trend200_s, index, p_adaptive, p_adaptive_min)
    trend730_score = _cheapness_percentile(trend730_s, index, p_adaptive, p_adaptive_min)
    trend1400_score = _cheapness_percentile(trend1400_s, index, p_adaptive, p_adaptive_min)

    dd365_score = _cheapness_percentile(dd365_norm_s, index, p_adaptive, p_adaptive_min)
    dd_regime_score = _cheapness_percentile(dd_regime_norm_s, index, p_adaptive, p_adaptive_min)

    prior_prices = values[:-1]
    percentile365 = _rolling_percentile_current(current, prior_prices, p_percentile, p_percentile_min)
    percentile4y = _rolling_percentile_current(current, prior_prices, p_adaptive, min(p_adaptive_min, p_adaptive))
    percentile365_score = 100.0 - percentile365 if percentile365 is not None else None
    ma365_score = _cheapness_percentile(ma365_dev_s, index, p_adaptive, p_adaptive_min)

    z20_score = _cheapness_percentile(z20_s, index, p_adaptive, p_adaptive_min)
    ma50_score = _cheapness_percentile(ma50_dev_s, index, p_adaptive, p_adaptive_min)

    mom30_score = _cheapness_percentile(mom30_s, index, p_adaptive, p_adaptive_min)
    mom90_score = _cheapness_percentile(mom90_s, index, p_adaptive, p_adaptive_min)
    rsi_score = _cheapness_percentile(rsi_s, index, p_adaptive, p_adaptive_min)

    pi_cycle_score = _cheapness_percentile(pi_cycle_s, index, p_adaptive, p_adaptive_min)
    two_year_upper_score = _cheapness_percentile(two_year_upper_s, index, p_adaptive, p_adaptive_min)

    power_law = _power_law_fit(dated_values, today, int(model["power_law_min_points"]))
    power_law_ratio = _ratio(current, power_law.get("fair_value"))
    power_law["ratio"] = power_law_ratio
    power_law_score = _piecewise(power_law_ratio, [
        (0.40, 100), (0.60, 90), (0.80, 75), (1.00, 55),
        (1.30, 35), (1.70, 15), (2.20, 0),
    ])

    signal_weights = normalized["signal_weights"]
    long_term_score = _weighted_average_available({
        "trend_base": trend200_score, "trend_long": trend730_score,
        "trend_cycle": trend1400_score, "power_law": power_law_score,
    }, signal_weights["long_term"])
    drawdown_score = _weighted_average_available({
        "drawdown_local": dd365_score, "drawdown_regime": dd_regime_score,
    }, signal_weights["drawdown"])
    range_score = _weighted_average_available({
        "price_percentile": percentile365_score, "trend_mid": ma365_score,
    }, signal_weights["range"])
    deviation_score = _weighted_average_available({
        "short_z": z20_score, "trend_short": ma50_score,
    }, signal_weights["deviation"])
    momentum_score = _weighted_average_available({
        "momentum_short": mom30_score, "momentum_long": mom90_score, "rsi": rsi_score,
    }, signal_weights["momentum"])
    cycle_score = _weighted_average_available({
        "trend_cycle": trend1400_score, "pi_cycle": pi_cycle_score,
        "two_year_upper": two_year_upper_score, "power_law": power_law_score,
    }, signal_weights["cycle"])

    components: dict[str, float | None] = {
        "long_term": long_term_score,
        "drawdown": drawdown_score,
        "range": range_score,
        "deviation": deviation_score,
        "momentum": momentum_score,
        "cycle": cycle_score,
    }

    configured_weights = normalized["weights"]
    available_weight = sum(
        configured_weights[key]
        for key, component in components.items()
        if component is not None and configured_weights[key] > 0
    )
    if available_weight <= 0:
        total_score = None
    else:
        total_score = sum(
            float(component) * configured_weights[key]
            for key, component in components.items()
            if component is not None and configured_weights[key] > 0
        ) / available_weight
        total_score = _clamp(total_score)

    normalized_weights = {
        key: (
            round(configured_weights[key] / available_weight * 100.0, 2)
            if available_weight > 0 and components[key] is not None and configured_weights[key] > 0
            else 0.0
        )
        for key in COMPONENT_KEYS
    }
    missing_components = [key for key, value in components.items() if value is None]

    ma20 = ma20_s[index]
    ma50 = ma50_s[index]
    ma111 = ma111_s[index]
    ma200 = ma200_s[index]
    ma350 = ma350_s[index]
    ma365 = ma365_s[index]
    ma730 = ma730_s[index]
    ma1400 = ma1400_s[index]
    volatility365_fraction = vol365_s[index]
    volatility365 = volatility365_fraction * 100.0 if volatility365_fraction is not None else None
    volatility30 = _annualized_volatility(values, 30)

    mayer = _ratio(current, ma200)
    ratio50 = _ratio(current, ma50)
    ratio365 = _ratio(current, ma365)
    ratio730 = _ratio(current, ma730)
    ratio1400 = _ratio(current, ma1400)
    ma50_200_ratio = _ratio(ma50, ma200) if ma50 is not None else None

    ath = max(values)
    high365 = high365_s[index]
    low365 = min(values[-p_drawdown:]) if len(values) >= p_drawdown else min(values)
    ath_drawdown = (1.0 - current / ath) * 100.0 if ath > 0 else None
    drawdown365 = (1.0 - current / high365) * 100.0 if high365 else None
    regime_high = regime_high_s[index]
    regime_drawdown = (1.0 - current / regime_high) * 100.0 if regime_high else None

    std20 = _std(values, 20)
    std200 = _std(values, 200)
    zscore200 = (current - ma200) / std200 if ma200 is not None and std200 is not None and std200 > 0 else None
    bollinger_percent_b = None
    if ma20 is not None and std20 is not None and std20 > 0:
        lower = ma20 - 2.0 * std20
        upper = ma20 + 2.0 * std20
        bollinger_percent_b = (current - lower) / (upper - lower)

    rsi14 = rsi_s[index]
    return7 = _percent_change(current, values[-8] if len(values) >= 8 else None)
    return30 = _percent_change(current, values[-(p_mom_short + 1)] if len(values) >= p_mom_short + 1 else None)
    return90 = _percent_change(current, values[-(p_mom_long + 1)] if len(values) >= p_mom_long + 1 else None)
    return365 = _percent_change(current, values[-366] if len(values) >= 366 else None)

    pi_cycle_ratio = pi_cycle_s[index]
    two_year_upper_ratio = two_year_upper_s[index]
    vol_reference_values = [
        value for value in vol365_s[max(0, index - p_adaptive):index]
        if value is not None and math.isfinite(value)
    ]
    volatility_reference = (
        sorted(vol_reference_values)[len(vol_reference_values) // 2] * 100.0
        if vol_reference_values else None
    )
    volatility_regime_ratio = (
        volatility365 / volatility_reference
        if volatility365 is not None and volatility_reference and volatility_reference > 0
        else None
    )
    if volatility_regime_ratio is None:
        volatility_regime = "unavailable"
    elif volatility_regime_ratio < float(model["volatility_regime_low_ratio"]):
        volatility_regime = "low"
    elif volatility_regime_ratio > float(model["volatility_regime_high_ratio"]):
        volatility_regime = "high"
    else:
        volatility_regime = "normal"

    # --- Adaptive turning-point layer -------------------------------------------------
    # These four models complement the valuation score. They remain causal and use
    # price history only, so adding them creates no new network dependency.
    tp_lookback = int(model["turning_point_lookback_days"])
    tp_separation = int(model["turning_point_separation_days"])
    tp_tolerance = float(model["divergence_price_tolerance_pct"])
    fast_vol_window = int(model["volatility_fast_window_days"])
    slow_vol_window = int(model["volatility_slow_window_days"])
    cooling_lookback = int(model["volatility_cooling_lookback_days"])
    exhaustion_days = int(model["exhaustion_short_days"])

    fast_vol_s = _rolling_volatility_series(values, fast_vol_window, min_points=max(5, min(fast_vol_window, fast_vol_window // 2)))
    slow_vol_s = _rolling_volatility_series(values, slow_vol_window, min_points=max(10, min(slow_vol_window, slow_vol_window // 2)))
    vol_ratio_s: list[float | None] = [
        (float(fast) / float(slow) if fast is not None and slow is not None and slow > 0 else None)
        for fast, slow in zip(fast_vol_s, slow_vol_s)
    ]
    volatility_stress_score = _highness_percentile(vol_ratio_s, index, p_adaptive, p_adaptive_min)

    duration_s = _days_since_rolling_high_series(values, p_adaptive)
    duration_score = _highness_percentile(duration_s, index, p_adaptive, p_adaptive_min)

    acceleration_s: list[float | None] = [
        (float(short) - float(long) if short is not None and long is not None else None)
        for short, long in zip(mom30_s, mom90_s)
    ]
    acceleration_score = _highness_percentile(acceleration_s, index, p_adaptive, p_adaptive_min)

    rsi_bottom_divergence = _divergence_score(
        values, rsi_s, index, lookback=tp_lookback, separation=tp_separation,
        tolerance_pct=tp_tolerance, direction="bottom",
    )
    rsi_top_divergence = _divergence_score(
        values, rsi_s, index, lookback=tp_lookback, separation=tp_separation,
        tolerance_pct=tp_tolerance, direction="top",
    )
    return_bottom_divergence = _divergence_score(
        values, mom30_s, index, lookback=tp_lookback, separation=tp_separation,
        tolerance_pct=tp_tolerance, direction="bottom",
    )
    return_top_divergence = _divergence_score(
        values, mom30_s, index, lookback=tp_lookback, separation=tp_separation,
        tolerance_pct=tp_tolerance, direction="top",
    )
    volatility_cooling = _volatility_cooling_score(fast_vol_s, slow_vol_s, index, cooling_lookback)
    trend_reclaim = _trend_transition_score(values, ma20_s, ma50_s, index, direction="bottom")
    trend_loss = _trend_transition_score(values, ma20_s, ma50_s, index, direction="top")

    # Short-horizon exhaustion compares the most recent standardized move with
    # the 30-day move under the volatility regime known before the current day.
    mom_exhaust_s: list[float | None] = [None] * len(values)
    for i, price in enumerate(values):
        prior_vol = vol365_s[i - 1] if i > 0 else None
        mom_exhaust_s[i] = _standardized_return(
            price, values[i - exhaustion_days] if i >= exhaustion_days else None,
            prior_vol, exhaustion_days, volatility_floor,
        )
    short_mom = mom_exhaust_s[index]
    long_mom = mom30_s[index]
    selling_exhaustion = None
    buying_exhaustion = None
    if short_mom is not None and long_mom is not None:
        sell_stress = _piecewise(long_mom, [(-2.5, 100), (-1.5, 80), (-0.75, 45), (0, 0)]) or 0.0
        sell_improve = _piecewise(short_mom - long_mom, [(0, 0), (0.5, 45), (1.5, 100)]) or 0.0
        selling_exhaustion = _clamp(math.sqrt(sell_stress * sell_improve))
        buy_stress = _piecewise(long_mom, [(0, 0), (0.75, 45), (1.5, 80), (2.5, 100)]) or 0.0
        buy_weaken = _piecewise(long_mom - short_mom, [(0, 0), (0.5, 45), (1.5, 100)]) or 0.0
        buying_exhaustion = _clamp(math.sqrt(buy_stress * buy_weaken))

    turning_weights = normalized["turning_point_weights"]
    bottom_zone_signals = {
        "valuation": long_term_score,
        "drawdown": drawdown_score,
        "duration": duration_score,
        "range": range_score,
        "momentum_stress": momentum_score,
        "volatility_stress": volatility_stress_score,
    }
    bottom_zone = _weighted_average_available(bottom_zone_signals, turning_weights["bottom_zone"])

    top_zone_signals = {
        "valuation": 100.0 - long_term_score if long_term_score is not None else None,
        "trend_extension": 100.0 - deviation_score if deviation_score is not None else None,
        "range": 100.0 - range_score if range_score is not None else None,
        "momentum_heat": 100.0 - momentum_score if momentum_score is not None else None,
        "pi_cycle": 100.0 - pi_cycle_score if pi_cycle_score is not None else None,
        "acceleration": acceleration_score,
        "near_high": 100.0 - dd_regime_score if dd_regime_score is not None else None,
    }
    top_zone = _weighted_average_available(top_zone_signals, turning_weights["top_zone"])

    # Confirmation is allowed to remember a recently extreme zone. A reversal is
    # necessarily observed after the extreme itself; binding confirmation only to
    # today's zone would discard exactly the information we want to confirm.
    zone_memory_days = int(model["turning_zone_memory_days"])
    recent_bottom_zones: list[float] = [float(bottom_zone)] if bottom_zone is not None else []
    recent_top_zones: list[float] = [float(top_zone)] if top_zone is not None else []
    memory_start = max(minimum_history_points - 1, index - zone_memory_days + 1)
    for j in range(memory_start, index):
        t200 = _cheapness_percentile(trend200_s, j, p_adaptive, p_adaptive_min)
        t730 = _cheapness_percentile(trend730_s, j, p_adaptive, p_adaptive_min)
        t1400 = _cheapness_percentile(trend1400_s, j, p_adaptive, p_adaptive_min)
        d365 = _cheapness_percentile(dd365_norm_s, j, p_adaptive, p_adaptive_min)
        dreg = _cheapness_percentile(dd_regime_norm_s, j, p_adaptive, p_adaptive_min)
        prior_j = values[:j]
        pct_j = _rolling_percentile_current(values[j], prior_j, p_percentile, p_percentile_min)
        pct_score_j = 100.0 - pct_j if pct_j is not None else None
        mid_j = _cheapness_percentile(ma365_dev_s, j, p_adaptive, p_adaptive_min)
        z_j = _cheapness_percentile(z20_s, j, p_adaptive, p_adaptive_min)
        short_j = _cheapness_percentile(ma50_dev_s, j, p_adaptive, p_adaptive_min)
        m30_j = _cheapness_percentile(mom30_s, j, p_adaptive, p_adaptive_min)
        m90_j = _cheapness_percentile(mom90_s, j, p_adaptive, p_adaptive_min)
        rsi_j = _cheapness_percentile(rsi_s, j, p_adaptive, p_adaptive_min)
        pi_j = _cheapness_percentile(pi_cycle_s, j, p_adaptive, p_adaptive_min)
        two_j = _cheapness_percentile(two_year_upper_s, j, p_adaptive, p_adaptive_min)
        long_j = _weighted_average_available({"trend_base": t200, "trend_long": t730, "trend_cycle": t1400, "power_law": None}, signal_weights["long_term"])
        draw_j = _weighted_average_available({"drawdown_local": d365, "drawdown_regime": dreg}, signal_weights["drawdown"])
        range_j = _weighted_average_available({"price_percentile": pct_score_j, "trend_mid": mid_j}, signal_weights["range"])
        dev_j = _weighted_average_available({"short_z": z_j, "trend_short": short_j}, signal_weights["deviation"])
        mom_j = _weighted_average_available({"momentum_short": m30_j, "momentum_long": m90_j, "rsi": rsi_j}, signal_weights["momentum"])
        duration_j = _highness_percentile(duration_s, j, p_adaptive, p_adaptive_min)
        vol_stress_j = _highness_percentile(vol_ratio_s, j, p_adaptive, p_adaptive_min)
        accel_j = _highness_percentile(acceleration_s, j, p_adaptive, p_adaptive_min)
        bz_j = _weighted_average_available({"valuation": long_j, "drawdown": draw_j, "duration": duration_j, "range": range_j, "momentum_stress": mom_j, "volatility_stress": vol_stress_j}, turning_weights["bottom_zone"])
        tz_j = _weighted_average_available({"valuation": 100.0 - long_j if long_j is not None else None, "trend_extension": 100.0 - dev_j if dev_j is not None else None, "range": 100.0 - range_j if range_j is not None else None, "momentum_heat": 100.0 - mom_j if mom_j is not None else None, "pi_cycle": 100.0 - pi_j if pi_j is not None else None, "acceleration": accel_j, "near_high": 100.0 - dreg if dreg is not None else None}, turning_weights["top_zone"])
        if bz_j is not None:
            recent_bottom_zones.append(float(bz_j))
        if tz_j is not None:
            recent_top_zones.append(float(tz_j))
    bottom_zone_memory = max(recent_bottom_zones) if recent_bottom_zones else bottom_zone
    top_zone_memory = max(recent_top_zones) if recent_top_zones else top_zone

    recent_slice_start = max(0, index - zone_memory_days + 1)
    recent_prices = values[recent_slice_start:index + 1]
    recent_low = min(recent_prices) if recent_prices else current
    recent_high = max(recent_prices) if recent_prices else current
    recent_low_index = recent_slice_start + recent_prices.index(recent_low) if recent_prices else index
    recent_high_index = recent_slice_start + recent_prices.index(recent_high) if recent_prices else index
    prior_vol_for_turn = vol365_s[index - 1] if index > 0 else None
    price_rebound = None
    price_rejection = None
    if prior_vol_for_turn is not None and prior_vol_for_turn > 0:
        rebound_days = max(1, index - recent_low_index)
        reject_days = max(1, index - recent_high_index)
        rebound_sigma = max(prior_vol_for_turn, volatility_floor) * math.sqrt(rebound_days / 365.0)
        reject_sigma = max(prior_vol_for_turn, volatility_floor) * math.sqrt(reject_days / 365.0)
        if rebound_sigma > 0 and recent_low > 0:
            rebound_z = math.log(current / recent_low) / rebound_sigma
            price_rebound = _piecewise(rebound_z, [(0.0, 0), (0.35, 25), (0.75, 60), (1.25, 100)])
        if reject_sigma > 0 and recent_high > 0:
            rejection_z = -math.log(current / recent_high) / reject_sigma
            price_rejection = _piecewise(rejection_z, [(0.0, 0), (0.35, 25), (0.75, 60), (1.25, 100)])

    bottom_confirmation_signals = {
        "rsi_divergence": rsi_bottom_divergence,
        "return_divergence": return_bottom_divergence,
        "volatility_cooling": volatility_cooling,
        "trend_reclaim": trend_reclaim,
        "selling_exhaustion": selling_exhaustion,
        "price_rebound": price_rebound,
    }
    bottom_confirmation_raw = _weighted_average_available(
        bottom_confirmation_signals, turning_weights["bottom_confirmation"]
    )
    top_confirmation_signals = {
        "rsi_divergence": rsi_top_divergence,
        "return_divergence": return_top_divergence,
        "volatility_cooling": volatility_cooling,
        "trend_loss": trend_loss,
        "buying_exhaustion": buying_exhaustion,
        "price_rejection": price_rejection,
    }
    top_confirmation_raw = _weighted_average_available(
        top_confirmation_signals, turning_weights["top_confirmation"]
    )
    gate_strength = float(model["confirmation_zone_gate"])
    bottom_gate = (1.0 - gate_strength) + gate_strength * ((bottom_zone_memory or 0.0) / 100.0)
    top_gate = (1.0 - gate_strength) + gate_strength * ((top_zone_memory or 0.0) / 100.0)
    bottom_confirmation = _clamp(bottom_confirmation_raw * bottom_gate) if bottom_confirmation_raw is not None else None
    top_confirmation = _clamp(top_confirmation_raw * top_gate) if top_confirmation_raw is not None else None

    market_phase = _market_phase(
        total_score, bottom_zone_memory, bottom_confirmation, top_zone_memory, top_confirmation, model
    )

    turning_points = {
        "bottom_zone": _round(bottom_zone, 2),
        "bottom_confirmation": _round(bottom_confirmation, 2),
        "bottom_confirmation_raw": _round(bottom_confirmation_raw, 2),
        "bottom_zone_memory": _round(bottom_zone_memory, 2),
        "top_zone": _round(top_zone, 2),
        "top_confirmation": _round(top_confirmation, 2),
        "top_confirmation_raw": _round(top_confirmation_raw, 2),
        "top_zone_memory": _round(top_zone_memory, 2),
        "zone_memory_days": zone_memory_days,
        "market_phase": market_phase,
        "bottom_zone_signals": {k: _round(v, 2) for k, v in bottom_zone_signals.items()},
        "bottom_confirmation_signals": {k: _round(v, 2) for k, v in bottom_confirmation_signals.items()},
        "top_zone_signals": {k: _round(v, 2) for k, v in top_zone_signals.items()},
        "top_confirmation_signals": {k: _round(v, 2) for k, v in top_confirmation_signals.items()},
        "weights": turning_weights,
        "thresholds": {
            "zone": float(model["turning_zone_threshold"]),
            "confirmation": float(model["turning_confirmation_threshold"]),
            "extreme": float(model["turning_extreme_threshold"]),
        },
        "notice": "Turning-point scores are contextual market assessments, not bottom/top declarations, trade signals, probabilities, forecasts, or investment recommendations.",
    }

    indicators = {
        "sma20": _round(ma20, 2),
        "sma50": _round(ma50, 2),
        "sma111": _round(ma111, 2),
        "sma200": _round(ma200, 2),
        "sma350": _round(ma350, 2),
        "sma365": _round(ma365, 2),
        "sma730": _round(ma730, 2),
        "sma1400": _round(ma1400, 2),
        "mayer_multiple": _round(mayer, 4),
        "price_to_sma50": _round(ratio50, 4),
        "price_to_sma365": _round(ratio365, 4),
        "price_to_sma730": _round(ratio730, 4),
        "price_to_sma1400": _round(ratio1400, 4),
        "sma50_to_sma200": _round(ma50_200_ratio, 4),
        "distance_sma50_pct": _round(_distance_pct(current, ma50), 2),
        "distance_sma200_pct": _round(_distance_pct(current, ma200), 2),
        "distance_sma365_pct": _round(_distance_pct(current, ma365), 2),
        "distance_sma730_pct": _round(_distance_pct(current, ma730), 2),
        "distance_sma1400_pct": _round(_distance_pct(current, ma1400), 2),
        "ath": _round(ath, 2),
        "ath_drawdown_pct": _round(ath_drawdown, 2),
        "high_365d": _round(high365, 2),
        "low_365d": _round(low365, 2),
        "drawdown_365d_pct": _round(drawdown365, 2),
        "regime_high": _round(regime_high, 2),
        "regime_drawdown_pct": _round(regime_drawdown, 2),
        "percentile_365d": _round(percentile365, 2),
        "percentile_4y": _round(percentile4y, 2),
        "zscore_200d": _round(zscore200, 4),
        "bollinger_percent_b_20d": _round(bollinger_percent_b, 4),
        "rsi_14": _round(rsi14, 2),
        "return_7d_pct": _round(return7, 2),
        "return_30d_pct": _round(return30, 2),
        "return_90d_pct": _round(return90, 2),
        "return_365d_pct": _round(return365, 2),
        "volatility_30d_annualized_pct": _round(volatility30, 2),
        "volatility_365d_annualized_pct": _round(volatility365, 2),
        "volatility_reference_pct": _round(volatility_reference, 2),
        "volatility_regime_ratio": _round(volatility_regime_ratio, 4),
        "volatility_regime": volatility_regime,
        "volatility_fast_annualized_pct": _round(fast_vol_s[index] * 100.0 if fast_vol_s[index] is not None else None, 2),
        "volatility_slow_annualized_pct": _round(slow_vol_s[index] * 100.0 if slow_vol_s[index] is not None else None, 2),
        "volatility_stress_ratio": _round(vol_ratio_s[index], 4),
        "days_since_regime_high": _round(duration_s[index], 0),
        "momentum_acceleration": _round(acceleration_s[index], 4),
        "turning_recent_low": _round(recent_low, 2),
        "turning_recent_high": _round(recent_high, 2),
        "turning_price_rebound_score": _round(price_rebound, 2),
        "turning_price_rejection_score": _round(price_rejection, 2),
        "adaptive_window_days": p_adaptive,
        "configured_periods": {
            "short_deviation_days": p_short_dev, "trend_short_days": p_short,
            "pi_short_days": p_pi_short, "trend_base_days": p_base,
            "pi_long_days": p_pi_long, "trend_mid_days": p_mid,
            "trend_long_days": p_long, "trend_cycle_days": p_cycle,
            "volatility_window_days": p_vol, "drawdown_window_days": p_drawdown,
            "rsi_period_days": p_rsi, "momentum_short_days": p_mom_short,
            "momentum_long_days": p_mom_long,
        },
        "power_law_fair_value": _round(power_law.get("fair_value"), 2),
        "power_law_ratio": _round(power_law_ratio, 4),
        "power_law_residual_z": _round(power_law.get("residual_z"), 4),
        "power_law_slope": _round(power_law.get("slope"), 6),
        "pi_cycle_ratio": _round(pi_cycle_ratio, 4),
        "two_year_upper_ratio": _round(two_year_upper_ratio, 4),
        "normalized_trend_200d": _round(trend200_s[index], 4),
        "normalized_drawdown_365d": _round(dd365_norm_s[index], 4),
        "standardized_return_30d": _round(mom30_s[index], 4),
        "standardized_return_90d": _round(mom90_s[index], 4),
    }

    sub_scores = {
        "mayer_multiple": _round(trend200_score, 2),
        "price_to_sma730": _round(trend730_score, 2),
        "price_to_sma1400": _round(trend1400_score, 2),
        "ath_drawdown": _round(dd_regime_score, 2),
        "drawdown_365d": _round(dd365_score, 2),
        "percentile_365d": _round(percentile365_score, 2),
        "percentile_4y": None,
        "zscore_200d": _round(trend200_score, 2),
        "bollinger_20d": _round(z20_score, 2),
        "rsi_14": _round(rsi_score, 2),
        "return_30d": _round(mom30_score, 2),
        "return_90d": _round(mom90_score, 2),
        "power_law": _round(power_law_score, 2),
        "pi_cycle": _round(pi_cycle_score, 2),
        "two_year_upper": _round(two_year_upper_score, 2),
        "ma365_deviation": _round(ma365_score, 2),
        "ma50_deviation": _round(ma50_score, 2),
        "regime_drawdown": _round(dd_regime_score, 2),
    }

    score_rounded = int(round(total_score)) if total_score is not None else None
    thresholds = normalized["thresholds"]
    return {
        "score": score_rounded,
        "score_raw": _round(total_score, 2),
        "rating": _rating(float(score_rounded), thresholds) if score_rounded is not None else "unavailable",
        "currency": str(currency).upper(),
        "current_price": _round(current, 2),
        "as_of_day": today.isoformat(),
        "score_version": SCORE_VERSION,
        "scoring_mode": "automatic_volatility_regime",
        "profile": normalized["profile"],
        "component_scores": {key: _round(value, 2) for key, value in components.items()},
        "sub_scores": sub_scores,
        "configured_weights": {key: _round(value, 2) for key, value in configured_weights.items()},
        "effective_weights": normalized_weights,
        "signal_weights": normalized["signal_weights"],
        "model_settings": normalized["model"],
        "thresholds": thresholds,
        "turning_points": turning_points,
        "turning_point_weights": turning_weights,
        "assessment_notice": "Additional model-based market assessment from public historical price data. Not a buy signal, bottom/top declaration, forecast, probability, or investment recommendation.",
        "network_policy": "price_history_only_no_new_outbound_connections",
        "indicators": indicators,
        "data_quality": {
            "history_points": len(values),
            "first_day": dated_values[0][0].isoformat() if dated_values else None,
            "last_day": dated_values[-1][0].isoformat() if dated_values else None,
            "missing_components": missing_components,
            "available_components": len(COMPONENT_KEYS) - len(missing_components),
            "component_count": len(COMPONENT_KEYS),
            "weight_coverage_pct": _round(available_weight / sum(configured_weights.values()) * 100.0, 2)
            if sum(configured_weights.values()) > 0 else 0.0,
            "adaptive_window_days": p_adaptive,
            "adaptive_reference_min_points": p_adaptive_min,
            "look_ahead": False,
        },
    }



def _power_law_fair_series(dated: list[tuple[date, float]], min_points: int) -> list[float | None]:
    out: list[float | None] = [None] * len(dated)
    n = 0
    sx = sy = sx2 = sxy = 0.0
    for index, (day, price) in enumerate(dated):
        elapsed = (day - GENESIS_DATE).days
        if elapsed <= 0 or price <= 0:
            continue
        x = math.log(float(elapsed)); y = math.log(float(price))
        n += 1; sx += x; sy += y; sx2 += x * x; sxy += x * y
        if n < max(2, int(min_points)):
            continue
        denominator = sx2 - (sx * sx / n)
        if denominator <= 0:
            continue
        slope = (sxy - (sx * sy / n)) / denominator
        intercept = (sy / n) - slope * (sx / n)
        out[index] = math.exp(intercept + slope * x)
    return out


def _main_score_series(dated: list[tuple[date, float]], normalized: Mapping[str, Any]) -> list[float | None]:
    """Calculate the main 0..100 score for every day in one causal pass."""
    values = [price for _, price in dated]
    n = len(values)
    if not values:
        return []
    model = normalized["model"]
    minimum_history_points = int(model["minimum_history_points"])
    p_short_dev = int(model["short_deviation_days"]); p_short = int(model["trend_short_days"])
    p_pi_short = int(model["pi_short_days"]); p_base = int(model["trend_base_days"])
    p_pi_long = int(model["pi_long_days"]); p_mid = int(model["trend_mid_days"])
    p_long = int(model["trend_long_days"]); p_cycle = int(model["trend_cycle_days"])
    p_vol = int(model["volatility_window_days"]); p_vol_min = int(model["volatility_min_points"])
    p_drawdown = int(model["drawdown_window_days"]); p_drawdown_min = int(model["drawdown_min_points"])
    p_adaptive = int(model["adaptive_window_days"]); p_adaptive_min = int(model["adaptive_min_reference_points"])
    p_regime_min = int(model["regime_high_min_points"]); p_percentile = int(model["percentile_window_days"])
    p_percentile_min = int(model["percentile_min_points"]); p_rsi = int(model["rsi_period_days"])
    p_mom_short = int(model["momentum_short_days"]); p_mom_long = int(model["momentum_long_days"])
    volatility_floor = float(model["volatility_floor_pct"]) / 100.0

    ma20_s = _rolling_mean_series(values, p_short_dev)
    ma50_s = _rolling_mean_series(values, p_short)
    ma111_s = _rolling_mean_series(values, p_pi_short)
    ma200_s = _rolling_mean_series(values, p_base)
    ma350_s = _rolling_mean_series(values, p_pi_long)
    ma365_s = _rolling_mean_series(values, p_mid)
    ma730_s = _rolling_mean_series(values, p_long)
    ma1400_s = _rolling_mean_series(values, p_cycle)
    vol365_s = _rolling_volatility_series(values, p_vol, min_points=p_vol_min)
    high365_s = _rolling_max_series(values, p_drawdown, min_points=p_drawdown_min)
    regime_high_s = _rolling_max_series(values, p_adaptive, min_points=p_regime_min)
    rsi_s = _rsi_series(values, p_rsi)
    log_values = [math.log(value) for value in values]
    log_mean20_s = _rolling_mean_series(log_values, p_short_dev)
    log_std20_s = _rolling_std_series(log_values, p_short_dev)

    trend200_s: list[float | None] = [None] * n; trend730_s: list[float | None] = [None] * n
    trend1400_s: list[float | None] = [None] * n; ma365_dev_s: list[float | None] = [None] * n
    ma50_dev_s: list[float | None] = [None] * n; dd365_norm_s: list[float | None] = [None] * n
    dd_regime_norm_s: list[float | None] = [None] * n; mom30_s: list[float | None] = [None] * n
    mom90_s: list[float | None] = [None] * n; z20_s: list[float | None] = [None] * n
    pi_cycle_s: list[float | None] = [None] * n; two_year_upper_s: list[float | None] = [None] * n
    for i, price in enumerate(values):
        vol = vol365_s[i - 1] if i > 0 else None
        trend200_s[i] = _safe_normalized_log_ratio(price, ma200_s[i], vol, volatility_floor)
        trend730_s[i] = _safe_normalized_log_ratio(price, ma730_s[i], vol, volatility_floor)
        trend1400_s[i] = _safe_normalized_log_ratio(price, ma1400_s[i], vol, volatility_floor)
        ma365_dev_s[i] = _safe_normalized_log_ratio(price, ma365_s[i], vol, volatility_floor)
        ma50_dev_s[i] = _safe_normalized_log_ratio(price, ma50_s[i], vol, volatility_floor)
        high365 = high365_s[i]
        if high365 is not None and high365 > 0 and vol is not None and vol > 0:
            dd365_norm_s[i] = math.log(price / high365) / max(vol, volatility_floor)
        regime_high = regime_high_s[i]
        if regime_high is not None and regime_high > 0 and vol is not None and vol > 0:
            dd_regime_norm_s[i] = math.log(price / regime_high) / max(vol, volatility_floor)
        mom30_s[i] = _standardized_return(price, values[i-p_mom_short] if i >= p_mom_short else None, vol, p_mom_short, volatility_floor)
        mom90_s[i] = _standardized_return(price, values[i-p_mom_long] if i >= p_mom_long else None, vol, p_mom_long, volatility_floor)
        if log_mean20_s[i] is not None and log_std20_s[i] is not None and log_std20_s[i] > 0:
            z20_s[i] = (log_values[i] - log_mean20_s[i]) / log_std20_s[i]
        if ma111_s[i] is not None and ma350_s[i] is not None and ma350_s[i] > 0:
            pi_cycle_s[i] = ma111_s[i] / (2.0 * ma350_s[i])
        if ma730_s[i] is not None and ma730_s[i] > 0:
            two_year_upper_s[i] = price / (float(model["two_year_multiplier"]) * ma730_s[i])

    fair_s = _power_law_fair_series(dated, int(model["power_law_min_points"]))
    signal_weights = normalized["signal_weights"]
    configured_weights = normalized["weights"]
    scores: list[float | None] = [None] * n
    for i, current in enumerate(values):
        if i + 1 < minimum_history_points:
            continue
        trend200_score = _cheapness_percentile(trend200_s, i, p_adaptive, p_adaptive_min)
        trend730_score = _cheapness_percentile(trend730_s, i, p_adaptive, p_adaptive_min)
        trend1400_score = _cheapness_percentile(trend1400_s, i, p_adaptive, p_adaptive_min)
        dd365_score = _cheapness_percentile(dd365_norm_s, i, p_adaptive, p_adaptive_min)
        dd_regime_score = _cheapness_percentile(dd_regime_norm_s, i, p_adaptive, p_adaptive_min)
        prior_prices = values[max(0, i-p_percentile):i]
        percentile365 = _rolling_percentile_current(current, prior_prices, p_percentile, p_percentile_min)
        percentile365_score = 100.0 - percentile365 if percentile365 is not None else None
        ma365_score = _cheapness_percentile(ma365_dev_s, i, p_adaptive, p_adaptive_min)
        z20_score = _cheapness_percentile(z20_s, i, p_adaptive, p_adaptive_min)
        ma50_score = _cheapness_percentile(ma50_dev_s, i, p_adaptive, p_adaptive_min)
        mom30_score = _cheapness_percentile(mom30_s, i, p_adaptive, p_adaptive_min)
        mom90_score = _cheapness_percentile(mom90_s, i, p_adaptive, p_adaptive_min)
        rsi_score = _cheapness_percentile(rsi_s, i, p_adaptive, p_adaptive_min)
        pi_cycle_score = _cheapness_percentile(pi_cycle_s, i, p_adaptive, p_adaptive_min)
        two_year_upper_score = _cheapness_percentile(two_year_upper_s, i, p_adaptive, p_adaptive_min)
        fair = fair_s[i]
        power_law_ratio = current / fair if fair and fair > 0 else None
        power_law_score = _piecewise(power_law_ratio, [(0.40,100),(0.60,90),(0.80,75),(1.00,55),(1.30,35),(1.70,15),(2.20,0)])
        components = {
            "long_term": _weighted_average_available({"trend_base":trend200_score,"trend_long":trend730_score,"trend_cycle":trend1400_score,"power_law":power_law_score}, signal_weights["long_term"]),
            "drawdown": _weighted_average_available({"drawdown_local":dd365_score,"drawdown_regime":dd_regime_score}, signal_weights["drawdown"]),
            "range": _weighted_average_available({"price_percentile":percentile365_score,"trend_mid":ma365_score}, signal_weights["range"]),
            "deviation": _weighted_average_available({"short_z":z20_score,"trend_short":ma50_score}, signal_weights["deviation"]),
            "momentum": _weighted_average_available({"momentum_short":mom30_score,"momentum_long":mom90_score,"rsi":rsi_score}, signal_weights["momentum"]),
            "cycle": _weighted_average_available({"trend_cycle":trend1400_score,"pi_cycle":pi_cycle_score,"two_year_upper":two_year_upper_score,"power_law":power_law_score}, signal_weights["cycle"]),
        }
        available_weight = sum(configured_weights[key] for key,value in components.items() if value is not None and configured_weights[key] > 0)
        if available_weight > 0:
            scores[i] = _clamp(sum(float(value)*configured_weights[key] for key,value in components.items() if value is not None and configured_weights[key] > 0) / available_weight)
    return scores


def calculate_buy_opportunity_history(
    history: Mapping[str, Any], current_price: Any, *, currency: str = "EUR",
    settings: Mapping[str, Any] | None = None, as_of_day: str | date | None = None,
    start_day: str | date | None = None, max_points: int = 360,
) -> dict[str, Any]:
    """Reconstruct the causal historical main score efficiently in one pass."""
    normalized = normalize_buy_opportunity_settings(settings, [currency])
    if isinstance(as_of_day, date): today = as_of_day
    elif as_of_day:
        try: today = date.fromisoformat(str(as_of_day)[:10])
        except ValueError: today = date.today()
    else: today = date.today()
    if isinstance(start_day, date): start = start_day
    elif start_day:
        try: start = date.fromisoformat(str(start_day)[:10])
        except ValueError: start = None
    else: start = None
    dated = [(day,price) for day,price in _parse_history(history) if day <= today]
    current = _positive(current_price)
    if current is not None:
        if dated and dated[-1][0] == today: dated[-1] = (today,current)
        else: dated.append((today,current))
    if not dated: return {"currency":str(currency).upper(),"points":[],"settings":normalized}
    scores = _main_score_series(dated, normalized)
    eligible = [i for i,score in enumerate(scores) if score is not None and (start is None or dated[i][0] >= start)]
    limit=max(30,min(720,int(max_points or 360)))
    if len(eligible)>limit:
        step=(len(eligible)-1)/float(limit-1); selected=sorted(set(eligible[round(i*step)] for i in range(limit)))
    else: selected=eligible
    thresholds=normalized["thresholds"]
    points=[{"date":dated[i][0].isoformat(),"score":round(float(scores[i]),2),"rating":_rating(float(scores[i]),thresholds),"price":float(dated[i][1])} for i in selected]
    return {"currency":str(currency).upper(),"points":points,"sampled":len(selected)<len(eligible),"source_points":len(eligible),"returned_points":len(points),"settings":normalized,"score_version":SCORE_VERSION}
