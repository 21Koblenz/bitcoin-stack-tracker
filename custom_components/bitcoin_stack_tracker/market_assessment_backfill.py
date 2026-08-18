"""Throttled 90-day five-minute market-assessment backfill.

The live assessment cache records real observations as they happen.  This module
fills the recent public chart history after an upgrade by downloading exact
five-minute BTC candle closes from Bitstamp through the configured Tor proxy and
replaying the existing causal model at those historical timestamps.

No portfolio, wallet, address, XPUB, descriptor or other private tracker data is
used or sent to the provider.  CPU work is intentionally bounded to a tiny batch
in Home Assistant's executor followed by a pause, so the backfill can take many
hours without competing aggressively with normal Home Assistant work.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from functools import partial
import logging
from typing import Any, Mapping

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .buy_opportunity import calculate_buy_opportunity, normalize_buy_opportunity_settings
from .const import CONF_BUY_OPPORTUNITY_SETTINGS, CONF_HISTORY_ENABLED, DOMAIN
from .helpers import configured_currencies, effective_settings
from .history import _fetch_bitstamp_ohlc_samples
from .market_assessment_intraday_cache import (
    MarketAssessmentIntradayCache,
    market_assessment_intraday_signature,
)
from .network import tor_proxy_from_settings
from .storage import BitcoinHistoryStore

_LOGGER = logging.getLogger(__name__)

BACKFILL_DAYS = 90
BACKFILL_INTERVAL_MINUTES = 5
BACKFILL_PAGE_LIMIT = 1000
BACKFILL_MAX_PAGES = 40
BACKFILL_NETWORK_PAUSE_SECONDS = 2
BACKFILL_SCORE_BATCH_POINTS = 4
BACKFILL_SCORE_PAUSE_SECONDS = 20
BACKFILL_INITIAL_DELAY_SECONDS = 45
BACKFILL_RETRY_SECONDS = 6 * 60 * 60
BACKFILL_GENERATION_RETRY_SECONDS = 30


def _utc_stamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _bucket(stamp: datetime) -> str:
    minute = (stamp.minute // BACKFILL_INTERVAL_MINUTES) * BACKFILL_INTERVAL_MINUTES
    return stamp.replace(minute=minute, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")


def _score_batch(
    history: Mapping[str, Any],
    rows: list[tuple[datetime, float]],
    *,
    currency: str,
    settings: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Replay a deliberately small historical batch outside the HA event loop."""
    points: list[dict[str, Any]] = []
    for stamp, price in rows:
        result = calculate_buy_opportunity(
            history,
            price,
            currency=currency,
            settings=settings,
            as_of_day=stamp.date(),
        )
        try:
            score = float(result.get("score_raw", result.get("score")))
        except (TypeError, ValueError):
            continue
        if not 0 <= score <= 100:
            continue
        points.append(
            {
                "timestamp": stamp.isoformat(),
                "date": stamp.date().isoformat(),
                "score": score,
                "rating": str(result.get("rating") or "unavailable"),
                "price": float(price),
                "currency": currency,
                "bucket": _bucket(stamp),
                "source": "Bitstamp 5m OHLC via Tor",
                "backfilled": True,
            }
        )
    return points


def _set_status(hass: HomeAssistant, entry_id: str, **values: Any) -> None:
    runtime = hass.data.get(DOMAIN, {}).get(entry_id)
    if not isinstance(runtime, dict):
        return
    current = runtime.get("market_assessment_backfill_status")
    status = dict(current) if isinstance(current, dict) else {}
    status.update(values)
    status["updated_at"] = datetime.now(timezone.utc).isoformat()
    runtime["market_assessment_backfill_status"] = status


def _current_generation(entry: ConfigEntry) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    settings = effective_settings(entry)
    currencies = configured_currencies(settings)
    scoring = normalize_buy_opportunity_settings(
        settings.get(CONF_BUY_OPPORTUNITY_SETTINGS), currencies
    )
    currency = str(scoring["currency"]).upper()
    signature = market_assessment_intraday_signature(currency=currency, settings=scoring)
    return signature, currency, scoring, settings


async def _backfill_once(
    hass: HomeAssistant,
    entry: ConfigEntry,
    history_store: BitcoinHistoryStore,
    cache: MarketAssessmentIntradayCache,
) -> bool:
    signature, currency, scoring_settings, settings = _current_generation(entry)
    if not bool(settings.get(CONF_HISTORY_ENABLED, True)):
        _set_status(hass, entry.entry_id, state="disabled", complete=False)
        return False

    history = history_store.data.get("prices", {}).get(currency, {})
    if not isinstance(history, dict) or len(history) < 365:
        _set_status(
            hass,
            entry.entry_id,
            state="waiting_for_daily_history",
            complete=False,
            currency=currency,
        )
        return False

    proxy_url = tor_proxy_from_settings(settings)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=BACKFILL_DAYS)
    cursor = int(now.timestamp())
    candles: dict[str, float] = {}

    _set_status(
        hass,
        entry.entry_id,
        state="downloading",
        complete=False,
        currency=currency,
        interval_minutes=BACKFILL_INTERVAL_MINUTES,
        retention_days=BACKFILL_DAYS,
        source="Bitstamp",
        network_route="Tor only",
        downloaded_points=0,
    )

    for page_index in range(BACKFILL_MAX_PAGES):
        page = await _fetch_bitstamp_ohlc_samples(
            hass,
            currency,
            proxy_url,
            BACKFILL_INTERVAL_MINUTES,
            end_timestamp=cursor,
            limit=BACKFILL_PAGE_LIMIT,
            exclude_current_candle=True,
        )
        page_rows: list[tuple[datetime, str, float]] = []
        for raw_stamp, raw_price in page.items():
            stamp = _utc_stamp(raw_stamp)
            try:
                price = float(raw_price)
            except (TypeError, ValueError):
                continue
            if stamp is None or price <= 0:
                continue
            if stamp >= cutoff:
                page_rows.append((stamp, raw_stamp, price))
        if page_rows:
            for _stamp, raw_stamp, price in page_rows:
                candles[raw_stamp] = price
        all_page_stamps = [stamp for raw in page for stamp in [_utc_stamp(raw)] if stamp is not None]
        if not all_page_stamps:
            break
        oldest = min(all_page_stamps)
        _set_status(
            hass,
            entry.entry_id,
            downloaded_points=len(candles),
            downloaded_pages=page_index + 1,
        )
        if oldest <= cutoff:
            break
        next_cursor = int(oldest.timestamp()) - BACKFILL_INTERVAL_MINUTES * 60
        if next_cursor >= cursor:
            break
        cursor = next_cursor
        await asyncio.sleep(BACKFILL_NETWORK_PAUSE_SECONDS)

    ordered: list[tuple[datetime, float]] = []
    for raw_stamp, price in candles.items():
        stamp = _utc_stamp(raw_stamp)
        if stamp is not None and cutoff <= stamp <= now:
            ordered.append((stamp, float(price)))
    ordered.sort(key=lambda item: item[0])
    if not ordered:
        raise ValueError("Bitstamp returned no usable five-minute candles for backfill")

    existing = await cache.async_points(signature, since=cutoff)
    existing_buckets = {
        str(item.get("bucket") or "")
        for item in existing
        if isinstance(item, dict) and item.get("bucket")
    }
    missing = [row for row in ordered if _bucket(row[0]) not in existing_buckets]
    total = len(ordered)
    completed = total - len(missing)
    _set_status(
        hass,
        entry.entry_id,
        state="scoring" if missing else "complete",
        complete=not missing,
        source_points=total,
        completed_points=completed,
        remaining_points=len(missing),
    )
    if not missing:
        return True

    for offset in range(0, len(missing), BACKFILL_SCORE_BATCH_POINTS):
        latest_signature, latest_currency, _latest_scoring, _latest_settings = _current_generation(entry)
        if latest_signature != signature or latest_currency != currency:
            _set_status(
                hass,
                entry.entry_id,
                state="generation_changed",
                complete=False,
            )
            return False

        batch = missing[offset : offset + BACKFILL_SCORE_BATCH_POINTS]
        points = await hass.async_add_executor_job(
            partial(
                _score_batch,
                history,
                batch,
                currency=currency,
                settings=scoring_settings,
            )
        )
        added = await cache.async_merge_points(signature, points)
        completed += added
        remaining = max(0, total - completed)
        _set_status(
            hass,
            entry.entry_id,
            state="scoring",
            complete=False,
            completed_points=completed,
            remaining_points=remaining,
        )
        if offset + BACKFILL_SCORE_BATCH_POINTS < len(missing):
            await asyncio.sleep(BACKFILL_SCORE_PAUSE_SECONDS)

    _set_status(
        hass,
        entry.entry_id,
        state="complete",
        complete=True,
        completed_points=total,
        remaining_points=0,
    )
    return True


async def async_market_assessment_backfill_loop(
    hass: HomeAssistant,
    entry: ConfigEntry,
    history_store: BitcoinHistoryStore,
    cache: MarketAssessmentIntradayCache,
) -> None:
    """Run/retry the public-data backfill until the current generation is complete."""
    await asyncio.sleep(BACKFILL_INITIAL_DELAY_SECONDS)
    while True:
        try:
            if await _backfill_once(hass, entry, history_store, cache):
                return
            await asyncio.sleep(BACKFILL_GENERATION_RETRY_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # display-only background work must not break setup
            _LOGGER.warning("Market-assessment intraday backfill paused: %s", err)
            _set_status(
                hass,
                entry.entry_id,
                state="retry_wait",
                complete=False,
                error=str(err)[:240],
            )
            await asyncio.sleep(BACKFILL_RETRY_SECONDS)
