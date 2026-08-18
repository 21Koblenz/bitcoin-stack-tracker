"""Throttled 90-day five-minute market-assessment backfill.

The live assessment cache records actual observations as they happen. After an
upgrade this module can additionally reconstruct the recent public chart history
from real five-minute Bitstamp OHLC closes and the existing causal price-only
model. Reconstructed points are marked ``backfilled``; a later live observation
always wins for the same five-minute bucket.

No portfolio, wallet, address, XPUB, descriptor or other private tracker data is
used or sent to the exchange. Public requests go through the configured Tor
proxy and are fail-closed. CPU work is intentionally limited to tiny executor
batches separated by pauses, so filling all 90 days can take multiple days
without monopolising Home Assistant.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from functools import partial
import logging
from typing import Any, Mapping
from urllib.parse import urljoin, urlparse

from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .buy_opportunity import calculate_buy_opportunity, normalize_buy_opportunity_settings
from .const import CONF_BUY_OPPORTUNITY_SETTINGS, CONF_HISTORY_ENABLED, DOMAIN
from .helpers import configured_currencies, effective_settings
from .http_limits import async_json_limited
from .market_assessment_intraday_cache import (
    MarketAssessmentIntradayCache,
    market_assessment_intraday_signature,
)
from .network import async_routed_session, tor_proxy_from_settings
from .storage import BitcoinHistoryStore

_LOGGER = logging.getLogger(__name__)

BACKFILL_DAYS = 90
BACKFILL_INTERVAL_MINUTES = 5
BACKFILL_PAGE_LIMIT = 1000
BACKFILL_MAX_PAGES = 40
BACKFILL_NETWORK_PAUSE_SECONDS = 2
# The full current model is intentionally replayed only two points at a time.
# At 20 s between batches the one-time fill takes days rather than creating a
# sustained CPU spike on smaller Home Assistant hosts.
BACKFILL_SCORE_BATCH_POINTS = 2
BACKFILL_SCORE_PAUSE_SECONDS = 20
BACKFILL_INITIAL_DELAY_SECONDS = 60
BACKFILL_RETRY_SECONDS = 6 * 60 * 60
BACKFILL_GENERATION_RETRY_SECONDS = 60
BITSTAMP_OHLC_HOSTS = {"bitstamp.net", "www.bitstamp.net"}


def _utc_stamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.isdigit():
            return datetime.fromtimestamp(int(text), tz=timezone.utc)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError, OSError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _bucket(stamp: datetime) -> str:
    minute = (stamp.minute // BACKFILL_INTERVAL_MINUTES) * BACKFILL_INTERVAL_MINUTES
    return stamp.replace(minute=minute, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")


def _validated_bitstamp_redirect(current_url: str, location: str | None) -> str:
    """Keep redirects on Bitstamp HTTPS OHLC endpoints only."""
    if not location:
        raise ValueError("Bitstamp OHLC redirect did not include Location")
    candidate = urljoin(current_url, location)
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() != "https" or host not in BITSTAMP_OHLC_HOSTS:
        raise ValueError(f"Blocked unsafe Bitstamp OHLC redirect to {host or 'unknown host'}")
    if not parsed.path.startswith("/api/v2/ohlc/"):
        raise ValueError("Blocked Bitstamp redirect outside the OHLC API")
    return candidate


async def _fetch_bitstamp_5m_page(
    hass: HomeAssistant,
    *,
    currency: str,
    proxy_url: str,
    end_timestamp: int,
) -> dict[str, float]:
    """Fetch at most 1,000 exact five-minute closes through Tor.

    Bitstamp's public OHLC API documents step=300, limit<=1000 and an ``end``
    Unix timestamp. Paging backwards with ``end`` therefore does not require an
    account, API key or any user-specific request data.
    """
    market = f"btc{currency.lower()}"
    target_url = f"https://www.bitstamp.net/api/v2/ohlc/{market}/"
    request_url = target_url
    params: dict[str, Any] | None = {
        "step": BACKFILL_INTERVAL_MINUTES * 60,
        "limit": BACKFILL_PAGE_LIMIT,
        "end": int(end_timestamp),
        "exclude_current_candle": "true",
    }
    payload: Any = None
    async with async_routed_session(
        hass, target_url=target_url, proxy_url=proxy_url
    ) as (session, request_kwargs):
        async with asyncio.timeout(45):
            for _hop in range(3):
                response = await session.get(
                    request_url,
                    params=params,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "BitcoinStackTracker/0.21",
                    },
                    **request_kwargs,
                )
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    response.release()
                    request_url = _validated_bitstamp_redirect(request_url, location)
                    params = None if urlparse(request_url).query else {
                        "step": BACKFILL_INTERVAL_MINUTES * 60,
                        "limit": BACKFILL_PAGE_LIMIT,
                        "end": int(end_timestamp),
                        "exclude_current_candle": "true",
                    }
                    continue
                response.raise_for_status()
                payload = await async_json_limited(response)
                break
            else:
                raise ValueError("Too many Bitstamp OHLC redirects")

    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    rows = data.get("ohlc", []) if isinstance(data, dict) else []
    result: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        stamp = _utc_stamp(row.get("timestamp"))
        try:
            price = float(row.get("close"))
        except (TypeError, ValueError):
            continue
        if stamp is None or price <= 0:
            continue
        result[stamp.isoformat()] = price
    if not result:
        raise ValueError("Bitstamp returned no usable five-minute OHLC values")
    return result


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


def _runtime(hass: HomeAssistant, entry_id: str) -> dict[str, Any] | None:
    value = hass.data.get(DOMAIN, {}).get(entry_id)
    return value if isinstance(value, dict) else None


def _set_status(hass: HomeAssistant, entry_id: str, **values: Any) -> None:
    runtime = _runtime(hass, entry_id)
    if runtime is None:
        return
    current = runtime.get("market_assessment_backfill_status")
    status = dict(current) if isinstance(current, dict) else {}
    status.update(values)
    status["updated_at"] = datetime.now(timezone.utc).isoformat()
    runtime["market_assessment_backfill_status"] = status


async def _sleep_while_loaded(hass: HomeAssistant, entry_id: str, seconds: float) -> bool:
    """Sleep in short slices so an unloaded integration leaves no orphan task."""
    remaining = max(0.0, float(seconds))
    while remaining > 0:
        if _runtime(hass, entry_id) is None:
            return False
        step = min(30.0, remaining)
        await asyncio.sleep(step)
        remaining -= step
    return _runtime(hass, entry_id) is not None


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
        _set_status(
            hass, entry.entry_id, state="disabled", complete=False, signature=signature
        )
        return False

    history = history_store.data.get("prices", {}).get(currency, {})
    if not isinstance(history, dict) or len(history) < 365:
        _set_status(
            hass,
            entry.entry_id,
            state="waiting_for_daily_history",
            complete=False,
            currency=currency,
            signature=signature,
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
        signature=signature,
        currency=currency,
        interval_minutes=BACKFILL_INTERVAL_MINUTES,
        retention_days=BACKFILL_DAYS,
        source="Bitstamp",
        network_route="Tor only",
        downloaded_points=0,
        error=None,
    )

    for page_index in range(BACKFILL_MAX_PAGES):
        if _runtime(hass, entry.entry_id) is None:
            return True
        page = await _fetch_bitstamp_5m_page(
            hass,
            currency=currency,
            proxy_url=proxy_url,
            end_timestamp=cursor,
        )
        page_stamps: list[datetime] = []
        for raw_stamp, raw_price in page.items():
            stamp = _utc_stamp(raw_stamp)
            if stamp is None:
                continue
            page_stamps.append(stamp)
            if stamp >= cutoff:
                candles[stamp.isoformat()] = float(raw_price)
        if not page_stamps:
            break
        oldest = min(page_stamps)
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
        if not await _sleep_while_loaded(
            hass, entry.entry_id, BACKFILL_NETWORK_PAUSE_SECONDS
        ):
            return True

    ordered = sorted(
        (
            (stamp, float(price))
            for raw_stamp, price in candles.items()
            for stamp in [_utc_stamp(raw_stamp)]
            if stamp is not None and cutoff <= stamp <= now
        ),
        key=lambda item: item[0],
    )
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
        signature=signature,
        source_points=total,
        completed_points=completed,
        remaining_points=len(missing),
    )
    if not missing:
        return True

    for offset in range(0, len(missing), BACKFILL_SCORE_BATCH_POINTS):
        if _runtime(hass, entry.entry_id) is None:
            return True
        latest_signature, latest_currency, _latest_scoring, _latest_settings = _current_generation(entry)
        if latest_signature != signature or latest_currency != currency:
            _set_status(
                hass,
                entry.entry_id,
                state="generation_changed",
                complete=False,
                signature=latest_signature,
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
        _set_status(
            hass,
            entry.entry_id,
            state="scoring",
            complete=False,
            signature=signature,
            completed_points=completed,
            remaining_points=max(0, total - completed),
        )
        if offset + BACKFILL_SCORE_BATCH_POINTS < len(missing):
            if not await _sleep_while_loaded(
                hass, entry.entry_id, BACKFILL_SCORE_PAUSE_SECONDS
            ):
                return True

    _set_status(
        hass,
        entry.entry_id,
        state="complete",
        complete=True,
        signature=signature,
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
    if not await _sleep_while_loaded(hass, entry.entry_id, BACKFILL_INITIAL_DELAY_SECONDS):
        return
    while _runtime(hass, entry.entry_id) is not None:
        try:
            if await _backfill_once(hass, entry, history_store, cache):
                return
            if not await _sleep_while_loaded(
                hass, entry.entry_id, BACKFILL_GENERATION_RETRY_SECONDS
            ):
                return
        except asyncio.CancelledError:
            raise
        except (ClientError, TimeoutError, ValueError, TypeError) as err:
            _LOGGER.warning("Market-assessment intraday backfill paused: %s", err)
            _set_status(
                hass,
                entry.entry_id,
                state="retry_wait",
                complete=False,
                error=str(err)[:240],
            )
            if not await _sleep_while_loaded(
                hass, entry.entry_id, BACKFILL_RETRY_SECONDS
            ):
                return
