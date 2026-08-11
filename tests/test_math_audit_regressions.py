from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
APP = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")
HISTORY = (COMP / "history.py").read_text(encoding="utf-8")
MIGRATIONS = (COMP / "migrations.py").read_text(encoding="utf-8")
STORAGE = (COMP / "storage.py").read_text(encoding="utf-8")
MATH = (COMP / "frontend/static/performance-math.js").read_text(encoding="utf-8")


def test_daily_history_snapshots_use_real_utc_instants_and_invalidate_old_cache():
    assert "numeric = _timestamp_value(ordered[position].get(\"timestamp\"))" in HISTORY
    assert "cutoff = as_of.timestamp()" in HISTORY
    assert '"chart_schema": 5' in HISTORY
    assert 'entry_day = str(ordered[position].get("timestamp", ""))[:10]' not in HISTORY


def test_legacy_migration_and_storage_sort_actual_instants():
    assert "def _entry_sort_key" in MIGRATIONS
    assert "normalized_entries.sort(key=_entry_sort_key)" in MIGRATIONS
    assert "def _ledger_sort_key" in STORAGE
    assert "entries.sort(key=_ledger_sort_key)" in STORAGE
    assert 'updated["timestamp"] = _validated_ledger_timestamp(updated["timestamp"])' in STORAGE


def test_daily_chart_points_are_end_of_day_and_analytics_skip_visual_downsampling():
    assert "function seriesValuationTimestamp(key)" in APP
    assert "T23:59:59.999Z" in APP
    assert "function analyticsValues(currency) { return chartValues(currency,true); }" in APP
    assert "analytics ? resampleSeriesUniform(rawPrice,1440) : resampleLongRangeUniform(rawPrice)" in APP


def test_intraday_fifo_metrics_replay_every_booking():
    assert "function fifoMetricEvents(currency)" in APP
    assert "const metricEvents = fifoMetricEvents(currency)" in APP
    assert "basisEvents[item.key] = item.basis" in APP
    assert "realizedEvents[item.key] = item.realized" in APP
    assert "knownEvents[item.key] = item.knownBtc" in APP


def test_first_purchase_range_and_personal_year_math_are_utc_based():
    assert 'filter(entry=>entry?.type==="purchase")' in APP
    assert "getUTCFullYear" in APP and "getUTCMonth" in APP
    assert "setUTCFullYear" in APP and "setUTCMonth" in APP


def test_fifo_sale_summary_uses_selected_currency_and_unique_dispositions():
    assert "const soldBtc=currencyMatches.reduce" in APP
    assert "const dispositionCount=new Set" in APP
    assert 't("dispositionCount")' in APP


def test_dca_best_worst_include_purchase_fees():
    assert "function effectivePurchaseUnitCost(entry)" in APP
    assert "(amount*price+(Number.isFinite(fee)?fee:0))/amount" in APP
    assert "effectivePurchaseUnitCost(best)" in APP
    assert "effectivePurchaseUnitCost(worst)" in APP


def test_no_recycled_capital_pseudo_roi_and_xirr_is_365_day():
    assert "roiPercent" not in APP
    assert "lifetimeCapital" not in APP
    assert "cumulativePurchaseOutlay" in APP
    assert "const XIRR_YEAR_MS = 365 * DAY_MS" in MATH
    assert "function xirrDayTime(value)" in MATH
    assert "31557600000" not in MATH


def test_twr_does_not_silently_discard_total_losses():
    assert "subperiod > -1" not in APP
    assert "invalid_flow_factor" in MATH
    assert "negative_balance" in MATH


def test_long_range_display_keeps_real_observation_dates():
    assert "const key = new Date(item.timestamp).toISOString().slice(0,10);" in APP
    assert "synthetic bucket end" in APP


def test_undefined_average_and_return_sensors_are_not_reported_as_zero():
    sensor = (COMP / "sensor.py").read_text(encoding="utf-8")
    assert 'return float(invested / known) if known > 0 else None' in sensor
    assert 'if invested > 0 else None' in sensor
    assert 'if summary["known_btc"] > 0:' in HISTORY


def test_performance_events_use_fifo_compatible_same_timestamp_order():
    assert 'sourceSequence' in APP
    assert 'Number(["sale","expense"].includes(a.kind))-Number(["sale","expense"].includes(b.kind))' in APP
