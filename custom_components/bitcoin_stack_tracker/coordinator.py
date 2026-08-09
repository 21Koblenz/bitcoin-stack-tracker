"""Price update coordinator for Bitcoin Stack Tracker."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from math import isfinite
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
    CONF_VERIFY_SSL,
    DEFAULT_UPDATE_INTERVAL,
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
        interval = int(settings.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=interval),
            always_update=False,
        )

    @property
    def settings(self) -> dict[str, Any]:
        """Return the effective config entry settings."""
        return {**self.entry.data, **self.entry.options}

    async def _async_update_data(self) -> dict[str, Any]:
        prices: dict[str, float] = {}
        errors: list[str] = []
        price_details: dict[str, Any] = {}

        for source in self.settings.get(CONF_SOURCES, []):
            source_type = source.get(CONF_SOURCE_TYPE)
            source_currencies = (
                [str(source.get(CONF_CURRENCY, "")).upper()]
                if source_type == SOURCE_ENTITY
                else [str(item).upper() for item in source.get(CONF_CURRENCIES, [])]
            )
            # Sources are ordered by priority. Do not contact a later fallback
            # when every one of its currencies already has a live price.
            if source_currencies and all(
                currency in prices for currency in source_currencies
            ):
                continue
            try:
                if source_type == SOURCE_ENTITY:
                    self._read_entity_source(source, prices)
                elif source_type == SOURCE_MEMPOOL:
                    await self._read_mempool_source(source, prices)
                elif source_type == SOURCE_KRAKEN:
                    await self._read_public_market_average_source(source, prices, price_details)
            except (ClientError, asyncio.TimeoutError, ValueError) as err:
                errors.append(f"{source_type}: {err}")

        if not prices:
            # Replace any previous live value with an explicitly offline result.
            # Cached daily history remains in BitcoinHistoryStore and the dashboard
            # stays usable, but no stale value is presented as a current live price.
            return {
                "prices": {},
                "errors": errors or ["No live Bitcoin price is available"],
                "updated_at": dt_util.utcnow().isoformat(),
                "live_data_available": False,
                "price_details": price_details,
            }

        updated_at = dt_util.utcnow().isoformat()
        if self.history_store is not None:
            try:
                await self.history_store.async_add_price_samples(prices, updated_at)
            except (OSError, ValueError) as err:
                # Live pricing must not fail merely because fine-grained local
                # chart sampling could not be persisted.
                _LOGGER.warning("Could not persist adaptive live-price sample: %s", err)

        return {
            "prices": prices,
            "errors": errors,
            "updated_at": updated_at,
            "live_data_available": True,
            "price_details": price_details,
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

