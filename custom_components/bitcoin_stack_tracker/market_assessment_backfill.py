"""Startup-safe throttled 90-day five-minute market-assessment backfill.

The live assessment cache records actual observations as they happen. This
module reconstructs the recent public chart history from real five-minute OHLC
closes and the existing causal price-only model. Reconstructed points are marked
``backfilled``; a later live observation always wins for the same five-minute
bucket.

No portfolio, wallet, address, XPUB, descriptor or other private tracker data is
used or sent to an exchange. Public requests always go through the configured
Tor proxy and remain fail-closed. The worker is deliberately registered as a
Home Assistant background task so it cannot hold Core in the STARTING state.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from functools import partial
import logging
from typing import Any, Mapping
from urllib.parse import urljoin, urlparse

from aiohttp import ClientError, ClientResponseError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CoreState, HomeAssistant

from .buy_opportunity import calculate_buy_opportunity, normalize_buy_opportunity_settings
from .const import CONF_BUY_OPPORTUNITY_SETTINGS, CONF_HISTORY_ENABLED, DOMAIN
from .helpers import configured_currencies, effective_settings
from .http_limits import async_json_limited
from .market_assessment_intraday_cache import (
    MarketAssessmentIntradayCache,
    market_assessment_intraday_signature,
)
from .network import (
    TorConfigurationError,
    async_routed_session,
    async_tor_gateway_host,
    tor_proxy_from_settings,
)
from .storage import BitcoinHistoryStore

_LOGGER = logging.getLogger(__name__)

BACKFILL_DAYS = 90
BACKFILL_INTERVAL_MINUTES = 5
BACKFILL_PAGE_LIMIT = 1000
BACKFILL_MAX_PAGES = 40
BACKFILL_COINBASE_PAGE_LIMIT = 300
BACKFILL_COINBASE_MAX_PAGES = 100
BACKFILL_NETWORK_PAUSE_SECONDS = 1
# The full current model is intentionally replayed only two points at a time.
# At 20 s between batches the one-time fill takes days rather than creating a
# sustained CPU spike on smaller Home Assistant hosts.
BACKFILL_SCORE_BATCH_POINTS = 2
BACKFILL_SCORE_PAUSE_SECONDS = 20
BACKFILL_INITIAL_DELAY_SECONDS = 45
BACKFILL_GATEWAY_RETRY_SECONDS = 30
BACKFILL_RETRY_SECONDS = 5 * 60
BACKFILL_GENERATION_RETRY_SECONDS = 60
BITSTAMP_OHLC_HOSTS = {"bitstamp.net", "www.bitstamp.net"}
COINBASE_EXCHANGE_HOSTS = {"api.exchange.coinbase.com"}


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


def _validated_redirect(
    current_url: str,
    location: str | None,
    *,
    allowed_hosts: set[str],
    allowed_path_prefix: str,
    provider: str,
) -> str:
    if not location:
        raise ValueError(f"{provider} redirect did not include Location")
    candidate = urljoin(current_url, location)
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() != "https" or host not in allowed_hosts:
        raise ValueError(f"Blocked unsafe {provider} redirect to {host or 'unknown host'}")
    if not parsed.path.startswith(allowed_path_prefix):
        raise ValueError(f"Blocked {provider} redirect outside the market-data API")
    return candidate


async def _request_json_with_safe_redirects(
    hass: HomeAssistant,
    *,
    target_url: str,
    params: dict[str, Any],
    proxy_url: str,
    allowed_hosts: set[str],
    allowed_path_prefix: str,
    provider: str,
) -> Any:
    request_url = target_url
    request_params: dict[str, Any] | None = dict(params)
    async with async_routed_session(
        hass, target_url=target_url, proxy_url=proxy_url
    ) as (session, request_kwargs):
        async with asyncio.timeout(45):
            for _hop in range(3):
                response = await session.get(
                    request_url,
                    params=request_params,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "BitcoinStackTracker/0.21",
                    },
                    **request_kwargs,
                )
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    response.release()
                    request_url = _validated_redirect(
                        request_url,
                        location,
                        allowed_hosts=allowed_hosts,
                        allowed_path_prefix=allowed_path_prefix,
                        provider=provider,
                    )
                    request_params = None if urlparse(request_url).query else dict(params)
                    continue
                response.raise_for_status()
                return await async_json_limited(response)
    raise ValueError(f"Too many {provider} redirects")


async def _fetch_bitstamp_5m_page(
    hass: HomeAssistant,
    *,
    currency: str,
    proxy_url: str,
    end_timestamp: int,
) -> dict[str, float]:
    market = f"btc{currency.lower()}"
    target_url = f"https://www.bitstamp.net/api/v2/ohlc/{market}/"
    payload = await _request_json_with_safe_redirects(
        hass,
        target_url=target_url,
        params={
            "step": BACKFILL_INTERVAL_MINUTES * 60,
            "limit": BACKFILL_PAGE_LIMIT,
            "end": int(end_timestamp),
            "exclude_current_candle": "true",
        },
        proxy_url=proxy_url,
        allowed_hosts=BITSTAMP_OHLC_HOSTS,
        allowed_path_prefix="/api/v2/ohlc/",
        provider="Bitstamp",
    )
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


async def _fetch_coinbase_5m_page(
    hass: HomeAssistant,
    *,
    currency: str,
    proxy_url: str,
    start: datetime,
    end: datetime,
) -> dict[str, float]:
    product = f"BTC-{currency.upper()}"
    target_url = f"https://api.exchange.coinbase.com/products/{product}/candles"
    payload = await _request_json_with_safe_redirects(
        hass,
        target_url=target_url,
        params={
            "granularity": BACKFILL_INTERVAL_MINUTES * 60,
            "start": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "end": end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
        proxy_url=proxy_url,
        allowed_hosts=COINBASE_EXCHANGE_HOSTS,
        allowed_path_prefix=f"/products/{product}/candles",
        provider="Coinbase Exchange",
    )
    rows = payload if isinstance(payload, list) else []
    result: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, list) or len(row) < 5:
            continue
        stamp = _utc_stamp(row[0])
        try:
            price = float(row[4])
        except (TypeError, ValueError):
            continue
        if stamp is None or price <= 0:
            continue
        result[stamp.isoformat()] = price
    if not result:
        raise ValueError("Coinbase Exchange returned no usable five-minute candles")
    return result


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
    remaining = max(0.0, float(seconds))
    while remaining > 0:
        if _runtime(hass, entry_id) is None:
            return False
        step = min(15.0, remaining)
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


async def _download_bitstamp_90d(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    currency: str,
    proxy_url: str,
    now: datetime,
    cutoff: datetime,
) -> dict[str, float]:
    cursor = int(now.timestamp())
    candles: dict[str, float] = {}
    for page_index in range(BACKFILL_MAX_PAGES):
        if _runtime(hass, entry.entry_id) is None:
            return {}
        page = await _fetch_bitstamp_5m_page(
            hass,
            currency=currency,
            proxy_url=proxy_url,
            end_timestamp=cursor,
        )
        stamps: list[datetime] = []
        for raw_stamp, raw_price in page.items():
            stamp = _utc_stamp(raw_stamp)
            if stamp is None:
                continue
            stamps.append(stamp)
            if cutoff <= stamp <= now:
                candles[stamp.isoformat()] = float(raw_price)
        if not stamps:
            break
        oldest = min(stamps)
        _set_status(
            hass,
            entry.entry_id,
            source="Bitstamp",
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
            return {}
    if not candles:
        raise ValueError("Bitstamp returned no usable five-minute candles for backfill")
    return candles


async def _download_coinbase_90d(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    currency: str,
    proxy_url: str,
    now: datetime,
    cutoff: datetime,
) -> dict[str, float]:
    candles: dict[str, float] = {}
    cursor_end = now
    page_span = timedelta(
        seconds=BACKFILL_INTERVAL_MINUTES * 60 * BACKFILL_COINBASE_PAGE_LIMIT
    )
    for page_index in range(BACKFILL_COINBASE_MAX_PAGES):
        if _runtime(hass, entry.entry_id) is None:
            return {}
        if cursor_end <= cutoff:
            break
        cursor_start = max(cutoff, cursor_end - page_span)
        page = await _fetch_coinbase_5m_page(
            hass,
            currency=currency,
            proxy_url=proxy_url,
            start=cursor_start,
            end=cursor_end,
        )
        for raw_stamp, raw_price in page.items():
            stamp = _utc_stamp(raw_stamp)
            if stamp is not None and cutoff <= stamp <= now:
                candles[stamp.isoformat()] = float(raw_price)
        _set_status(
            hass,
            entry.entry_id,
            source="Coinbase Exchange",
            downloaded_points=len(candles),
            downloaded_pages=page_index + 1,
        )
        if cursor_start <= cutoff:
            break
        cursor_end = cursor_start - timedelta(seconds=1)
        if not await _sleep_while_loaded(
            hass, entry.entry_id, BACKFILL_NETWORK_PAUSE_SECONDS
        ):
            return {}
    if not candles:
        raise ValueError("Coinbase Exchange returned no usable five-minute candles for backfill")
    return candles


async def _download_90d_with_fallback(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    currency: str,
    proxy_url: str,
    now: datetime,
    cutoff: datetime,
) -> tuple[dict[str, float], str]:
    try:
        candles = await _download_bitstamp_90d(
            hass,
            entry,
            currency=currency,
            proxy_url=proxy_url,
            now=now,
            cutoff=cutoff,
        )
        return candles, "Bitstamp 5m OHLC via Tor"
    except asyncio.CancelledError:
        raise
    except (ClientError, TimeoutError, ValueError, TypeError) as err:
        # Bitstamp currently returns HTTP 403 for some Tor exits. This is a
        # provider refusal, not a reason to weaken the Tor-only policy. Fall
        # through to another public exchange over the exact same Tor route.
        status = getattr(err, "status", None)
        _LOGGER.warning(
            "Bitstamp 5m backfill unavailable%s; trying Coinbase Exchange through Tor: %s",
            f" (HTTP {status})" if status else "",
            err,
        )
        _set_status(
            hass,
            entry.entry_id,
            state="provider_fallback",
            complete=False,
            source="Bitstamp -> Coinbase Exchange",
            provider_error=f"{type(err).__name__}: {err}"[:240],
            downloaded_points=0,
            downloaded_pages=0,
        )

    candles = await _download_coinbase_90d(
        hass,
        entry,
        currency=currency,
        proxy_url=proxy_url,
        now=now,
        cutoff=cutoff,
    )
    return candles, "Coinbase Exchange 5m candles via Tor"


def _score_batch(
    history: Mapping[str, Any],
    rows: list[tuple[datetime, float]],
    *,
    currency: str,
    settings: Mapping[str, Any],
    source: str,
) -> list[dict[str, Any]]:
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
                "source": source,
                "backfilled": True,
            }
        )
    return points


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
        downloaded_pages=0,
        provider_error=None,
        error=None,
    )

    candles, source = await _download_90d_with_fallback(
        hass,
        entry,
        currency=currency,
        proxy_url=proxy_url,
        now=now,
        cutoff=cutoff,
    )
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
        raise ValueError("No usable five-minute candles were returned by any Tor provider")

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
        source=source,
        source_points=total,
        completed_points=completed,
        remaining_points=len(missing),
        error=None,
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
                source=source,
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
            source=source,
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
        source=source,
        completed_points=total,
        remaining_points=0,
    )
    return True


async def _background_worker(
    hass: HomeAssistant,
    entry: ConfigEntry,
    history_store: BitcoinHistoryStore,
    cache: MarketAssessmentIntradayCache,
) -> None:
    # Application-stage add-ons such as the bundled Tor Gateway may not be
    # available while Core is still STARTING. Waiting here is safe because this
    # coroutine is registered in Home Assistant's background-task bucket.
    while _runtime(hass, entry.entry_id) is not None and hass.state is not CoreState.running:
        _set_status(
            hass,
            entry.entry_id,
            state="waiting_for_home_assistant",
            complete=False,
            error=None,
        )
        if not await _sleep_while_loaded(hass, entry.entry_id, 2):
            return

    if not await _sleep_while_loaded(hass, entry.entry_id, BACKFILL_INITIAL_DELAY_SECONDS):
        return

    while _runtime(hass, entry.entry_id) is not None:
        try:
            try:
                gateway_host = await async_tor_gateway_host()
            except TorConfigurationError as err:
                _set_status(
                    hass,
                    entry.entry_id,
                    state="waiting_for_tor_gateway",
                    complete=False,
                    error=str(err)[:240],
                    retry_in_seconds=BACKFILL_GATEWAY_RETRY_SECONDS,
                    next_retry_at=(
                        datetime.now(timezone.utc)
                        + timedelta(seconds=BACKFILL_GATEWAY_RETRY_SECONDS)
                    ).isoformat(),
                )
                if not await _sleep_while_loaded(
                    hass, entry.entry_id, BACKFILL_GATEWAY_RETRY_SECONDS
                ):
                    return
                continue

            _set_status(
                hass,
                entry.entry_id,
                gateway_host=gateway_host,
                error=None,
                retry_in_seconds=0,
                next_retry_at=None,
            )
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
                error=f"{type(err).__name__}: {err}"[:240],
                retry_in_seconds=BACKFILL_RETRY_SECONDS,
                next_retry_at=(
                    datetime.now(timezone.utc) + timedelta(seconds=BACKFILL_RETRY_SECONDS)
                ).isoformat(),
            )
            if not await _sleep_while_loaded(
                hass, entry.entry_id, BACKFILL_RETRY_SECONDS
            ):
                return


async def async_market_assessment_backfill_loop(
    hass: HomeAssistant,
    entry: ConfigEntry,
    history_store: BitcoinHistoryStore,
    cache: MarketAssessmentIntradayCache,
) -> None:
    """Detach the long-running reconstruction from Home Assistant startup.

    ``async_setup_entry`` currently invokes this coroutine through
    ``hass.async_create_task``. A normal task is part of Home Assistant's startup
    wait set. Therefore this thin wrapper immediately moves the real long-lived
    work into ``async_create_background_task`` and returns. Background tasks do
    not block startup and are automatically cancelled on Core shutdown.
    """
    runtime = _runtime(hass, entry.entry_id)
    if runtime is None:
        return
    existing = runtime.get("_market_assessment_backfill_worker_task")
    if existing is not None and not existing.done():
        return
    task = hass.async_create_background_task(
        _background_worker(hass, entry, history_store, cache),
        "Bitcoin Stack Tracker 90-day market assessment background worker",
    )
    runtime["_market_assessment_backfill_worker_task"] = task
