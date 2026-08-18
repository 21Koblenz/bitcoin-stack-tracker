"""Shared, bounded runtime cache for the market-assessment model.

The scoring model is intentionally CPU-heavy. Home Assistant can update public
prices every minute and the native panel can be open on several clients at once,
so recalculating the complete model on every coordinator/UI refresh creates
avoidable CPU stalls and large amounts of short-lived Python objects.

This module keeps one cache per config entry, runs the model only in HA's
executor, and coalesces concurrent requests. Structural input changes (settings
or historical source data) invalidate immediately. Intraday live-price ticks do
not invalidate the current snapshot before the five-minute TTL expires. When
the next calculation is due it uses the newest coordinator price available at
that moment. Historical chart scores are cached separately and are never
invalidated by intraday price ticks. A separate low-duty background task may
reconstruct the last 90 days of five-minute scores from public OHLC data.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from functools import partial
from time import monotonic
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .buy_opportunity import calculate_buy_opportunity, normalize_buy_opportunity_settings
from .const import CONF_BUY_OPPORTUNITY_SETTINGS, DOMAIN
from .helpers import configured_currencies, effective_settings
from .market_assessment_backfill import async_market_assessment_backfill_loop
from .market_assessment_intraday_cache import market_assessment_intraday_signature

_LOGGER = logging.getLogger(__name__)

MARKET_ASSESSMENT_CACHE_SECONDS = 5 * 60
_CACHE_KEY = "_market_assessment_cache"
_TASK_KEY = "_market_assessment_task"
_BACKFILL_TASK_KEY = "_market_assessment_backfill_task"


def _assessment_inputs(
    entry: ConfigEntry,
    coordinator: Any,
    history_storage: Any,
) -> tuple[tuple[Any, ...], dict[str, Any], Any, str, dict[str, Any], str]:
    current_settings = effective_settings(entry)
    currencies = configured_currencies(current_settings)
    scoring_settings = normalize_buy_opportunity_settings(
        current_settings.get(CONF_BUY_OPPORTUNITY_SETTINGS), currencies
    )
    currency = scoring_settings["currency"]
    live = coordinator.data or {}
    prices = live.get("prices", {}) if isinstance(live.get("prices", {}), dict) else {}
    current_price = prices.get(currency)
    history_data = history_storage.data
    history = history_data.get("prices", {}).get(currency, {})
    price_source = "live"
    if current_price is None and isinstance(history, dict) and history:
        for day in sorted(history, reverse=True):
            try:
                candidate = float(history[day])
            except (TypeError, ValueError):
                continue
            if candidate > 0:
                current_price = candidate
                price_source = "history_fallback"
                break

    today = dt_util.utcnow().date()
    latest_history_day = max(history, default=None) if isinstance(history, dict) else None
    latest_history_value = history.get(latest_history_day) if latest_history_day and isinstance(history, dict) else None
    # Keep the expensive current assessment bounded to one calculation per five
    # minutes. Do not include ``current_price`` in the structural key: doing so
    # would let every coordinator quote bypass the TTL. The newest live price is
    # still passed into calculate_buy_opportunity() once the TTL expires.
    # Settings/history/day/source transitions remain immediate invalidators.
    structural_key = (
        currency,
        price_source,
        history_data.get("last_sync"),
        len(history) if isinstance(history, dict) else 0,
        latest_history_day,
        latest_history_value,
        repr(scoring_settings),
        today,
    )
    return structural_key, history, current_price, currency, scoring_settings, price_source


def _ensure_backfill(
    hass: HomeAssistant,
    entry: ConfigEntry,
    history_storage: Any,
    runtime: dict[str, Any],
    *,
    currency: str,
    settings: dict[str, Any],
) -> None:
    """Ensure at most one low-duty 90-day backfill task exists per entry."""
    intraday_cache = runtime.get("market_assessment_intraday_cache")
    if intraday_cache is None:
        return
    signature = market_assessment_intraday_signature(currency=currency, settings=settings)
    status = runtime.get("market_assessment_backfill_status")
    if (
        isinstance(status, dict)
        and bool(status.get("complete"))
        and str(status.get("signature") or "") == signature
    ):
        return
    current = runtime.get(_BACKFILL_TASK_KEY)
    if current is not None and not current.done():
        return

    task = hass.async_create_task(
        async_market_assessment_backfill_loop(
            hass, entry, history_storage, intraday_cache
        ),
        "Bitcoin Stack Tracker throttled market assessment backfill",
    )
    runtime[_BACKFILL_TASK_KEY] = task

    def _finished(done: Any) -> None:
        active = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if isinstance(active, dict) and active.get(_BACKFILL_TASK_KEY) is done:
            active.pop(_BACKFILL_TASK_KEY, None)
        try:
            done.result()
        except Exception:
            _LOGGER.debug("Market-assessment backfill task ended", exc_info=True)

    task.add_done_callback(_finished)


async def async_market_assessment(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: Any,
    history_storage: Any,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Return a cached assessment snapshot without blocking HA's event loop."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not isinstance(runtime, dict):
        raise RuntimeError("Bitcoin Stack Tracker runtime is unavailable")

    structural_key, history, current_price, currency, settings, price_source = _assessment_inputs(
        entry, coordinator, history_storage
    )
    _ensure_backfill(
        hass,
        entry,
        history_storage,
        runtime,
        currency=currency,
        settings=settings,
    )
    now = monotonic()
    cached = runtime.get(_CACHE_KEY)
    if (
        not force
        and isinstance(cached, dict)
        and cached.get("structural_key") == structural_key
        and now - float(cached.get("monotonic_at") or 0.0) < MARKET_ASSESSMENT_CACHE_SECONDS
        and isinstance(cached.get("result"), dict)
    ):
        return cached

    running = runtime.get(_TASK_KEY)
    if running is not None and not running.done():
        try:
            await running
        except Exception:
            # The caller below will retry with its own current inputs.
            pass
        cached = runtime.get(_CACHE_KEY)
        now = monotonic()
        if (
            not force
            and isinstance(cached, dict)
            and cached.get("structural_key") == structural_key
            and now - float(cached.get("monotonic_at") or 0.0) < MARKET_ASSESSMENT_CACHE_SECONDS
            and isinstance(cached.get("result"), dict)
        ):
            return cached

    async def _calculate() -> dict[str, Any]:
        result = await hass.async_add_executor_job(
            partial(
                calculate_buy_opportunity,
                history,
                current_price,
                currency=currency,
                settings=settings,
                as_of_day=dt_util.utcnow().date(),
            )
        )
        snapshot = {
            "structural_key": structural_key,
            "monotonic_at": monotonic(),
            "calculated_at": datetime.now(timezone.utc).isoformat(),
            "result": result,
            "settings": settings,
            "currency": currency,
            "price_source": price_source,
        }
        runtime[_CACHE_KEY] = snapshot
        intraday_cache = runtime.get("market_assessment_intraday_cache")
        if intraday_cache is not None:
            try:
                signature = market_assessment_intraday_signature(
                    currency=currency, settings=settings
                )
                await intraday_cache.async_record(
                    signature,
                    calculated_at=snapshot["calculated_at"],
                    result=result,
                    currency=currency,
                )
            except Exception:
                # Snapshot persistence is display-only and must never turn a
                # successful market calculation into a failed HA sensor update.
                _LOGGER.debug("Could not persist market-assessment intraday snapshot", exc_info=True)
        return snapshot

    task = hass.async_create_task(
        _calculate(), "Bitcoin Stack Tracker cached market assessment"
    )
    runtime[_TASK_KEY] = task
    try:
        return await task
    finally:
        if runtime.get(_TASK_KEY) is task:
            runtime.pop(_TASK_KEY, None)


def invalidate_market_assessment_cache(hass: HomeAssistant, entry_id: str) -> None:
    """Invalidate cached public-model output after settings/config changes."""
    runtime = hass.data.get(DOMAIN, {}).get(entry_id)
    if isinstance(runtime, dict):
        runtime.pop(_CACHE_KEY, None)
