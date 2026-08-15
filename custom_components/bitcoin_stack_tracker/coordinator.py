"""Price update coordinator for Bitcoin Stack Tracker."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from math import isfinite
from time import monotonic
from typing import Any

from aiohttp import ClientError, ClientResponseError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BASE_URL,
    CONF_CURRENCIES,
    CONF_CURRENCY,
    CONF_ENTITY_ID,
    CONF_SOURCE_TYPE,
    CONF_SOURCES,
    CONF_UPDATE_INTERVAL,
    CONF_PUBLIC_UPDATE_INTERVAL,
    CONF_MEMPOOL_OWN_INSTANCE,
    CONF_VERIFY_SSL,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_PUBLIC_UPDATE_INTERVAL,
    DOMAIN,
    SOURCE_ENTITY,
    SOURCE_KRAKEN,
    SOURCE_MEMPOOL,
)
from .storage import BitcoinHistoryStore
from .http_limits import async_json_limited
from .network import (
    async_routed_session,
    mempool_source_uses_tor,
    tor_proxy_from_settings,
)

_LOGGER = logging.getLogger(__name__)


class BitcoinPriceCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Collect Bitcoin prices from local entities, a public market average, or mempool."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, history_store: BitcoinHistoryStore | None = None
    ) -> None:
        self.entry = entry
        self.history_store = history_store
        settings = {**entry.data, **entry.options}
        local_interval = max(60, int(settings.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)))
        public_interval = max(30, int(settings.get(CONF_PUBLIC_UPDATE_INTERVAL, DEFAULT_PUBLIC_UPDATE_INTERVAL)))
        has_fast_public = any(self._is_public_source(source) for source in settings.get(CONF_SOURCES, []))
        coordinator_interval = min(local_interval, public_interval) if has_fast_public else local_interval
        self.local_interval_seconds = local_interval
        self.public_interval_seconds = public_interval
        self._source_cache: dict[int, dict[str, Any]] = {}
        self._source_last_attempt: dict[int, float] = {}
        self._last_persisted_updated_at: str | None = None
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=coordinator_interval),
            always_update=False,
        )

    @property
    def settings(self) -> dict[str, Any]:
        """Return the effective config entry settings."""
        return {**self.entry.data, **self.entry.options}

    @staticmethod
    def _is_public_source(source: Any) -> bool:
        """Return True for sources that must use the fast Tor/public lane."""
        if not isinstance(source, dict):
            return False
        source_type = source.get(CONF_SOURCE_TYPE)
        if source_type == SOURCE_KRAKEN:
            return True
        return source_type == SOURCE_MEMPOOL and not bool(source.get(CONF_MEMPOOL_OWN_INSTANCE, False))

    def _source_interval_seconds(self, source: dict[str, Any]) -> int:
        return self.public_interval_seconds if self._is_public_source(source) else self.local_interval_seconds

    def _cache_is_fresh(self, source: dict[str, Any], cached: dict[str, Any], now_mono: float) -> bool:
        last_success = float(cached.get("last_success_mono", 0.0) or 0.0)
        if last_success <= 0:
            return False
        # A failed public ticker should stop masking a healthy local source after
        # a short grace period. Local sources get a wider window because their
        # normal cadence is intentionally slower.
        max_age = max(90, self._source_interval_seconds(source) * 3)
        return (now_mono - last_success) <= max_age

    async def _async_update_data(self) -> dict[str, Any]:
        errors: list[str] = []
        now_mono = monotonic()
        sources = [source for source in self.settings.get(CONF_SOURCES, []) if isinstance(source, dict)]

        # Refresh each source on its own cadence. Own/local sources keep the
        # normal five-minute default, while configured public sources can run
        # on the faster Tor-only interval (default 60 s).
        for index, source in enumerate(sources):
            interval = self._source_interval_seconds(source)
            last_attempt = self._source_last_attempt.get(index, 0.0)
            due = index not in self._source_cache or (now_mono - last_attempt) >= interval
            if not due:
                continue
            self._source_last_attempt[index] = now_mono
            source_prices: dict[str, float] = {}
            source_details: dict[str, Any] = {}
            source_type = source.get(CONF_SOURCE_TYPE)
            try:
                if source_type == SOURCE_ENTITY:
                    self._read_entity_source(source, source_prices)
                elif source_type == SOURCE_MEMPOOL:
                    await self._read_mempool_source(source, source_prices)
                elif source_type == SOURCE_KRAKEN:
                    await self._read_public_market_average_source(source, source_prices, source_details)
                else:
                    raise ValueError(f"Unsupported source type {source_type}")
                if not source_prices:
                    raise ValueError("source returned no usable BTC price")
                refreshed_at = dt_util.utcnow().isoformat()
                self._source_cache[index] = {
                    "prices": dict(source_prices),
                    "price_details": dict(source_details),
                    "updated_at": refreshed_at,
                    "last_success_mono": monotonic(),
                    "source_type": source_type,
                    "public_fast_lane": self._is_public_source(source),
                }
            except (ClientError, asyncio.TimeoutError, ValueError) as err:
                errors.append(f"{source_type}: {err}")

        prices: dict[str, float] = {}
        price_details: dict[str, Any] = {}
        live_source_by_currency: dict[str, Any] = {}
        selected_timestamps: list[str] = []

        # When an additional public source is configured it is intentionally the
        # live fast lane. It updates the dashboard between the slower own-node
        # anchor polls. Within each lane the user's configured source order remains
        # the priority order. If the public lane becomes stale, local/own data
        # automatically takes over; this is price-source failover only and is
        # completely separate from Sats Sentinel's strict own-node-only policy.
        ordered_indices = [
            index for index, source in enumerate(sources) if self._is_public_source(source)
        ] + [
            index for index, source in enumerate(sources) if not self._is_public_source(source)
        ]
        for index in ordered_indices:
            source = sources[index]
            cached = self._source_cache.get(index)
            if not cached or not self._cache_is_fresh(source, cached, now_mono):
                continue
            updated_at = str(cached.get("updated_at") or "")
            for currency, value in (cached.get("prices") or {}).items():
                code = str(currency).upper()
                if code in prices:
                    continue
                prices[code] = float(value)
                if updated_at:
                    selected_timestamps.append(updated_at)
                details = (cached.get("price_details") or {}).get(code)
                if isinstance(details, dict):
                    price_details[code] = dict(details)
                live_source_by_currency[code] = {
                    "source_type": str(source.get(CONF_SOURCE_TYPE) or "unknown"),
                    "source_index": index,
                    "route": "tor" if self._is_public_source(source) or mempool_source_uses_tor(source) else ("ha-local" if source.get(CONF_SOURCE_TYPE) == SOURCE_ENTITY else "local-direct"),
                    "updated_at": updated_at or None,
                    "public_fast_lane": self._is_public_source(source),
                    "interval_seconds": self._source_interval_seconds(source),
                }

        if not prices:
            return {
                "prices": {},
                "errors": errors or ["No live Bitcoin price is available"],
                "updated_at": dt_util.utcnow().isoformat(),
                "live_data_available": False,
                "price_details": {},
                "live_source_by_currency": {},
                "local_interval_seconds": self.local_interval_seconds,
                "public_interval_seconds": self.public_interval_seconds,
            }

        updated_at = max(selected_timestamps) if selected_timestamps else dt_util.utcnow().isoformat()
        if self.history_store is not None and updated_at != self._last_persisted_updated_at:
            try:
                await self.history_store.async_add_price_samples(prices, updated_at)
                self._last_persisted_updated_at = updated_at
            except (OSError, ValueError) as err:
                _LOGGER.warning("Could not persist adaptive live-price sample: %s", err)

        return {
            "prices": prices,
            "errors": errors,
            "updated_at": updated_at,
            "live_data_available": True,
            "price_details": price_details,
            "live_source_by_currency": live_source_by_currency,
            "local_interval_seconds": self.local_interval_seconds,
            "public_interval_seconds": self.public_interval_seconds,
        }

    def _read_entity_source(
        self, source: dict[str, Any], prices: dict[str, float]
    ) -> None:
        entity_id = source[CONF_ENTITY_ID]
        currency = source[CONF_CURRENCY].upper()
        state = self.hass.states.get(entity_id)
        if state is None or state.state in {"unknown", "unavailable", "none", ""}:
            raise ValueError(f"Entity {entity_id} is unavailable")
        value = float(state.state)
        if not isfinite(value) or value <= 0:
            raise ValueError(f"Entity {entity_id} has no positive price")
        prices.setdefault(currency, value)

    async def _read_mempool_source(
        self, source: dict[str, Any], prices: dict[str, float]
    ) -> None:
        base_url = str(source[CONF_BASE_URL]).rstrip("/")
        verify_ssl = bool(source.get(CONF_VERIFY_SSL, True))
        proxy_url = (
            tor_proxy_from_settings(self.settings)
            if mempool_source_uses_tor(source)
            else None
        )
        target_url = f"{base_url}/api/v1/prices"
        async with async_routed_session(
            self.hass,
            target_url=target_url,
            proxy_url=proxy_url,
            allow_local_direct=not mempool_source_uses_tor(source),
            verify_ssl=verify_ssl,
        ) as (session, request_kwargs):
            async with asyncio.timeout(15):
                response = await session.get(target_url, **request_kwargs)
                response.raise_for_status()
                payload = await async_json_limited(response)

        for currency in source.get(CONF_CURRENCIES, []):
            value = payload.get(currency.upper())
            if value is not None:
                numeric = float(value)
                if isfinite(numeric) and numeric > 0:
                    prices.setdefault(currency.upper(), numeric)

    async def _read_public_market_average_source(
        self,
        source: dict[str, Any],
        prices: dict[str, float],
        price_details: dict[str, Any],
    ) -> None:
        """Fetch independent public BTC tickers through Tor and average them.

        The legacy source identifier remains ``kraken`` for configuration
        compatibility, but live pricing now uses a provider consensus. Every
        public provider is routed with ``async_routed_session`` and therefore
        cannot fall back to a direct Clearnet socket. A provider that is
        unavailable or does not support a requested fiat currency is ignored.
        """
        currencies = [
            str(item).upper()
            for item in source.get(CONF_CURRENCIES, [])
            if str(item).upper() not in prices
        ]
        proxy_url = tor_proxy_from_settings(self.settings)

        async def request_json(
            name: str, target_url: str, *, params: dict[str, Any] | None = None
        ) -> Any:
            async with async_routed_session(
                self.hass, target_url=target_url, proxy_url=proxy_url
            ) as (session, request_kwargs):
                async with asyncio.timeout(15):
                    response = await session.get(
                        target_url, params=params, headers={"Accept": "application/json"}, **request_kwargs
                    )
                    response.raise_for_status()
                    return await async_json_limited(response)

        async def fetch_provider(name: str, currency: str) -> tuple[str, str, float]:
            if name == "Kraken":
                target_url = "https://api.kraken.com/0/public/Ticker"
                payload = await request_json(
                    name, target_url, params={"pair": f"XBT{currency}"}
                )
                if payload.get("error"):
                    raise ValueError(", ".join(payload["error"]))
                result = payload.get("result") or {}
                if not result:
                    raise ValueError(f"Kraken returned no ticker for XBT{currency}")
                ticker = next(iter(result.values()))
                value = float(ticker["c"][0])
            elif name == "Coinbase":
                target_url = f"https://api.exchange.coinbase.com/products/BTC-{currency}/ticker"
                payload = await request_json(name, target_url)
                value = float(payload["price"])
            elif name == "Bitstamp":
                target_url = f"https://www.bitstamp.net/api/v2/ticker/btc{currency.lower()}/"
                payload = await request_json(name, target_url)
                value = float(payload["last"])
            elif name == "CoinGecko":
                target_url = "https://api.coingecko.com/api/v3/simple/price"
                payload = await request_json(
                    name,
                    target_url,
                    params={"ids": "bitcoin", "vs_currencies": currency.lower(), "precision": "full"},
                )
                value = float((payload.get("bitcoin") or {})[currency.lower()])
            else:
                raise ValueError(f"Unknown public provider {name}")
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} returned an invalid BTC/{currency} ticker")
            return name, target_url, value

        provider_names = ("Kraken", "Coinbase", "Bitstamp", "CoinGecko")
        any_success = False
        failures: list[str] = []
        for currency in currencies:
            raw_results = await asyncio.gather(
                *(fetch_provider(name, currency) for name in provider_names),
                return_exceptions=True,
            )
            valid: list[tuple[str, str, float]] = []
            provider_rows: list[dict[str, Any]] = []
            for name, result in zip(provider_names, raw_results, strict=True):
                if isinstance(result, Exception):
                    failures.append(f"{name} {currency}: {result}")
                    provider_rows.append({
                        "name": name,
                        "price": None,
                        "used": False,
                        "status": "unavailable",
                    })
                    continue
                provider, target_url, value = result
                valid.append((provider, target_url, value))
                provider_rows.append({
                    "name": provider,
                    "target": target_url.split("/", 3)[2],
                    "price": value,
                    "used": True,
                    "status": "ok",
                })

            # A wildly wrong provider must not drag the arithmetic mean with it.
            # With three or more valid quotes, reject values more than 5% away
            # from the median; the displayed price is the arithmetic mean of the
            # remaining independent quotes.
            accepted = list(valid)
            excluded: list[str] = []
            if len(valid) >= 3:
                sorted_values = sorted(item[2] for item in valid)
                mid = len(sorted_values) // 2
                median = (
                    sorted_values[mid]
                    if len(sorted_values) % 2
                    else (sorted_values[mid - 1] + sorted_values[mid]) / 2.0
                )
                accepted = [item for item in valid if abs(item[2] - median) / median <= 0.05]
                if len(accepted) < 2:
                    accepted = list(valid)
                excluded = [item[0] for item in valid if item not in accepted]
                for row in provider_rows:
                    if row.get("name") in excluded:
                        row["used"] = False
                        row["status"] = "outlier"

            if not accepted:
                continue
            mean_value = sum(item[2] for item in accepted) / len(accepted)
            prices.setdefault(currency, mean_value)
            any_success = True
            spread_pct = 0.0
            if len(accepted) > 1:
                values = [item[2] for item in accepted]
                spread_pct = ((max(values) - min(values)) / mean_value) * 100.0
            price_details[currency] = {
                "method": "arithmetic_mean",
                "price": mean_value,
                "source_count": len(accepted),
                "available_source_count": len(valid),
                "providers": provider_rows,
                "excluded_outliers": excluded,
                "spread_pct": spread_pct,
                "route": "tor",
            }
            if len(accepted) == 1:
                failures.append(
                    f"Public market average degraded for {currency}: only {accepted[0][0]} was available"
                )

        if not any_success:
            raise ValueError("; ".join(failures) or "No public BTC ticker provider is available")

