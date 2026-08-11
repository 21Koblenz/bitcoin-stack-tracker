"""Daily historical Bitcoin price download and Home Assistant statistics import."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
from datetime import date, datetime, time, timedelta, timezone
import logging
from bisect import bisect_right
from functools import partial
from math import isfinite
from typing import Any
from urllib.parse import urljoin, urlparse

from aiohttp import ClientError

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    valid_statistic_id,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    ALL_DEPOTS,
    CONF_BASE_URL,
    CONF_CURRENCIES,
    CONF_HISTORY_DAYS,
    CONF_HISTORY_ENABLED,
    CONF_SOURCE_TYPE,
    CONF_SOURCES,
    CONF_VERIFY_SSL,
    DEFAULT_HISTORY_DAYS,
    DOMAIN,
    KRAKEN_CURRENCIES,
    SOURCE_KRAKEN,
    SOURCE_MEMPOOL,
)
from .fifo import currency_summary_from_result, fifo_result
from .helpers import configured_currencies, effective_settings
from .http_limits import (
    MAX_BULK_RESPONSE_BYTES,
    MAX_ERROR_RESPONSE_BYTES,
    async_json_limited,
    async_read_limited,
    async_text_limited,
)
from .models import decimal_value, external_statistic_id
from .network import (
    async_routed_session,
    mempool_source_uses_tor,
    tor_proxy_from_settings,
)
from .limits import MAX_HISTORY_CURRENCIES
from .storage import BitcoinHistoryStore, BitcoinLedgerStore

_LOGGER = logging.getLogger(__name__)

# Bump this marker whenever the long-history composition strategy changes.  It
# intentionally causes one full backfill after an upgrade so installations
# that were previously marked complete (for example an own mempool history
# beginning in 2013) can discover older data from the Tor-routed fallbacks.
HISTORY_STRATEGY_VERSION = "ordered-source-cascade-v9-dense-gap-fill"
ALL_TIME_PRICE_START_DAY = "2010-07-01"
LONG_HISTORY_REQUIRED_BEFORE_DAY = "2010-09-01"
FULL_HISTORY_MIN_DENSITY = 0.95
FULL_HISTORY_MAX_GAP_DAYS = 7
FULL_HISTORY_MAX_RECENT_LAG_DAYS = 7

# The exchange cache can retain several resolutions, but each chart request uses
# one uniform OHLC interval from left to right.  Choose the smallest supported
# interval that can cover the requested window without exceeding the provider's
# useful REST result limit. Kraken supplies up to 720 recent OHLC rows; Bitstamp
# is used for the native 2h and 12h tiers and can cover a full year at 12h.
KRAKEN_OHLC_INTERVALS = (5, 15, 30, 60, 240, 1440)
BITSTAMP_OHLC_STEPS = {120: 7200, 720: 43200}
MARKET_OHLC_TIERS = (5, 15, 30, 60, 120, 240, 720, 1440)
KRAKEN_OHLC_LIMIT = 720
BITSTAMP_OHLC_LIMIT = 1000
BITSTAMP_OHLC_HOSTS = {"bitstamp.net", "www.bitstamp.net"}
ECB_BULK_HISTORY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"


def _market_ohlc_interval_for_days(history_days: int) -> int:
    """Return one uniform, finest practical OHLC interval for a time window."""
    days = max(1, int(history_days or 1))
    capacities = (
        (5, KRAKEN_OHLC_LIMIT),
        (15, KRAKEN_OHLC_LIMIT),
        (30, KRAKEN_OHLC_LIMIT),
        (60, KRAKEN_OHLC_LIMIT),
        (120, BITSTAMP_OHLC_LIMIT),
        (240, KRAKEN_OHLC_LIMIT),
        (720, BITSTAMP_OHLC_LIMIT),
        (1440, KRAKEN_OHLC_LIMIT),
    )
    minutes = days * 24 * 60
    for interval, limit in capacities:
        if minutes / interval <= limit:
            return interval
    return 1440


def market_ohlc_interval_for_days(history_days: int) -> int:
    """Public helper shared with the native dashboard request path."""
    return _market_ohlc_interval_for_days(history_days)


def _market_ohlc_tiers_for_days(history_days: int) -> tuple[int, ...]:
    """Compatibility wrapper: requests now deliberately contain one tier only."""
    return (_market_ohlc_interval_for_days(history_days),)


def _is_full_market_history(values: dict[str, float]) -> bool:
    """Return whether an all-time cache is genuinely dense daily history.

    Reaching 2010 with a few sampled observations is not enough. Some chart
    providers may return a performance-sampled all-time response (~1.5k points),
    which spans the full date range but leaves most calendar days missing. A
    completed bootstrap therefore requires an early start, recent coverage, high
    calendar-day density, and no large internal gaps.
    """
    if len(values) <= 720:
        return False
    try:
        days = sorted(date.fromisoformat(day) for day in values)
    except (TypeError, ValueError):
        return False
    if not days or days[0].isoformat() >= LONG_HISTORY_REQUIRED_BEFORE_DAY:
        return False
    today = datetime.now(timezone.utc).date()
    if days[-1] < today - timedelta(days=FULL_HISTORY_MAX_RECENT_LAG_DAYS):
        return False
    span_days = (days[-1] - days[0]).days + 1
    if span_days <= 0 or len(days) / span_days < FULL_HISTORY_MIN_DENSITY:
        return False
    return all(
        (current - previous).days <= FULL_HISTORY_MAX_GAP_DAYS
        for previous, current in zip(days, days[1:])
    )


def _timestamp_value(timestamp: Any) -> float | None:
    try:
        numeric = float(timestamp)
        if numeric > 10_000_000_000:
            numeric /= 1000
        return numeric
    except (TypeError, ValueError):
        if isinstance(timestamp, str):
            try:
                parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.timestamp()
            except ValueError:
                pass
    return None


def _day_key(timestamp: Any) -> str | None:
    """Return the UTC calendar day for any supported timestamp representation."""
    try:
        numeric = _timestamp_value(timestamp)
        if numeric is None:
            return None
        return datetime.fromtimestamp(numeric, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _parse_mempool_payload(payload: Any, currency: str) -> dict[str, float]:
    currency = currency.upper()
    rows: list[Any]
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        candidate = payload.get("prices", payload.get("data", payload.get("history", [])))
        if isinstance(candidate, dict):
            rows = [
                dict(value, timestamp=key)
                if isinstance(value, dict)
                else {"timestamp": key, "price": value}
                for key, value in candidate.items()
            ]
        elif isinstance(candidate, list):
            rows = candidate
        else:
            rows = []
    else:
        rows = []

    result: dict[str, tuple[float, float]] = {}
    for row in rows:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            timestamp, raw_price = row[0], row[1]
        elif isinstance(row, dict):
            timestamp = row.get("time", row.get("timestamp", row.get("date", row.get("t"))))
            raw_price = row.get(currency, row.get(currency.lower(), row.get("price", row.get("value"))))
        else:
            continue
        day = _day_key(timestamp)
        try:
            price = float(raw_price)
            numeric_ts = _timestamp_value(timestamp) or 0.0
        except (TypeError, ValueError):
            continue
        if day and isfinite(price) and price > 0:
            previous = result.get(day)
            if previous is None or numeric_ts >= previous[0]:
                result[day] = (numeric_ts, price)
    return {day: value[1] for day, value in result.items()}


async def _fetch_mempool_history(
    hass: HomeAssistant,
    settings: dict[str, Any],
    source: dict[str, Any],
    currency: str,
) -> dict[str, float]:
    """Fetch history only from the configured mempool base URL."""
    base_url = str(source[CONF_BASE_URL]).rstrip("/")
    verify_ssl = bool(source.get(CONF_VERIFY_SSL, True))
    proxy_url = (
        tor_proxy_from_settings(settings)
        if mempool_source_uses_tor(source)
        else None
    )
    target_url = f"{base_url}/api/v1/historical-price"
    async with async_routed_session(
        hass,
        target_url=target_url,
        proxy_url=proxy_url,
        allow_local_direct=not mempool_source_uses_tor(source),
        verify_ssl=verify_ssl,
    ) as (session, request_kwargs):
        async with asyncio.timeout(60):
            response = await session.get(
                target_url,
                params={"currency": currency.upper()},
                **request_kwargs,
            )
            response.raise_for_status()
            payload = await async_json_limited(response)
    values = _parse_mempool_payload(payload, currency)
    if not values:
        raise ValueError("mempool historical-price returned no usable daily values")
    return values


async def _fetch_kraken_history(
    hass: HomeAssistant, currency: str, proxy_url: str
) -> dict[str, float]:
    """Fetch Kraken daily OHLC closes. Kraken limits this endpoint to 720 rows."""
    if currency.upper() not in KRAKEN_CURRENCIES:
        raise ValueError(f"Kraken does not support XBT{currency.upper()} in this integration")
    target_url = "https://api.kraken.com/0/public/OHLC"
    async with async_routed_session(
        hass, target_url=target_url, proxy_url=proxy_url
    ) as (session, request_kwargs):
        async with asyncio.timeout(30):
            response = await session.get(
                target_url,
                params={"pair": f"XBT{currency.upper()}", "interval": 1440},
                **request_kwargs,
            )
            response.raise_for_status()
            payload = await async_json_limited(response)
    if payload.get("error"):
        raise ValueError(", ".join(payload["error"]))
    result = payload.get("result") or {}
    rows = next((value for key, value in result.items() if key != "last"), [])
    values: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, list) or len(row) < 5:
            continue
        day = _day_key(row[0])
        price = float(row[4])
        if day and isfinite(price) and price > 0:
            values[day] = price
    if not values:
        raise ValueError("Kraken returned no daily OHLC values")
    return values


async def _fetch_kraken_ohlc_samples(
    hass: HomeAssistant, currency: str, proxy_url: str, interval: int
) -> dict[str, float]:
    """Fetch one Kraken OHLC tier through Tor and return candle closes."""
    if currency.upper() not in KRAKEN_CURRENCIES:
        return {}
    if int(interval) not in KRAKEN_OHLC_INTERVALS:
        raise ValueError(f"Unsupported Kraken OHLC interval: {interval}")
    target_url = "https://api.kraken.com/0/public/OHLC"
    async with async_routed_session(
        hass, target_url=target_url, proxy_url=proxy_url
    ) as (session, request_kwargs):
        async with asyncio.timeout(30):
            response = await session.get(
                target_url,
                params={"pair": f"XBT{currency.upper()}", "interval": int(interval)},
                **request_kwargs,
            )
            response.raise_for_status()
            payload = await async_json_limited(response)
    if payload.get("error"):
        raise ValueError(", ".join(payload["error"]))
    result = payload.get("result") or {}
    rows = next((value for key, value in result.items() if key != "last"), [])
    values: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, list) or len(row) < 5:
            continue
        numeric = _timestamp_value(row[0])
        try:
            price = float(row[4])
        except (TypeError, ValueError):
            continue
        if numeric is None or not isfinite(price) or price <= 0:
            continue
        key = datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        values[key] = price
    if not values:
        raise ValueError(f"Kraken returned no {interval}-minute OHLC values")
    return values


def _validated_bitstamp_ohlc_redirect(current_url: str, location: str | None) -> str:
    """Allow only an HTTPS redirect that stays on Bitstamp's OHLC API."""
    if not location:
        raise ValueError("Bitstamp OHLC redirect did not include a Location header")
    candidate = urljoin(current_url, location)
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() != "https" or host not in BITSTAMP_OHLC_HOSTS:
        raise ValueError(f"Blocked unsafe Bitstamp OHLC redirect to {host or 'unknown host'}")
    if not parsed.path.startswith("/api/v2/ohlc/"):
        raise ValueError("Blocked Bitstamp redirect outside the OHLC API")
    return candidate


async def _fetch_bitstamp_ohlc_samples(
    hass: HomeAssistant, currency: str, proxy_url: str, interval: int
) -> dict[str, float]:
    """Fetch one Bitstamp OHLC tier through Tor with a strict same-provider redirect."""
    step = BITSTAMP_OHLC_STEPS.get(int(interval))
    if step is None:
        raise ValueError(f"Unsupported Bitstamp OHLC interval: {interval}")
    market = f"btc{currency.lower()}"
    target_url = f"https://www.bitstamp.net/api/v2/ohlc/{market}/"
    request_url = target_url
    params: dict[str, Any] | None = {
        "step": step,
        "limit": BITSTAMP_OHLC_LIMIT,
        "exclude_current_candle": "false",
    }
    payload: Any = None
    async with async_routed_session(
        hass, target_url=target_url, proxy_url=proxy_url
    ) as (session, request_kwargs):
        async with asyncio.timeout(45):
            for _redirect_hop in range(3):
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
                    request_url = _validated_bitstamp_ohlc_redirect(request_url, location)
                    # Preserve the original query if the redirect only changes host/path.
                    # If Bitstamp supplied its own query string, do not duplicate it.
                    params = None if urlparse(request_url).query else {
                        "step": step,
                        "limit": BITSTAMP_OHLC_LIMIT,
                        "exclude_current_candle": "false",
                    }
                    continue
                response.raise_for_status()
                content_type = str(response.headers.get("Content-Type") or "").lower()
                if "json" not in content_type:
                    body = (await async_text_limited(response, max_bytes=MAX_ERROR_RESPONSE_BYTES))[:180].replace("\n", " ")
                    raise ValueError(
                        f"Bitstamp OHLC returned non-JSON content ({content_type or 'unknown'}): {body}"
                    )
                payload = await async_json_limited(response)
                break
            else:
                raise ValueError("Bitstamp OHLC exceeded the safe redirect limit")
    rows = ((payload.get("data") or {}).get("ohlc") or []) if isinstance(payload, dict) else []
    values: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        numeric = _timestamp_value(row.get("timestamp"))
        try:
            price = float(row.get("close"))
        except (TypeError, ValueError):
            continue
        if numeric is None or not isfinite(price) or price <= 0:
            continue
        key = datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        values[key] = price
    if not values:
        raise ValueError(f"Bitstamp returned no {interval}-minute OHLC values")
    return values


async def _fetch_kraken_intraday_samples(
    hass: HomeAssistant, currency: str, proxy_url: str, history_days: int = 366
) -> tuple[dict[str, float], dict[int, int]]:
    """Fetch one uniform exchange candle interval selected for the requested range."""
    merged: dict[str, float] = {}
    counts: dict[int, int] = {}
    errors: list[str] = []
    tiers = _market_ohlc_tiers_for_days(history_days)
    for index, interval in enumerate(tiers):
        provider = "Bitstamp" if interval in BITSTAMP_OHLC_STEPS else "Kraken"
        try:
            if provider == "Bitstamp":
                tier = await _fetch_bitstamp_ohlc_samples(hass, currency, proxy_url, interval)
            else:
                tier = await _fetch_kraken_ohlc_samples(hass, currency, proxy_url, interval)
            counts[interval] = len(tier)
            for timestamp, price in tier.items():
                merged.setdefault(timestamp, price)
        except (ClientError, asyncio.TimeoutError, ValueError) as err:
            errors.append(f"{provider} {interval}m: {err}")
        # Kraken's current support guidance keeps public REST requests at or below
        # roughly one per second. Bitstamp permits much higher public limits.
        if provider == "Kraken" and index + 1 < len(tiers):
            await asyncio.sleep(1.05)
    if not merged:
        detail = "; ".join(errors) or "no OHLC tier returned data"
        raise ValueError(f"Uniform exchange OHLC unavailable: {detail}")
    return merged, counts


async def _fetch_exact_market_candles(
    hass: HomeAssistant, currency: str, proxy_url: str, interval: int
) -> tuple[dict[str, float], str]:
    """Fetch exactly one provider-native interval for a uniform chart."""
    interval = int(interval)
    if interval in BITSTAMP_OHLC_STEPS:
        return await _fetch_bitstamp_ohlc_samples(hass, currency, proxy_url, interval), "Bitstamp"
    if interval in KRAKEN_OHLC_INTERVALS:
        return await _fetch_kraken_ohlc_samples(hass, currency, proxy_url, interval), "Kraken"
    raise ValueError(f"Unsupported market OHLC interval: {interval}")


async def _request_json_with_backoff(
    hass: HomeAssistant,
    url: str,
    *,
    params: dict[str, Any],
    proxy_url: str,
    timeout_seconds: int = 90,
) -> Any:
    """Fetch public historical data with conservative 429 retry handling."""
    last_error: Exception | None = None
    async with async_routed_session(
        hass, target_url=url, proxy_url=proxy_url
    ) as (session, request_kwargs):
        for attempt in range(3):
            try:
                async with asyncio.timeout(timeout_seconds):
                    response = await session.get(
                        url,
                        params=params,
                        headers={"Accept": "application/json", "User-Agent": "BitcoinStackTracker/0.6"},
                        **request_kwargs,
                    )
                    if response.status == 429:
                        retry_after = min(int(response.headers.get("Retry-After", "2") or 2), 15)
                        response.release()
                        await asyncio.sleep(retry_after * (attempt + 1))
                        continue
                    response.raise_for_status()
                    return await async_json_limited(response)
            except (ClientError, asyncio.TimeoutError, ValueError) as err:
                last_error = err
                if attempt < 2:
                    await asyncio.sleep(2**attempt)
    raise ValueError(f"historical source request failed: {last_error}")


def _parse_timestamp_price_rows(rows: Any) -> dict[str, float]:
    """Reduce timestamp/value rows to one latest positive value per UTC day."""
    result: dict[str, tuple[float, float]] = {}
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        numeric = _timestamp_value(row[0])
        day = _day_key(row[0])
        try:
            price = float(row[1])
        except (TypeError, ValueError):
            continue
        if day and numeric is not None and isfinite(price) and price > 0:
            previous = result.get(day)
            if previous is None or numeric >= previous[0]:
                result[day] = (numeric, price)
    return {day: item[1] for day, item in result.items()}


async def _fetch_coingecko_history(
    hass: HomeAssistant,
    currency: str,
    *,
    proxy_url: str,
    start_day: str | None = None,
    end_day: str | None = None,
) -> dict[str, float]:
    """Fetch CoinGecko public daily market-chart values for an explicit range."""
    code = currency.lower()
    if start_day or end_day:
        start = datetime.combine(date.fromisoformat(start_day or ALL_TIME_PRICE_START_DAY), time.min, tzinfo=timezone.utc)
        end = datetime.combine(date.fromisoformat(end_day) if end_day else dt_util.utcnow().date(), time.max, tzinfo=timezone.utc)
        payload = await _request_json_with_backoff(
            hass,
            "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart/range",
            params={
                "vs_currency": code,
                "from": int(start.timestamp()),
                "to": int(end.timestamp()),
                "precision": "full",
            },
            proxy_url=proxy_url,
        )
    else:
        payload = await _request_json_with_backoff(
            hass,
            "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
            params={"vs_currency": code, "days": "max", "precision": "full"},
            proxy_url=proxy_url,
        )
    values = _parse_timestamp_price_rows(payload.get("prices", []) if isinstance(payload, dict) else [])
    if not values:
        raise ValueError("CoinGecko returned no usable Bitcoin price history")
    return values


async def _fetch_blockchain_usd_history(
    hass: HomeAssistant, *, proxy_url: str, start_day: str | None = None, end_day: str | None = None
) -> dict[str, float]:
    """Fetch Blockchain.com's all-time or incremental daily BTC/USD chart."""
    params: dict[str, Any] = {
        "format": "json",
        "sampled": "false",
    }
    # Use an explicit start and duration even for a full bootstrap.  This avoids
    # provider/default-window changes silently truncating Max history to 2013+.
    effective_start = start_day or ALL_TIME_PRICE_START_DAY
    params["start"] = effective_start
    effective_end = date.fromisoformat(end_day) if end_day else dt_util.utcnow().date()
    days = max((effective_end - date.fromisoformat(effective_start)).days + 1, 1)
    params["timespan"] = f"{days}days"
    payload = await _request_json_with_backoff(
        hass,
        "https://api.blockchain.info/charts/market-price",
        params=params,
        proxy_url=proxy_url,
        timeout_seconds=120,
    )
    rows = []
    if isinstance(payload, dict):
        rows = [[item.get("x"), item.get("y")] for item in payload.get("values", []) if isinstance(item, dict)]
    values = _parse_timestamp_price_rows(rows)
    if not values:
        raise ValueError("Blockchain.com returned no usable BTC/USD history")
    return values


async def _fetch_coinmetrics_usd_history(
    hass: HomeAssistant, *, proxy_url: str, start_day: str | None = None, end_day: str | None = None
) -> dict[str, float]:
    """Fetch Coin Metrics community daily BTC/USD reference history."""
    params: dict[str, Any] = {
        "assets": "btc",
        "metrics": "PriceUSD",
        "frequency": "1d",
        "paging_from": "start",
        "page_size": 10000,
        # Do not rely on the provider's default time window.  The Max chart
        # explicitly needs the oldest available market history.
        "start_time": start_day or ALL_TIME_PRICE_START_DAY,
    }
    if end_day:
        params["end_time"] = end_day
    payload = await _request_json_with_backoff(
        hass,
        "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics",
        params=params,
        proxy_url=proxy_url,
        timeout_seconds=120,
    )
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    values: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        day = _day_key(row.get("time"))
        try:
            price = float(row.get("PriceUSD"))
        except (TypeError, ValueError):
            continue
        if day and isfinite(price) and price > 0:
            values[day] = price
    if not values:
        raise ValueError("Coin Metrics returned no usable BTC/USD history")
    return values


def _parse_ecb_sdmx_csv(
    text: str, codes: set[str]
) -> dict[str, dict[str, float]]:
    """Parse ECB Data Portal SDMX CSV rows into currency-per-EUR daily rates."""
    wanted = {str(code).upper() for code in codes if str(code).upper() != "EUR"}
    result: dict[str, dict[str, float]] = {code: {} for code in wanted}
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    for row in reader:
        code = str(row.get("CURRENCY") or row.get("currency") or "").strip().upper()
        day = str(row.get("TIME_PERIOD") or row.get("time_period") or "").strip()[:10]
        raw = row.get("OBS_VALUE") or row.get("obs_value")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if code in result and len(day) == 10 and value > 0 and isfinite(value):
            result[code][day] = value
    return result


def _parse_ecb_bulk_zip(
    payload: bytes,
    codes: set[str],
    start_day: str | None,
    end_day: str | None,
) -> dict[str, dict[str, float]]:
    """Parse the ECB's official full historical eurofxref CSV ZIP."""
    import zipfile

    wanted = {str(code).upper() for code in codes if str(code).upper() != "EUR"}
    result: dict[str, dict[str, float]] = {code: {} for code in wanted}
    start = date.fromisoformat(start_day) if start_day else None
    end = date.fromisoformat(end_day) if end_day else None
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if not csv_names:
                raise ValueError("ECB historical ZIP contains no CSV file")
            with archive.open(csv_names[0], "r") as handle:
                text = handle.read().decode("utf-8-sig", errors="replace")
    except zipfile.BadZipFile as err:
        raise ValueError("ECB historical download was not a valid ZIP archive") from err
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        raw_day = str(row.get("Date") or row.get("DATE") or "").strip()[:10]
        try:
            day_obj = date.fromisoformat(raw_day)
        except ValueError:
            continue
        if start is not None and day_obj < start:
            continue
        if end is not None and day_obj > end:
            continue
        for code in wanted:
            raw = row.get(code)
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if value > 0 and isfinite(value):
                result[code][raw_day] = value
    return result


def _fx_range_coverage_ok(
    rates: dict[str, dict[str, float]],
    *,
    start_day: str | None,
    end_day: str | None,
) -> bool:
    """Require the returned USD reference series to actually span the requested range."""
    usd = rates.get("USD", {})
    if not usd:
        return False
    try:
        first = date.fromisoformat(min(usd))
        last = date.fromisoformat(max(usd))
    except (ValueError, TypeError):
        return False
    if start_day:
        # ECB publishes on working days only, so tolerate weekends/holidays.
        if first > date.fromisoformat(start_day) + timedelta(days=7):
            return False
    if end_day:
        if last < date.fromisoformat(end_day) - timedelta(days=7):
            return False
    return True


async def _fetch_ecb_bulk_rates(
    hass: HomeAssistant,
    currencies: set[str],
    *,
    proxy_url: str,
    start_day: str | None = None,
    end_day: str | None = None,
) -> dict[str, dict[str, float]]:
    """Fetch ECB full historical reference-rate ZIP through Tor and filter locally."""
    codes = {code.upper() for code in currencies if code.upper() != "EUR"} | {"USD"}
    async with async_routed_session(
        hass, target_url=ECB_BULK_HISTORY_URL, proxy_url=proxy_url
    ) as (session, request_kwargs):
        async with asyncio.timeout(120):
            response = await session.get(
                ECB_BULK_HISTORY_URL,
                headers={"Accept": "application/zip", "User-Agent": "BitcoinStackTracker/0.6"},
                **request_kwargs,
            )
            response.raise_for_status()
            payload = await async_read_limited(response, max_bytes=MAX_BULK_RESPONSE_BYTES)
    result = await hass.async_add_executor_job(
        _parse_ecb_bulk_zip, payload, codes, start_day, end_day
    )
    if not _fx_range_coverage_ok(result, start_day=start_day, end_day=end_day):
        raise ValueError("ECB historical ZIP did not cover the requested USD/EUR range")
    return result


async def _fetch_ecb_rates(
    hass: HomeAssistant,
    currencies: set[str],
    *,
    proxy_url: str,
    start_day: str | None = None,
    end_day: str | None = None,
) -> dict[str, dict[str, float]]:
    """Fetch official ECB daily reference rates expressed as currency per EUR.

    Long-range conversions prefer the ECB's official bulk history ZIP.  The Data
    Portal range API remains the lighter path for short windows.  This prevents
    a provider/API truncation from silently leaving BTC/EUR stuck at 2013 while
    a complete BTC/USD cache already exists locally.
    """
    codes = {code.upper() for code in currencies if code.upper() != "EUR"} | {"USD"}
    if not codes:
        return {"EUR": {}}

    long_range = False
    if start_day and end_day:
        try:
            long_range = (date.fromisoformat(end_day) - date.fromisoformat(start_day)).days > 370
        except ValueError:
            long_range = False
    if long_range:
        return await _fetch_ecb_bulk_rates(
            hass, codes, proxy_url=proxy_url, start_day=start_day, end_day=end_day
        )

    url = f"https://data-api.ecb.europa.eu/service/data/EXR/D.{'+'.join(sorted(codes))}.EUR.SP00.A"
    params = {"format": "csvdata"}
    if start_day:
        params["startPeriod"] = start_day
    if end_day:
        params["endPeriod"] = end_day
    try:
        async with async_routed_session(
            hass, target_url=url, proxy_url=proxy_url
        ) as (session, request_kwargs):
            async with asyncio.timeout(120):
                response = await session.get(
                    url,
                    params=params,
                    headers={"Accept": "text/csv", "User-Agent": "BitcoinStackTracker/0.6"},
                    **request_kwargs,
                )
                response.raise_for_status()
                text = await async_text_limited(response)
        result = _parse_ecb_sdmx_csv(text, codes)
        if _fx_range_coverage_ok(result, start_day=start_day, end_day=end_day):
            return result
    except (ClientError, asyncio.TimeoutError, ValueError):
        pass

    # Fail over to a second official ECB representation, still through Tor.
    return await _fetch_ecb_bulk_rates(
        hass, codes, proxy_url=proxy_url, start_day=start_day, end_day=end_day
    )


def _last_rate_on_or_before(
    day: str, rate_days: list[str], rates: dict[str, float]
) -> float | None:
    """Return the latest working-day FX rate at or before one BTC price day."""
    index = bisect_right(rate_days, day) - 1
    if index < 0:
        return None
    try:
        value = float(rates[rate_days[index]])
    except (KeyError, TypeError, ValueError):
        return None
    return value if value > 0 and isfinite(value) else None


def _convert_usd_history(
    usd_prices: dict[str, float],
    currency: str,
    rates: dict[str, dict[str, float]],
) -> dict[str, float]:
    """Convert BTC/USD with the latest ECB working-day rate on/before each BTC day."""
    code = currency.upper()
    if code == "USD":
        return dict(usd_prices)
    usd_rates = rates.get("USD", {})
    target_rates = {} if code == "EUR" else rates.get(code, {})
    usd_days = sorted(usd_rates)
    target_days = sorted(target_rates)
    result: dict[str, float] = {}
    for day, btc_usd in sorted(usd_prices.items()):
        usd_per_eur = _last_rate_on_or_before(day, usd_days, usd_rates)
        target_per_eur = (
            1.0
            if code == "EUR"
            else _last_rate_on_or_before(day, target_days, target_rates)
        )
        if usd_per_eur and target_per_eur and usd_per_eur > 0 and target_per_eur > 0:
            value = float(btc_usd) * target_per_eur / usd_per_eur
            if value > 0 and isfinite(value):
                result[day] = value
    return result


def _older_gap_end(values: dict[str, float], today: date) -> str:
    """Return the last day a backwards source may contribute."""
    if values:
        return (date.fromisoformat(min(values)) - timedelta(days=1)).isoformat()
    return (today - timedelta(days=1)).isoformat()


def _merge_older_prefix(
    values: dict[str, float], candidate: dict[str, float]
) -> dict[str, float]:
    """Merge only observations older than the current left edge."""
    boundary = min(values) if values else None
    added = {
        day: float(price)
        for day, price in candidate.items()
        if (boundary is None or day < boundary) and float(price) > 0
    }
    values.update(added)
    return added


def _fill_missing_days(
    values: dict[str, float], candidate: dict[str, float]
) -> dict[str, float]:
    """Fill missing calendar days without overwriting the preferred source."""
    added = {
        day: float(price)
        for day, price in candidate.items()
        if day not in values and float(price) > 0
    }
    values.update(added)
    return added


def _history_source_record(
    name: str, values: dict[str, float], *, route: str, role: str
) -> dict[str, Any] | None:
    """Build compact persisted provenance for a source contribution."""
    if not values:
        return None
    return {
        "source": name,
        "first_day": min(values),
        "last_day": max(values),
        "points": len(values),
        "route": route,
        "role": role,
    }


def _statistic_id(
    entry_id: str,
    metric: str,
    currency: str | None = None,
    suffix: str | None = None,
) -> str:
    # New Home Assistant config-entry ULIDs are uppercase. External statistic
    # IDs must be lowercase, so every component is normalized centrally.
    return external_statistic_id(DOMAIN, entry_id, metric, currency, suffix)


def _import_measurement(
    hass: HomeAssistant,
    *,
    statistic_id: str,
    name: str,
    unit: str | None,
    values: dict[str, float],
) -> None:
    """Queue one complete external daily statistic series in Recorder."""
    if not valid_statistic_id(statistic_id):
        raise ValueError(
            f"Generated invalid Home Assistant statistic_id: {statistic_id!r}"
        )
    metadata: StatisticMetaData = {
        "source": DOMAIN,
        "statistic_id": statistic_id,
        "name": name,
        "unit_of_measurement": unit,
        "unit_class": None,
        "mean_type": StatisticMeanType.ARITHMETIC,
        "has_sum": False,
    }
    statistics: list[StatisticData] = []
    for day, value in sorted(values.items()):
        start = datetime.combine(date.fromisoformat(day), time.min, tzinfo=timezone.utc)
        statistics.append(
            {"start": start, "mean": float(value), "min": float(value), "max": float(value)}
        )
    if statistics:
        async_add_external_statistics(hass, metadata, statistics)


def _daily_fifo_snapshots(
    entries: list[dict[str, Any]], days: list[str], long_term_days: int
) -> dict[str, dict[str, Any]]:
    """Build compact daily FIFO snapshots in one chronological pass.

    Older releases rebuilt the complete FIFO ledger from the beginning for every
    historical day.  With thousands of ledger rows and several thousand cached
    price days that made the first dashboard request after an import extremely
    expensive.  This state machine processes each ledger row and each lot
    maturity only once while preserving exact chronological FIFO semantics.

    The per-depot lot cursor exists only for this calculation run.  Any later
    import/edit that inserts a historical transaction starts a fresh run, sorts
    the complete ledger again, and therefore restarts FIFO from the first lot.
    """
    threshold = max(1, int(long_term_days))
    zero = decimal_value(0)

    def entry_sort_key(row: dict[str, Any]) -> tuple[float, int, str]:
        numeric = _timestamp_value(row.get("timestamp"))
        return (
            numeric if numeric is not None else float("inf"),
            1 if row.get("type") in {"sale", "expense"} else 0,
            str(row.get("id", "")),
        )

    ordered = sorted(entries, key=entry_sort_key)
    lots_by_depot: dict[str, list[dict[str, Any]]] = {}
    lot_cursor_by_depot: dict[str, int] = {}

    # Acquisition timestamps are processed chronologically. Adding the same
    # holding period to each timestamp preserves that order, so maturities can
    # use a simple append-only queue rather than a heap.
    maturities: list[tuple[float, dict[str, Any]]] = []
    maturity_position = 0

    total_btc = zero
    long_term_btc = zero
    short_term_btc = zero

    depot_total: dict[str, Any] = {}
    depot_long: dict[str, Any] = {}
    depot_short: dict[str, Any] = {}

    known_btc_by_currency: dict[str, Any] = {}
    invested_by_currency: dict[str, Any] = {}
    realized_by_currency: dict[str, Any] = {}
    realized_long_by_currency: dict[str, Any] = {}
    realized_short_by_currency: dict[str, Any] = {}
    purchase_fees_by_currency: dict[str, Any] = {}
    sale_fees_by_currency: dict[str, Any] = {}

    def add(mapping: dict[str, Any], key: str, value: Any) -> None:
        mapping[key] = mapping.get(key, zero) + value

    def mature_until(cutoff: float) -> None:
        nonlocal maturity_position, long_term_btc, short_term_btc
        while maturity_position < len(maturities):
            maturity_at, lot = maturities[maturity_position]
            if maturity_at > cutoff:
                break
            maturity_position += 1
            if lot.get("holding_status") != "short_term":
                continue
            remaining = decimal_value(lot.get("remaining_btc"))
            lot["holding_status"] = "long_term"
            if remaining <= 0:
                continue
            depot_id = str(lot.get("depot_id") or "main")
            short_term_btc -= remaining
            long_term_btc += remaining
            add(depot_short, depot_id, -remaining)
            add(depot_long, depot_id, remaining)

    def consume_lots(
        *,
        depot_id: str,
        amount: Any,
        timestamp_value: float,
        sale_currency: str | None = None,
        sale_price: Any = None,
        sale_fee: Any = None,
    ) -> None:
        nonlocal total_btc, long_term_btc, short_term_btc
        lots = lots_by_depot.setdefault(depot_id, [])
        cursor = lot_cursor_by_depot.get(depot_id, 0)
        remaining_out = amount
        is_sale = sale_currency is not None
        sale_price_value = decimal_value(sale_price) if is_sale else zero
        sale_fee_value = decimal_value(sale_fee) if is_sale else zero

        while cursor < len(lots) and remaining_out > 0:
            lot = lots[cursor]
            available = decimal_value(lot.get("remaining_btc"))
            if available <= 0:
                cursor += 1
                continue
            used = min(available, remaining_out)
            left = available - used
            lot["remaining_btc"] = left
            remaining_out -= used

            total_btc -= used
            add(depot_total, depot_id, -used)
            if lot.get("holding_status") == "long_term":
                long_term_btc -= used
                add(depot_long, depot_id, -used)
            else:
                short_term_btc -= used
                add(depot_short, depot_id, -used)

            lot_currency = str(lot.get("currency") or "").upper()
            if lot.get("known_cost") and lot_currency:
                unit_basis = decimal_value(lot.get("unit_basis"))
                add(known_btc_by_currency, lot_currency, -used)
                add(invested_by_currency, lot_currency, -(used * unit_basis))
                if is_sale and lot_currency == sale_currency:
                    fee_share = sale_fee_value * used / amount if amount > 0 else zero
                    proceeds = used * sale_price_value - fee_share
                    gain = proceeds - used * unit_basis
                    add(realized_by_currency, sale_currency, gain)
                    if lot.get("holding_status") == "long_term":
                        add(realized_long_by_currency, sale_currency, gain)
                    else:
                        add(realized_short_by_currency, sale_currency, gain)

            if left <= 0:
                cursor += 1

        lot_cursor_by_depot[depot_id] = cursor
        # Oversold BTC is deliberately not subtracted from the running stack;
        # fifo_result() likewise reports it separately while open-lot total stays
        # at zero. Imports reject oversold ledgers before they reach this cache.

    snapshots: dict[str, dict[str, Any]] = {}
    position = 0
    maturity_seconds = float(threshold * 86400)

    for day in sorted(days):
        as_of = datetime.combine(date.fromisoformat(day), time.max, tzinfo=timezone.utc)
        cutoff = as_of.timestamp()

        while position < len(ordered):
            numeric = _timestamp_value(ordered[position].get("timestamp"))
            item = ordered[position]
            if numeric is None or numeric > cutoff:
                break

            # A lot becomes long-term at the exact maturity instant, so apply
            # maturity events before any ledger transaction at that same instant.
            mature_until(numeric)

            position += 1
            kind = str(item.get("type") or "")
            amount = max(decimal_value(item.get("amount_btc")), zero)
            if amount <= 0:
                continue
            depot_id = str(item.get("depot_id") or "main")

            if kind in {"purchase", "stack"}:
                currency = (
                    str(item.get("currency") or "").upper()
                    if kind == "purchase" and item.get("currency")
                    else ""
                )
                price = decimal_value(item.get("price")) if kind == "purchase" else zero
                fee = decimal_value(item.get("fee")) if kind == "purchase" else zero
                total_basis = amount * price + fee if kind == "purchase" else None
                unit_basis = total_basis / amount if total_basis is not None and amount > 0 else None
                lot = {
                    "remaining_btc": amount,
                    "depot_id": depot_id,
                    "currency": currency or None,
                    "unit_basis": unit_basis,
                    "known_cost": kind == "purchase",
                    "holding_status": "short_term",
                }
                lots_by_depot.setdefault(depot_id, []).append(lot)
                maturities.append((numeric + maturity_seconds, lot))

                total_btc += amount
                short_term_btc += amount
                add(depot_total, depot_id, amount)
                add(depot_short, depot_id, amount)
                if currency:
                    add(known_btc_by_currency, currency, amount)
                    add(invested_by_currency, currency, total_basis)
                    add(purchase_fees_by_currency, currency, fee)
                continue

            if kind == "expense":
                # A priced BTC expense is a disposal for FIFO/performance just
                # like a sale: BTC leaves the stack and the merchant/fiat value
                # is the disposal value. Keep the ledger type as expense; only
                # the mathematical treatment is sale-like. Unpriced expenses
                # still consume FIFO lots without inventing a fiat value.
                expense_currency = str(item.get("currency") or "").upper()
                expense_price = decimal_value(item.get("price"))
                expense_fee = decimal_value(item.get("fee"))
                if expense_currency and expense_price > 0:
                    consume_lots(
                        depot_id=depot_id,
                        amount=amount,
                        timestamp_value=numeric,
                        sale_currency=expense_currency,
                        sale_price=expense_price,
                        sale_fee=expense_fee,
                    )
                else:
                    consume_lots(
                        depot_id=depot_id,
                        amount=amount,
                        timestamp_value=numeric,
                    )
                continue

            if kind == "sale":
                sale_currency = str(item.get("currency") or "").upper()
                sale_fee = decimal_value(item.get("fee"))
                if sale_currency:
                    add(sale_fees_by_currency, sale_currency, sale_fee)
                consume_lots(
                    depot_id=depot_id,
                    amount=amount,
                    timestamp_value=numeric,
                    sale_currency=sale_currency,
                    sale_price=item.get("price"),
                    sale_fee=sale_fee,
                )

        mature_until(cutoff)

        currencies = (
            set(known_btc_by_currency)
            | set(invested_by_currency)
            | set(realized_by_currency)
            | set(realized_long_by_currency)
            | set(realized_short_by_currency)
            | set(purchase_fees_by_currency)
            | set(sale_fees_by_currency)
        )
        currency_summaries = {
            currency: {
                "known_btc": known_btc_by_currency.get(currency, zero),
                "invested": invested_by_currency.get(currency, zero),
                "realized_gain": realized_by_currency.get(currency, zero),
                "realized_long_term_gain": realized_long_by_currency.get(currency, zero),
                "realized_short_term_gain": realized_short_by_currency.get(currency, zero),
                "purchase_fees": purchase_fees_by_currency.get(currency, zero),
                "sale_fees": sale_fees_by_currency.get(currency, zero),
            }
            for currency in currencies
        }
        depot_ids = set(depot_total) | set(depot_long) | set(depot_short)
        snapshots[day] = {
            "total_btc": total_btc,
            "long_term_btc": long_term_btc,
            "short_term_btc": short_term_btc,
            "unknown_holding_btc": max(total_btc - long_term_btc - short_term_btc, zero),
            "currencies": currency_summaries,
            "depots": {
                depot_id: {
                    "total_btc": depot_total.get(depot_id, zero),
                    "long_term_btc": depot_long.get(depot_id, zero),
                    "short_term_btc": depot_short.get(depot_id, zero),
                }
                for depot_id in depot_ids
            },
        }

    return snapshots


def _snapshot_currency_summary(snapshot: dict[str, Any], currency: str) -> dict[str, Any]:
    """Return one compact daily FIFO currency summary with Decimal zero defaults."""
    zero = decimal_value(0)
    value = snapshot.get("currencies", {}).get(str(currency).upper(), {})
    return {
        "total_btc": snapshot.get("total_btc", zero),
        "known_btc": value.get("known_btc", zero),
        "invested": value.get("invested", zero),
        "realized_gain": value.get("realized_gain", zero),
        "realized_long_term_gain": value.get("realized_long_term_gain", zero),
        "realized_short_term_gain": value.get("realized_short_term_gain", zero),
        "purchase_fees": value.get("purchase_fees", zero),
        "sale_fees": value.get("sale_fees", zero),
    }


def _chart_revision(
    entries: list[dict[str, Any]],
    depots: list[dict[str, Any]],
    goals: list[dict[str, Any]],
    long_term_days: int,
    all_prices: dict[str, dict[str, float]],
) -> str:
    """Hash every input that changes a locally derived chart value."""
    payload = {
        "chart_schema": 5,
        "entries": entries,
        "depots": depots,
        "goals": goals,
        "long_term_days": int(long_term_days),
        "prices": {
            code: sorted(values.items()) for code, values in sorted(all_prices.items())
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _build_chart_cache(
    entries: list[dict[str, Any]],
    depots: list[dict[str, Any]],
    goals: list[dict[str, Any]],
    long_term_days: int,
    all_prices: dict[str, dict[str, float]],
) -> dict[str, Any]:
    """Build sensitive daily chart values exclusively from local cached prices."""
    days = sorted(
        {
            day
            for values in all_prices.values()
            for day, price in values.items()
            if float(price) > 0
        }
    )
    if not days:
        return {
            "stack_btc": {},
            "long_term_btc": {},
            "short_term_btc": {},
            "portfolio_value": {},
            "open_cost_basis": {},
            "unrealized_profit_loss": {},
            "realized_profit_loss": {},
            "total_profit_loss": {},
        }
    snapshots = _daily_fifo_snapshots(entries, days, long_term_days)
    result: dict[str, Any] = {
        "stack_btc": {},
        "long_term_btc": {},
        "short_term_btc": {},
        "portfolio_value": {code: {} for code in all_prices},
        "open_cost_basis": {code: {} for code in all_prices},
        "unrealized_profit_loss": {code: {} for code in all_prices},
        "realized_profit_loss": {code: {} for code in all_prices},
        "total_profit_loss": {code: {} for code in all_prices},
    }
    for day in days:
        total = snapshots[day]
        result["stack_btc"][day] = float(total["total_btc"])
        result["long_term_btc"][day] = float(total["long_term_btc"])
        result["short_term_btc"][day] = float(total["short_term_btc"])
        for code, prices in all_prices.items():
            raw_price = prices.get(day)
            if raw_price is None:
                continue
            price = decimal_value(raw_price)
            summary = _snapshot_currency_summary(total, code)
            result["portfolio_value"][code][day] = float(total["total_btc"] * price)
            result["open_cost_basis"][code][day] = float(summary["invested"])
            unrealized = summary["known_btc"] * price - summary["invested"]
            realized = summary["realized_gain"]
            result["unrealized_profit_loss"][code][day] = float(unrealized)
            result["realized_profit_loss"][code][day] = float(realized)
            result["total_profit_loss"][code][day] = float(unrealized + realized)
    return result


async def async_ensure_chart_cache(
    hass: HomeAssistant,
    ledger: BitcoinLedgerStore,
    history_store: BitcoinHistoryStore,
) -> dict[str, Any]:
    """Return a revisioned chart cache stored inside the optionally encrypted ledger."""
    ledger.require_unlocked()
    history = history_store.data
    all_prices = history.get("prices", {})
    entries = ledger.entries
    depots = ledger.depots
    goals = ledger.goals
    long_term_days = int(ledger.tax_settings.get("long_term_days", 365))
    revision = await hass.async_add_executor_job(
        _chart_revision, entries, depots, goals, long_term_days, all_prices
    )
    current = ledger.chart_cache
    if current.get("revision") == revision and isinstance(current.get("data"), dict):
        return current["data"]
    data = await hass.async_add_executor_job(
        _build_chart_cache,
        entries,
        depots,
        goals,
        long_term_days,
        all_prices,
    )
    await ledger.async_set_chart_cache(revision, data)
    return data


def _series_digest(name: str, unit: str | None, values: dict[str, float]) -> str:
    import hashlib
    import json

    encoded = json.dumps(
        {"name": name, "unit": unit, "values": sorted(values.items())},
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _build_statistics_series(
    *,
    entry_id: str,
    title: str,
    all_prices: dict[str, dict[str, float]],
    earliest: date,
    today: date,
    private_mode: bool,
    entries: list[dict[str, Any]],
    depots: list[dict[str, Any]],
    goals: list[dict[str, Any]],
    long_term_days: int,
) -> list[dict[str, Any]]:
    """Build all requested series outside the Home Assistant event loop."""
    series: list[dict[str, Any]] = []

    def add(priority: int, statistic_id: str, name: str, unit: str | None, values: dict[str, float]) -> None:
        clean = {
            day: float(value)
            for day, value in sorted(values.items())
            if earliest <= date.fromisoformat(day) < today and isfinite(float(value))
        }
        if clean:
            series.append(
                {
                    "priority": priority,
                    "statistic_id": statistic_id,
                    "name": name,
                    "unit": unit,
                    "values": clean,
                }
            )

    # Public BTC prices always have highest priority and are safe in Recorder.
    for currency, values in sorted(all_prices.items()):
        add(
            0,
            _statistic_id(entry_id, "btc_price", currency),
            f"{title} BTC price {currency}",
            f"{currency}/BTC",
            values,
        )

    if private_mode:
        return series

    history_days = sorted(
        {
            day
            for values in all_prices.values()
            for day in values
            if earliest <= date.fromisoformat(day) < today
        }
    )
    if not history_days:
        return series

    snapshots = _daily_fifo_snapshots(entries, history_days, long_term_days)
    stack_values: dict[str, float] = {}
    long_term_values: dict[str, float] = {}
    short_term_values: dict[str, float] = {}
    depot_stack = {str(depot["id"]): {} for depot in depots}
    depot_long = {str(depot["id"]): {} for depot in depots}
    depot_short = {str(depot["id"]): {} for depot in depots}
    goal_progress = {str(goal["id"]): {} for goal in goals}
    goal_remaining_fiat = {str(goal["id"]): {} for goal in goals}

    for day in history_days:
        total = snapshots[day]
        stack = total["total_btc"]
        stack_values[day] = float(stack)
        long_term_values[day] = float(total["long_term_btc"])
        short_term_values[day] = float(total["short_term_btc"])
        compact_depots = total.get("depots", {})
        depot_totals = {
            str(depot["id"]): decimal_value(compact_depots.get(str(depot["id"]), {}).get("total_btc"))
            for depot in depots
        }
        depot_long_totals = {
            str(depot["id"]): decimal_value(compact_depots.get(str(depot["id"]), {}).get("long_term_btc"))
            for depot in depots
        }
        depot_short_totals = {
            str(depot["id"]): decimal_value(compact_depots.get(str(depot["id"]), {}).get("short_term_btc"))
            for depot in depots
        }
        for depot_id in depot_totals:
            depot_stack[depot_id][day] = float(depot_totals[depot_id])
            depot_long[depot_id][day] = float(depot_long_totals[depot_id])
            depot_short[depot_id][day] = float(depot_short_totals[depot_id])

        for goal in goals:
            goal_id = str(goal["id"])
            scope = str(goal.get("depot_id", ALL_DEPOTS))
            goal_stack = stack if scope == ALL_DEPOTS else depot_totals.get(scope, decimal_value(0))
            target = decimal_value(goal.get("amount_btc"))
            remaining = max(target - goal_stack, decimal_value(0))
            goal_progress[goal_id][day] = float(min(goal_stack / target * 100, decimal_value(100))) if target > 0 else 0.0
            goal_currency = str(goal.get("currency", "EUR")).upper()
            price = all_prices.get(goal_currency, {}).get(day)
            if price is not None:
                goal_remaining_fiat[goal_id][day] = float(remaining * decimal_value(price))

    for metric, label, values in (
        ("stack_btc", "stack", stack_values),
        ("long_term_btc", "long-term stack", long_term_values),
        ("short_term_btc", "short-term stack", short_term_values),
    ):
        add(10, _statistic_id(entry_id, metric), f"{title} {label}", "BTC", values)

    # Core fiat series before optional depot and goal detail series.
    for currency, price_series in sorted(all_prices.items()):
        series_map: dict[str, dict[str, float]] = {
            "portfolio_value": {},
            "known_cost_market_value": {},
            "invested": {},
            "average_buy_price": {},
            "unrealized_profit_loss": {},
            "realized_profit_loss": {},
            "realized_long_term_profit_loss": {},
            "realized_short_term_profit_loss": {},
            "purchase_fees": {},
            "sale_fees": {},
        }
        for day, raw_price in sorted(price_series.items()):
            if day not in snapshots:
                continue
            total = snapshots[day]
            summary = _snapshot_currency_summary(total, currency)
            price = decimal_value(raw_price)
            series_map["portfolio_value"][day] = float(total["total_btc"] * price)
            series_map["known_cost_market_value"][day] = float(summary["known_btc"] * price)
            series_map["invested"][day] = float(summary["invested"])
            if summary["known_btc"] > 0:
                series_map["average_buy_price"][day] = float(summary["invested"] / summary["known_btc"])
            series_map["unrealized_profit_loss"][day] = float(summary["known_btc"] * price - summary["invested"])
            series_map["realized_profit_loss"][day] = float(summary["realized_gain"])
            series_map["realized_long_term_profit_loss"][day] = float(summary["realized_long_term_gain"])
            series_map["realized_short_term_profit_loss"][day] = float(summary["realized_short_term_gain"])
            series_map["purchase_fees"][day] = float(summary["purchase_fees"])
            series_map["sale_fees"][day] = float(summary["sale_fees"])
        labels = {
            "portfolio_value": "portfolio value",
            "known_cost_market_value": "cost-tracked market value",
            "invested": "open cost basis",
            "average_buy_price": "average open purchase price",
            "unrealized_profit_loss": "unrealized profit/loss",
            "realized_profit_loss": "realized FIFO profit/loss",
            "realized_long_term_profit_loss": "realized long-term FIFO profit/loss",
            "realized_short_term_profit_loss": "realized short-term FIFO profit/loss",
            "purchase_fees": "purchase fees",
            "sale_fees": "sale fees",
        }
        for metric, values in series_map.items():
            add(
                20,
                _statistic_id(entry_id, metric, currency),
                f"{title} {labels[metric]} {currency}",
                currency,
                values,
            )

    for depot in depots:
        depot_id = str(depot["id"])
        for metric, label, values in (
            ("depot_stack_btc", "stack", depot_stack[depot_id]),
            ("depot_long_term_btc", "long-term stack", depot_long[depot_id]),
            ("depot_short_term_btc", "short-term stack", depot_short[depot_id]),
        ):
            add(
                30,
                _statistic_id(entry_id, metric, suffix=depot_id),
                f"{title} {depot['name']} {label}",
                "BTC",
                values,
            )

    for goal in goals:
        goal_id = str(goal["id"])
        add(
            40,
            _statistic_id(entry_id, "goal_progress", suffix=goal_id),
            f"{title} {goal['name']} progress",
            "%",
            goal_progress[goal_id],
        )
        currency = str(goal.get("currency", "EUR")).upper()
        add(
            40,
            _statistic_id(entry_id, "goal_remaining_fiat", currency=currency, suffix=goal_id),
            f"{title} {goal['name']} remaining fiat",
            currency,
            goal_remaining_fiat[goal_id],
        )
    return sorted(series, key=lambda item: (item["priority"], item["statistic_id"]))


def _select_series_with_limits(series: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    from .limits import (
        MAX_STATISTIC_POINTS_PER_SERIES,
        MAX_STATISTIC_POINTS_PER_SYNC,
        MAX_STATISTIC_SERIES,
    )

    selected: list[dict[str, Any]] = []
    omitted: list[str] = []
    total_points = 0
    for item in series:
        values = dict(sorted(item["values"].items()))
        points = len(values)
        if points > MAX_STATISTIC_POINTS_PER_SERIES:
            omitted.append(item["statistic_id"])
            continue
        if len(selected) >= MAX_STATISTIC_SERIES or total_points + points > MAX_STATISTIC_POINTS_PER_SYNC:
            omitted.append(item["statistic_id"])
            continue
        selected.append({**item, "values": values})
        total_points += points
    return selected, omitted


async def async_clear_entry_statistics(
    hass: HomeAssistant, statistic_ids: list[str]
) -> int:
    """Queue deletion of integration-owned external statistics."""
    ids = sorted({item for item in statistic_ids if item.startswith(f"{DOMAIN}:")})
    if not ids:
        return 0
    from homeassistant.components.recorder import get_instance

    get_instance(hass).async_clear_statistics(ids)
    return len(ids)


async def async_sync_intraday_history(
    hass: HomeAssistant,
    entry: ConfigEntry,
    history_store: BitcoinHistoryStore,
    history_days: int = 366,
    interval_minutes: int | None = None,
) -> dict[str, Any]:
    """Fetch one exact, uniform candle tier through Tor for the selected chart."""
    settings = effective_settings(entry)
    if not bool(settings.get(CONF_HISTORY_ENABLED, True)):
        return {"history_enabled": False, "sample_counts": {}, "errors": []}
    requested_days = max(1, min(int(history_days or 1), 731))
    interval = int(interval_minutes or _market_ohlc_interval_for_days(requested_days))
    if interval not in MARKET_OHLC_TIERS:
        raise ValueError(f"Unsupported requested chart interval: {interval}")
    currencies = configured_currencies(settings)[:MAX_HISTORY_CURRENCIES]
    errors: list[str] = []
    changed: dict[str, int] = {}
    counts: dict[str, int] = {}
    providers: dict[str, str] = {}
    proxy_url = tor_proxy_from_settings(settings)
    for currency in currencies:
        if currency not in KRAKEN_CURRENCIES:
            continue
        try:
            values, provider = await _fetch_exact_market_candles(
                hass, currency, proxy_url, interval
            )
            changed[currency] = await history_store.async_merge_market_candles(
                currency, interval, values
            )
            providers[currency] = provider
            counts[currency] = len(
                history_store.market_candles_for_days(requested_days, interval).get(currency, {})
            )
        except (ClientError, asyncio.TimeoutError, ValueError) as err:
            provider = "Bitstamp" if interval in BITSTAMP_OHLC_STEPS else "Kraken"
            errors.append(f"{currency}: {provider} {interval}m OHLC through Tor unavailable: {err}")
    return {
        "history_enabled": True,
        "changed_samples": changed,
        "sample_counts": counts,
        "interval_minutes": interval,
        "providers": providers,
        "requested_days": requested_days,
        "errors": errors,
        "network_route": "Tor only",
    }


async def async_sync_history(
    hass: HomeAssistant,
    entry: ConfigEntry,
    ledger: BitcoinLedgerStore,
    history_store: BitcoinHistoryStore,
) -> dict[str, Any]:
    """Serialize history synchronization per portfolio."""
    async with history_store.sync_lock:
        return await _async_sync_history_unlocked(
            hass, entry, ledger, history_store
        )


async def _async_sync_history_unlocked(
    hass: HomeAssistant,
    entry: ConfigEntry,
    ledger: BitcoinLedgerStore,
    history_store: BitcoinHistoryStore,
) -> dict[str, Any]:
    """Incrementally extend the durable daily cache and import HA statistics."""
    settings = effective_settings(entry)
    now_iso = dt_util.utcnow().isoformat()
    if not bool(settings.get(CONF_HISTORY_ENABLED, True)):
        await history_store.async_set_sync_status(now_iso, [])
        return {
            "history_enabled": False,
            "downloaded_daily_values": {},
            "errors": [],
            "last_sync": now_iso,
            "cache_retained": True,
        }

    configured = configured_currencies(settings)
    currencies = configured[:MAX_HISTORY_CURRENCIES]
    errors: list[str] = []
    source_notes: dict[str, list[str]] = {code: [] for code in currencies}
    if len(configured) > MAX_HISTORY_CURRENCIES:
        errors.append(
            f"History source limit: using the first {MAX_HISTORY_CURRENCIES} currencies"
        )

    initial_state = history_store.data
    initial_prices: dict[str, dict[str, float]] = initial_state.get("prices", {})
    bootstrap_state = initial_state.get("bootstrap_complete", {})
    source_metadata_state = initial_state.get("source_metadata", {})
    today = dt_util.utcnow().date()
    bootstrap_needed = {
        code
        for code in currencies
        if not bool(bootstrap_state.get(code))
        or dict(source_metadata_state.get(code, {})).get("history_strategy")
        != HISTORY_STRATEGY_VERSION
        or not _is_full_market_history(dict(initial_prices.get(code, {})))
    }

    # v7: ordered backwards source cascade.  The integration first asks the
    # user's own/configured infrastructure, then only asks the next provider for
    # the still-missing prefix before the oldest cached day.  Public providers
    # are never fanned out in parallel and all of them remain Tor-only.
    public_proxy: str | None = None
    try:
        public_proxy = tor_proxy_from_settings(settings)
    except (ValueError, TypeError) as err:
        errors.append(f"Tor proxy unavailable: {err}")

    provider_cache: dict[tuple[str, str, str, str], dict[str, float]] = {}
    ecb_cache: dict[tuple[str, str, str], dict[str, dict[str, float]]] = {}

    async def cached_public_usd(provider: str, start_day: str, end_day: str) -> dict[str, float]:
        key = (provider, "USD", start_day, end_day)
        if key in provider_cache:
            return provider_cache[key]
        if public_proxy is None:
            raise ValueError("Tor proxy unavailable")
        if provider == "Blockchain.com":
            result = await _fetch_blockchain_usd_history(
                hass, proxy_url=public_proxy, start_day=start_day, end_day=end_day
            )
        elif provider == "Coin Metrics":
            result = await _fetch_coinmetrics_usd_history(
                hass, proxy_url=public_proxy, start_day=start_day, end_day=end_day
            )
        else:
            raise ValueError(f"Unsupported USD history provider: {provider}")
        provider_cache[key] = result
        return result

    async def cached_coingecko(currency: str, start_day: str, end_day: str) -> dict[str, float]:
        key = ("CoinGecko", currency.upper(), start_day, end_day)
        if key not in provider_cache:
            if public_proxy is None:
                raise ValueError("Tor proxy unavailable")
            provider_cache[key] = await _fetch_coingecko_history(
                hass,
                currency,
                proxy_url=public_proxy,
                start_day=start_day,
                end_day=end_day,
            )
        return provider_cache[key]

    async def cached_ecb(currency: str, start_day: str, end_day: str) -> dict[str, dict[str, float]]:
        code = currency.upper()
        key = (code, start_day, end_day)
        if key not in ecb_cache:
            if public_proxy is None:
                raise ValueError("Tor proxy unavailable")
            ecb_cache[key] = await _fetch_ecb_rates(
                hass,
                {code},
                proxy_url=public_proxy,
                start_day=start_day,
                end_day=end_day,
            )
        return ecb_cache[key]

    async def usd_to_currency(
        usd_values: dict[str, float], currency: str, start_day: str, end_day: str
    ) -> dict[str, float]:
        if currency.upper() == "USD":
            return dict(usd_values)
        rates = await cached_ecb(currency, start_day, end_day)
        return _convert_usd_history(usd_values, currency, rates)

    downloaded: dict[str, int] = {}
    for currency in currencies:
        existing = dict(initial_prices.get(currency, {}))
        values: dict[str, float] = dict(existing)
        metadata: dict[str, Any] = dict(source_metadata_state.get(currency, {}))
        needs_full_backfill = currency in bootstrap_needed
        source_chain: list[dict[str, Any]] = []
        public_sources_used: list[str] = []
        preferred_overlay: dict[str, float] = {}
        yesterday = (today - timedelta(days=1)).isoformat()

        if needs_full_backfill:
            for stale_key in (
                "primary_history_source", "fallback_history_source",
                "preferred_history_source", "public_history_sources",
                "exclusive_source", "history_strategy", "history_source_chain",
            ):
                metadata.pop(stale_key, None)

        configured_sources = []
        for source in settings.get(CONF_SOURCES, []):
            source_currencies = {str(item).upper() for item in source.get(CONF_CURRENCIES, [])}
            if currency in source_currencies:
                configured_sources.append(source)
        own_sources = [
            source for source in configured_sources
            if source.get(CONF_SOURCE_TYPE) == SOURCE_MEMPOOL
            and bool(source.get("mempool_own_instance"))
        ]
        secondary_sources = [source for source in configured_sources if source not in own_sources]

        # 1) Own infrastructure first. The own mempool instance preferred on overlap
        # remains authoritative; the first configured own instance wins.
        # on overlap; additional own instances may still extend the left edge.
        for source_index, source in enumerate(own_sources):
            try:
                own_values = await _fetch_mempool_history(hass, settings, source, currency)
                for day, price in own_values.items():
                    preferred_overlay.setdefault(day, float(price))
                before = min(values) if values else None
                if not values:
                    values.update(own_values)
                    contributed = dict(own_values)
                else:
                    contributed = _merge_older_prefix(values, own_values)
                    # Refresh recent/overlapping data from the preferred source too.
                    values.update(own_values)
                route = "Tor" if mempool_source_uses_tor(source) else "local-direct"
                label = "own mempool instance" if source_index == 0 else f"own mempool instance #{source_index + 1}"
                record = _history_source_record(label, contributed or own_values, route=route, role="preferred")
                if record:
                    source_chain.append(record)
                source_notes[currency].append(
                    f"{label} preferred on overlap: {len(own_values)} daily values ({min(own_values)} → {max(own_values)}, {route})"
                )
                metadata.update({
                    "preferred_history_source": "own mempool instance",
                    "own_mempool_network_route": route,
                    "exclusive_source": False,
                    "configured_source_points": len(own_values),
                })
            except (ClientError, asyncio.TimeoutError, ValueError) as err:
                source_notes[currency].append(
                    f"own mempool instance unavailable ({type(err).__name__})"
                )

        # 2) Then other explicitly configured history-capable sources in their
        # configuration order, but only when they can improve current/deep data.
        recent_needed = not values or max(values) < yesterday
        for source in secondary_sources:
            if not needs_full_backfill and not recent_needed:
                break
            source_type = source.get(CONF_SOURCE_TYPE)
            try:
                candidate: dict[str, float] = {}
                label = str(source_type or "configured source")
                if source_type == SOURCE_MEMPOOL:
                    candidate = await _fetch_mempool_history(hass, settings, source, currency)
                    label = "configured mempool API"
                elif source_type == SOURCE_KRAKEN:
                    # Kraken REST OHLC only exposes the latest 720 rows.  Skip a
                    # useless request when the current left edge is already older.
                    kraken_oldest_possible = today - timedelta(days=KRAKEN_OHLC_LIMIT + 2)
                    if values and date.fromisoformat(min(values)) <= kraken_oldest_possible and needs_full_backfill:
                        source_notes[currency].append(
                            "configured Kraken skipped for deep backfill: 720 daily candles cannot extend the current left edge"
                        )
                        continue
                    if public_proxy is None:
                        raise ValueError("Tor proxy unavailable")
                    candidate = await _fetch_kraken_history(hass, currency, public_proxy)
                    label = "configured Kraken daily OHLC"
                else:
                    continue

                if needs_full_backfill:
                    contributed = _merge_older_prefix(values, candidate)
                else:
                    old = dict(values)
                    values.update(candidate)
                    contributed = {day: price for day, price in candidate.items() if old.get(day) != price}
                values.update(preferred_overlay)
                if contributed:
                    route = "Tor" if source_type == SOURCE_KRAKEN or mempool_source_uses_tor(source) else "local-direct"
                    record = _history_source_record(label, contributed, route=route, role="configured-backfill")
                    if record:
                        source_chain.append(record)
                    source_notes[currency].append(
                        f"{label}: added {len(contributed)} values ({min(contributed)} → {max(contributed)})"
                    )
                recent_needed = not values or max(values) < yesterday
                if _is_full_market_history(values) and not recent_needed:
                    break
            except (ClientError, asyncio.TimeoutError, ValueError) as err:
                source_notes[currency].append(f"configured source unavailable: {err}")

        # 3) Reuse an already cached BTC/USD all-time series before making a new
        # Bitcoin-market request.  Convert the local USD cache with official ECB
        # FX history and fill *every missing day*, not only the prefix before the
        # own node's oldest observation.  Own/configured values already present in
        # ``values`` remain authoritative on overlap.
        if needs_full_backfill and currency != "USD":
            local_usd = {
                day: float(price)
                for day, price in dict(initial_prices.get("USD", {})).items()
                if ALL_TIME_PRICE_START_DAY <= day <= yesterday and float(price) > 0
            }
            if local_usd:
                fx_start = min(local_usd)
                fx_end = max(local_usd)
                # Include the preceding working week so an earliest BTC point on
                # a weekend can still use Friday's official ECB reference rate.
                fx_rate_start = (date.fromisoformat(fx_start) - timedelta(days=7)).isoformat()
                try:
                    converted = await usd_to_currency(
                        local_usd, currency, fx_rate_start, fx_end
                    )
                    contributed = _fill_missing_days(values, converted)
                    values.update(preferred_overlay)
                    if contributed:
                        record = _history_source_record(
                            "local BTC/USD cache + ECB",
                            contributed,
                            route="local cache + Tor FX",
                            role="gap-fill + deep-backfill",
                        )
                        if record:
                            source_chain.append(record)
                        public_sources_used.append("ECB")
                        source_notes[currency].append(
                            f"local USD cache + ECB: filled {len(contributed)} missing values "
                            f"({min(contributed)} → {max(contributed)}); preferred own-source values retained"
                        )
                    elif not _is_full_market_history(values):
                        source_notes[currency].append(
                            f"local USD cache + ECB produced {len(converted)} convertible values but no missing days were added"
                        )
                except (ClientError, asyncio.TimeoutError, ValueError) as err:
                    source_notes[currency].append(f"local USD cache conversion through ECB unavailable: {err}")

        # 4) Deep public cascade. Every provider is allowed to fill *all* missing
        # calendar days in the all-time range, not only a prefix before the oldest
        # cached observation. This is essential when a provider returns a sampled
        # series that reaches 2010 but contains only ~1.5k points. Existing own or
        # configured values remain authoritative because _fill_missing_days never
        # overwrites them. Stop only after the cache is actually dense and recent.
        if needs_full_backfill and public_proxy is not None:
            full_range_end = yesterday
            for provider in ("Blockchain.com", "Coin Metrics", "CoinGecko"):
                if _is_full_market_history(values):
                    break
                try:
                    if provider == "CoinGecko":
                        candidate = await cached_coingecko(
                            currency, ALL_TIME_PRICE_START_DAY, full_range_end
                        )
                        label = "CoinGecko public market chart"
                    else:
                        usd_values = await cached_public_usd(
                            provider, ALL_TIME_PRICE_START_DAY, full_range_end
                        )
                        candidate = await usd_to_currency(
                            usd_values, currency, ALL_TIME_PRICE_START_DAY, full_range_end
                        )
                        label = (
                            f"{provider} BTC/USD"
                            if currency == "USD"
                            else f"{provider} BTC/USD + ECB"
                        )
                    contributed = _fill_missing_days(values, candidate)
                    values.update(preferred_overlay)
                    if contributed:
                        record = _history_source_record(
                            label, contributed, route="Tor", role="gap-fill + deep-backfill"
                        )
                        if record:
                            source_chain.append(record)
                        public_sources_used.append(provider)
                        if currency != "USD" and provider != "CoinGecko":
                            public_sources_used.append("ECB")
                        source_notes[currency].append(
                            f"{label} through Tor: filled {len(contributed)} missing daily values "
                            f"({min(contributed)} → {max(contributed)})"
                        )
                    else:
                        source_notes[currency].append(
                            f"{label} through Tor: no missing daily values could be filled"
                        )
                except (ClientError, asyncio.TimeoutError, ValueError) as err:
                    source_notes[currency].append(f"{provider} through Tor unavailable: {err}")

        # 5) Normal daily refresh after a completed bootstrap: only one public
        # fallback is tried if configured/local infrastructure did not reach
        # yesterday.  This prevents a daily fan-out to every provider.
        recent_needed = not values or max(values) < yesterday
        if not needs_full_backfill and recent_needed and public_proxy is not None:
            recent_start = (
                (date.fromisoformat(max(values)) - timedelta(days=3)).isoformat()
                if values else (today - timedelta(days=14)).isoformat()
            )
            try:
                direct = await cached_coingecko(currency, recent_start, yesterday)
                old = dict(values)
                values.update(direct)
                values.update(preferred_overlay)
                changed_recent = {day: price for day, price in direct.items() if old.get(day) != price}
                if changed_recent:
                    record = _history_source_record(
                        "CoinGecko recent fallback", changed_recent, route="Tor", role="incremental"
                    )
                    if record:
                        source_chain.append(record)
                    public_sources_used.append("CoinGecko")
                    source_notes[currency].append(
                        f"CoinGecko recent fallback through Tor: {len(changed_recent)} changed values"
                    )
            except (ClientError, asyncio.TimeoutError, ValueError) as err:
                source_notes[currency].append(f"CoinGecko recent fallback through Tor unavailable: {err}")

        # Seed the recent chart with the single exact OHLC interval needed for
        # the one-year view.  This remains separate from the daily deep cascade.
        if public_proxy is not None and currency in KRAKEN_CURRENCIES:
            try:
                seed_interval = _market_ohlc_interval_for_days(366)
                intraday, provider = await _fetch_exact_market_candles(
                    hass, currency, public_proxy, seed_interval
                )
                sample_changes = await history_store.async_merge_market_candles(
                    currency, seed_interval, intraday
                )
                source_notes[currency].append(f"{provider} {seed_interval}m OHLC through Tor")
                metadata.update(
                    {
                        "intraday_history_source": f"{provider} {seed_interval}m OHLC through Tor",
                        "intraday_network_route": "Tor",
                        "intraday_source_points": len(intraday),
                        "intraday_interval_minutes": seed_interval,
                        "intraday_changed_points": sample_changes,
                    }
                )
            except (ClientError, asyncio.TimeoutError, ValueError) as err:
                source_notes[currency].append(
                    f"intraday OHLC through Tor unavailable: {err}"
                )

        # Persist readable provenance.  The chain describes the order actually
        # used by this sync instead of presenting every possible provider as if
        # all of them had been queried.
        if source_chain:
            metadata["history_source_chain"] = source_chain
            metadata["primary_history_source"] = source_chain[0]["source"]
            if len(source_chain) > 1:
                metadata["fallback_history_source"] = " → ".join(
                    item["source"] for item in source_chain[1:]
                )
        if public_sources_used:
            metadata["public_history_sources"] = list(dict.fromkeys(public_sources_used))
            metadata["public_network_route"] = "Tor"

        values = {
            day: float(price)
            for day, price in values.items()
            if date.fromisoformat(day) < today and float(price) > 0
        }
        if not values:
            source_reason = "; ".join(source_notes[currency] + shared_errors)
            reason = source_reason or "no historical source available"
            errors.append(f"{currency}: {reason}")
            continue

        changed = sum(1 for day, price in values.items() if existing.get(day) != price)
        await history_store.async_merge_prices(currency, values)
        combined_days = set(existing) | set(values)
        bootstrap_complete = _is_full_market_history(values)
        if bootstrap_complete:
            metadata["history_strategy"] = HISTORY_STRATEGY_VERSION
        else:
            metadata.pop("history_strategy", None)
        metadata.update(
            {
                "last_incremental_start": (
                    (date.fromisoformat(max(values)) - timedelta(days=3)).isoformat()
                    if values else None
                ),
                "last_update": now_iso,
                "cached_first_day": min(combined_days),
                "cached_last_day": max(combined_days),
                "all_time_backfill_complete": bootstrap_complete,
            }
        )
        await history_store.async_set_source_state(
            currency,
            bootstrap_complete=bootstrap_complete,
            metadata=metadata,
        )
        downloaded[currency] = changed

    all_history = history_store.data
    all_prices: dict[str, dict[str, float]] = all_history.get("prices", {})
    all_days = [day for values in all_prices.values() for day in values]
    earliest = date.fromisoformat(min(all_days)) if all_days else today

    private_mode = (
        ledger.security.encryption_mode == "password"
        or ledger.is_locked
        or not ledger.security.expose_sensitive_sensors
    )
    if private_mode:
        entries: list[dict[str, Any]] = []
        depots: list[dict[str, Any]] = []
        goals: list[dict[str, Any]] = []
        long_term_days = 365
    else:
        entries = ledger.entries
        depots = ledger.depots
        goals = ledger.goals
        long_term_days = int(ledger.tax_settings.get("long_term_days", 365))

    full_series = await hass.async_add_executor_job(
        partial(
            _build_statistics_series,
            entry_id=entry.entry_id,
            title=entry.title,
            all_prices=all_prices,
            earliest=earliest,
            today=today,
            private_mode=private_mode,
            entries=entries,
            depots=depots,
            goals=goals,
            long_term_days=long_term_days,
        )
    )
    selected, omitted = await hass.async_add_executor_job(
        _select_series_with_limits, full_series
    )
    desired_ids = {item["statistic_id"] for item in full_series}
    old_hashes = dict(all_history.get("statistics_hashes", {}))
    old_ids = set(all_history.get("statistics_ids", [])) | set(old_hashes)
    removed_ids = sorted(old_ids - desired_ids)
    cleared = await async_clear_entry_statistics(hass, removed_ids)

    new_hashes = {key: value for key, value in old_hashes.items() if key in desired_ids}
    imported = 0
    unchanged = 0
    for item in selected:
        statistic_id = item["statistic_id"]
        digest = await hass.async_add_executor_job(
            _series_digest, item["name"], item["unit"], item["values"]
        )
        if old_hashes.get(statistic_id) == digest:
            unchanged += 1
            new_hashes[statistic_id] = digest
            continue
        await async_clear_entry_statistics(hass, [statistic_id])
        _import_measurement(
            hass,
            statistic_id=statistic_id,
            name=item["name"],
            unit=item["unit"],
            values=item["values"],
        )
        new_hashes[statistic_id] = digest
        imported += 1

    current_ids = sorted(
        (old_ids & set(omitted)) | {item["statistic_id"] for item in selected}
    )
    await history_store.async_set_statistics_state(new_hashes, current_ids)
    if omitted:
        errors.append(
            f"Recorder protection omitted {len(omitted)} optional series; the complete local dashboard cache is retained"
        )

    chart_points = 0
    if not ledger.is_locked:
        chart_cache = await async_ensure_chart_cache(hass, ledger, history_store)
        chart_points = len(chart_cache.get("stack_btc", {}))

    await history_store.async_set_sync_status(now_iso, errors)
    _LOGGER.info(
        "Bitcoin history sync for %s: %d imported, %d unchanged, %d removed, %d omitted, %d chart days",
        entry.entry_id,
        imported,
        unchanged,
        cleared,
        len(omitted),
        chart_points,
    )
    return {
        "history_enabled": True,
        "downloaded_daily_values": downloaded,
        "cached_daily_values": {
            code: len(values) for code, values in all_prices.items()
        },
        "source_notes": source_notes,
        "errors": errors,
        "last_sync": now_iso,
        "cache_retained": True,
        "holding_period_days": long_term_days,
        "private_mode": private_mode,
        "portfolio_statistics_imported": not private_mode,
        "statistics_imported": imported,
        "statistics_unchanged": unchanged,
        "statistics_removed": cleared,
        "statistics_omitted_by_limit": len(omitted),
        "chart_daily_points": chart_points,
    }
