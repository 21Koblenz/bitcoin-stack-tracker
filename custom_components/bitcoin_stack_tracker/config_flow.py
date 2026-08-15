"""UI configuration for Bitcoin Stack Tracker."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from functools import partial
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from aiohttp import ClientError
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .const import (
    ALL_DEPOTS,
    CONF_BASE_URL,
    CONF_CURRENCIES,
    CONF_CURRENCY,
    CONF_ENTITY_ID,
    CONF_ENCRYPTION_ENABLED,
    CONF_ENCRYPTION_MODE,
    CONF_SETUP_TOKEN,
    CONF_VAULT_PASSWORD,
    CONF_VAULT_PASSWORD_CONFIRM,
    CONF_GOAL_BTC,
    CONF_HISTORY_AUTO_SYNC,
    CONF_HISTORY_DAYS,
    CONF_HISTORY_ENABLED,
    CONF_HISTORY_TOR_PROXY,
    CONF_LONG_TERM_DAYS,
    CONF_MEMPOOL_OWN_INSTANCE,
    CONF_MEMPOOL_ROUTE,
    CONF_TAX_NOTE,
    CONF_SOURCE_TYPE,
    CONF_SOURCES,
    CONF_UPDATE_INTERVAL,
    CONF_PUBLIC_UPDATE_INTERVAL,
    CONF_VERIFY_SSL,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_HISTORY_TOR_PROXY,
    DEFAULT_KRAKEN_CURRENCIES,
    DEFAULT_LONG_TERM_DAYS,
    DEFAULT_TAX_NOTE,
    DEFAULT_MEMPOOL_URL,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_PUBLIC_UPDATE_INTERVAL,
    DOMAIN,
    KRAKEN_CURRENCIES,
    MAX_HISTORY_DAYS,
    MAX_LONG_TERM_DAYS,
    MAX_UPDATE_INTERVAL,
    MAX_PUBLIC_UPDATE_INTERVAL,
    MIN_HISTORY_DAYS,
    MIN_LONG_TERM_DAYS,
    MIN_UPDATE_INTERVAL,
    MIN_PUBLIC_UPDATE_INTERVAL,
    MEMPOOL_ROUTE_DIRECT,
    MEMPOOL_ROUTE_TOR,
    SOURCE_ENTITY,
    SOURCE_KRAKEN,
    SOURCE_MEMPOOL,
    UNIT_BTC,
    UNIT_SATS,
)
from .crypto import PasswordValidationError, validate_new_password
from .fifo import fifo_result
from .helpers import configured_currencies, effective_settings, parse_timestamp
from .history import async_sync_history
from .models import amount_to_btc, btc_string, decimal_value, money_string
from .http_limits import async_json_limited
from .network import (
    async_routed_session,
    automatic_mempool_route,
    mempool_source_uses_tor,
    tor_proxy_from_settings,
    validate_mempool_route,
)
from .security import ENCRYPTION_NONE, ENCRYPTION_PASSWORD
from .storage import BitcoinLedgerStore

_LOGGER = logging.getLogger(__name__)

CONF_GOAL = "goal"
CONF_GOAL_UNIT = "goal_unit"
CONF_GOAL_NAME = "goal_name"
CONF_GOAL_ID = "goal_id"
CONF_AMOUNT = "amount"
CONF_AMOUNT_UNIT = "amount_unit"
CONF_PRICE = "price"
CONF_FEE = "fee"
CONF_TIMESTAMP = "timestamp"
CONF_TIMESTAMP_TEXT = "timestamp_text"
CONF_NOTE = "note"
CONF_LEDGER_ENTRY_ID = "ledger_entry_id"
CONF_SOURCE_INDEX = "source_index"
CONF_DEPOT_ID = "depot_id"
CONF_DEPOT_NAME = "depot_name"
CONF_STORAGE_REVISION = "storage_revision"
CONF_DELIMITER = "delimiter"

SOURCE_OPTIONS = [
    {"value": SOURCE_KRAKEN, "label": "Marktmittel (4 öffentliche APIs via Tor)"},
    {"value": SOURCE_MEMPOOL, "label": "mempool"},
    {"value": SOURCE_ENTITY, "label": "Home Assistant"},
]
MEMPOOL_ROUTE_OPTIONS = [
    {"value": MEMPOOL_ROUTE_TOR, "label": "Tor / SOCKS5"},
    {"value": MEMPOOL_ROUTE_DIRECT, "label": "Direkt zur eigenen Instanz"},
]
UNIT_OPTIONS = [
    {"value": UNIT_BTC, "label": "BTC"},
    {"value": UNIT_SATS, "label": "sats"},
]


def _select(options: list[Any], *, multiple: bool = False, custom_value: bool = False) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            multiple=multiple,
            custom_value=custom_value,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


async def _async_validate_kraken(
    hass: HomeAssistant, currencies: list[str], settings: dict[str, Any]
) -> None:
    """Validate the public live-price consensus through Tor only.

    The function name is retained for config-flow compatibility with the legacy
    ``kraken`` source id. A currency is accepted when at least two independent
    public providers answer with a positive BTC price.
    """
    if not currencies:
        raise ValueError("No currency selected")
    proxy_url = tor_proxy_from_settings(settings)

    async def probe(name: str, currency: str) -> float:
        if name == "Kraken":
            url = "https://api.kraken.com/0/public/Ticker"
            params = {"pair": f"XBT{currency}"}
        elif name == "Coinbase":
            url = f"https://api.exchange.coinbase.com/products/BTC-{currency}/ticker"
            params = None
        elif name == "Bitstamp":
            url = f"https://www.bitstamp.net/api/v2/ticker/btc{currency.lower()}/"
            params = None
        else:
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {"ids": "bitcoin", "vs_currencies": currency.lower(), "precision": "full"}
        async with async_routed_session(hass, target_url=url, proxy_url=proxy_url) as (session, request_kwargs):
            async with asyncio.timeout(15):
                response = await session.get(url, params=params, **request_kwargs)
                response.raise_for_status()
                payload = await async_json_limited(response)
        if name == "Kraken":
            if payload.get("error") or not payload.get("result"):
                raise ValueError(f"Kraken ticker unavailable for {currency}")
            value = float(next(iter(payload["result"].values()))["c"][0])
        elif name == "Coinbase":
            value = float(payload["price"])
        elif name == "Bitstamp":
            value = float(payload["last"])
        else:
            value = float((payload.get("bitcoin") or {})[currency.lower()])
        if value <= 0:
            raise ValueError(f"{name} ticker unavailable for {currency}")
        return value

    for currency in currencies:
        results = await asyncio.gather(
            *(probe(name, currency) for name in ("Kraken", "Coinbase", "Bitstamp", "CoinGecko")),
            return_exceptions=True,
        )
        if sum(not isinstance(result, Exception) for result in results) < 2:
            raise ValueError(f"Fewer than two public BTC/{currency} ticker providers are available")


async def _async_mempool_currencies(
    hass: HomeAssistant,
    source: dict[str, Any],
    settings: dict[str, Any],
) -> set[str]:
    base_url = str(source[CONF_BASE_URL]).rstrip("/")
    verify_ssl = bool(source.get(CONF_VERIFY_SSL, True))
    proxy_url = (
        tor_proxy_from_settings(settings)
        if mempool_source_uses_tor(source)
        else None
    )
    target_url = f"{base_url}/api/v1/prices"
    async with async_routed_session(
        hass,
        target_url=target_url,
        proxy_url=proxy_url,
        allow_local_direct=not mempool_source_uses_tor(source),
        verify_ssl=verify_ssl,
    ) as (session, request_kwargs):
        async with asyncio.timeout(15):
            response = await session.get(
                target_url, **request_kwargs
            )
            response.raise_for_status()
            payload = await async_json_limited(response)
    return {
        str(key).upper()
        for key, value in payload.items()
        if str(key).upper() != "TIME" and isinstance(value, (int, float)) and value > 0
    }


class BitcoinStackTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create a Bitcoin Stack Tracker config entry."""

    VERSION = 10

    def __init__(self) -> None:
        self._base: dict[str, Any] = {}
        self._vault_password: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            tor_proxy = DEFAULT_HISTORY_TOR_PROXY
            goal_btc = amount_to_btc(user_input[CONF_GOAL], user_input[CONF_GOAL_UNIT])
            self._base = {
                CONF_NAME: user_input[CONF_NAME].strip(),
                CONF_GOAL_BTC: float(goal_btc),
                CONF_UPDATE_INTERVAL: int(user_input[CONF_UPDATE_INTERVAL]),
                CONF_HISTORY_ENABLED: bool(user_input[CONF_HISTORY_ENABLED]),
                CONF_HISTORY_AUTO_SYNC: bool(user_input[CONF_HISTORY_AUTO_SYNC]),
                CONF_HISTORY_DAYS: 0,
                CONF_HISTORY_TOR_PROXY: tor_proxy,
                CONF_SOURCE_TYPE: user_input[CONF_SOURCE_TYPE],
                CONF_ENCRYPTION_MODE: (
                    ENCRYPTION_PASSWORD
                    if bool(user_input[CONF_ENCRYPTION_ENABLED])
                    else ENCRYPTION_NONE
                ),
            }
            if bool(user_input[CONF_ENCRYPTION_ENABLED]):
                return await self.async_step_encryption_password()
            return await getattr(self, f"async_step_{user_input[CONF_SOURCE_TYPE]}")()

        return self.async_show_form(step_id="user", data_schema=self._user_schema())

    def _user_schema(self, defaults: dict[str, Any] | None = None) -> vol.Schema:
        values = defaults or {}
        return vol.Schema({
            vol.Required(CONF_NAME, default=values.get(CONF_NAME, "Bitcoin Stack")): str,
            vol.Optional(CONF_GOAL, default=values.get(CONF_GOAL, 1)): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Optional(CONF_GOAL_UNIT, default=values.get(CONF_GOAL_UNIT, UNIT_BTC)): _select(UNIT_OPTIONS),
            vol.Required(CONF_SOURCE_TYPE, default=values.get(CONF_SOURCE_TYPE, SOURCE_KRAKEN)): _select(SOURCE_OPTIONS),
            vol.Required(CONF_ENCRYPTION_ENABLED, default=values.get(CONF_ENCRYPTION_ENABLED, True)): bool,
            vol.Optional(CONF_UPDATE_INTERVAL, default=values.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL, step=30, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="s")
            ),
            vol.Required(CONF_HISTORY_ENABLED, default=values.get(CONF_HISTORY_ENABLED, True)): bool,
            vol.Required(CONF_HISTORY_AUTO_SYNC, default=values.get(CONF_HISTORY_AUTO_SYNC, True)): bool,
        })

    async def async_step_encryption_password(
        self, user_input: dict[str, Any] | None = None
    ):
        errors: dict[str, str] = {}
        if user_input is not None:
            password = str(user_input[CONF_VAULT_PASSWORD])
            confirmation = str(user_input[CONF_VAULT_PASSWORD_CONFIRM])
            if password != confirmation:
                errors["base"] = "password_mismatch"
            else:
                try:
                    validate_new_password(password)
                except PasswordValidationError:
                    errors["base"] = "weak_password"
                else:
                    self._vault_password = password
                    return await getattr(
                        self, f"async_step_{self._base[CONF_SOURCE_TYPE]}"
                    )()
        password_selector = selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        )
        return self.async_show_form(
            step_id="encryption_password",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_VAULT_PASSWORD): password_selector,
                    vol.Required(CONF_VAULT_PASSWORD_CONFIRM): password_selector,
                }
            ),
            errors=errors,
        )

    async def async_step_kraken(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            currencies = [item.upper() for item in user_input[CONF_CURRENCIES]]
            try:
                await _async_validate_kraken(self.hass, currencies, self._base)
            except (ClientError, asyncio.TimeoutError, ValueError):
                errors["base"] = "cannot_connect"
            else:
                return self._create_entry({CONF_SOURCE_TYPE: SOURCE_KRAKEN, CONF_CURRENCIES: currencies})
        return self.async_show_form(
            step_id="kraken",
            data_schema=vol.Schema({vol.Required(CONF_CURRENCIES, default=DEFAULT_KRAKEN_CURRENCIES): _select(KRAKEN_CURRENCIES, multiple=True)}),
            errors=errors,
        )

    async def async_step_mempool(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            base_url = str(user_input[CONF_BASE_URL]).rstrip("/")
            verify_ssl = bool(user_input[CONF_VERIFY_SSL])
            own_instance = bool(user_input[CONF_MEMPOOL_OWN_INSTANCE])
            route = automatic_mempool_route(
                base_url=base_url, own_instance=own_instance
            )
            currencies = [item.strip().upper() for item in str(user_input[CONF_CURRENCIES]).split(",") if item.strip()]
            source = {
                CONF_SOURCE_TYPE: SOURCE_MEMPOOL,
                CONF_BASE_URL: base_url,
                CONF_VERIFY_SSL: verify_ssl,
                CONF_CURRENCIES: currencies,
                CONF_MEMPOOL_OWN_INSTANCE: own_instance,
                CONF_MEMPOOL_ROUTE: route,
            }
            try:
                validate_mempool_route(
                    base_url=base_url, own_instance=own_instance, route=route
                )
            except ValueError:
                errors["base"] = "invalid_mempool_route"
            if not errors:
                try:
                    available = await _async_mempool_currencies(
                        self.hass, source, self._base
                    )
                    if not currencies or any(currency not in available for currency in currencies):
                        errors["base"] = "unsupported_currency"
                    else:
                        return self._create_entry(source)
                except (ClientError, asyncio.TimeoutError, ValueError):
                    errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="mempool",
            data_schema=vol.Schema({
                vol.Required(CONF_BASE_URL, default=DEFAULT_MEMPOOL_URL): str,
                vol.Required(CONF_VERIFY_SSL, default=True): bool,
                vol.Required(CONF_CURRENCIES, default="EUR,USD"): str,
                vol.Required(CONF_MEMPOOL_OWN_INSTANCE, default=False): bool,
            }),
            errors=errors,
        )

    async def async_step_entity(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self._create_entry({
                CONF_SOURCE_TYPE: SOURCE_ENTITY,
                CONF_ENTITY_ID: user_input[CONF_ENTITY_ID],
                CONF_CURRENCY: user_input[CONF_CURRENCY].strip().upper(),
            })
        return self.async_show_form(
            step_id="entity",
            data_schema=vol.Schema({
                vol.Required(CONF_ENTITY_ID): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_CURRENCY, default="EUR"): str,
            }),
        )

    def _create_entry(self, source: dict[str, Any]):
        name = self._base[CONF_NAME]
        data = {
            CONF_NAME: name,
            CONF_UPDATE_INTERVAL: self._base[CONF_UPDATE_INTERVAL],
            CONF_HISTORY_ENABLED: self._base[CONF_HISTORY_ENABLED],
            CONF_HISTORY_AUTO_SYNC: self._base[CONF_HISTORY_AUTO_SYNC],
            CONF_HISTORY_DAYS: self._base[CONF_HISTORY_DAYS],
            CONF_HISTORY_TOR_PROXY: self._base[CONF_HISTORY_TOR_PROXY],
            CONF_ENCRYPTION_MODE: self._base.get(
                CONF_ENCRYPTION_MODE, ENCRYPTION_NONE
            ),
            CONF_SOURCES: [source],
        }
        if self._vault_password:
            token = uuid4().hex
            data[CONF_SETUP_TOKEN] = token
            self.hass.data.setdefault(DOMAIN, {}).setdefault(
                "_pending_passwords", {}
            )[token] = {
                "password": self._vault_password,
                "goal_btc": self._base[CONF_GOAL_BTC],
            }
            self._vault_password = None
        else:
            # Unencrypted mode already stores the ledger in plaintext; retain the
            # legacy field only until async_setup_entry migrates it into the ledger.
            data[CONF_GOAL_BTC] = self._base[CONF_GOAL_BTC]
        return self.async_create_entry(title=name, data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        return BitcoinStackTrackerOptionsFlow()


class BitcoinStackTrackerOptionsFlow(config_entries.OptionsFlowWithReload):
    """Manage transactions, depots, goals, history, and price sources."""

    @property
    def settings(self) -> dict[str, Any]:
        return effective_settings(self.config_entry)

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        runtime = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        if isinstance(runtime, dict) and runtime["storage"].is_locked:
            return self.async_abort(reason="vault_locked_use_dashboard")
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_purchase", "add_sale", "add_stack", "delete_ledger_entry",
                "add_depot", "delete_depot", "add_goal", "edit_goal", "delete_goal",
                "tax_settings", "history_settings", "sync_history", "settings",
                "add_source", "delete_source",
            ],
        )

    async def _storage(self) -> BitcoinLedgerStore:
        runtime = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        if runtime is not None:
            return runtime["storage"]
        security = BitcoinSecurityStore(self.hass, self.config_entry.entry_id)
        await security.async_load()
        storage = BitcoinLedgerStore(
            self.hass, self.config_entry.entry_id, security
        )
        await storage.async_load()
        return storage

    def _finish(self, settings: dict[str, Any] | None = None):
        return self.async_create_entry(title="", data=settings or self.settings)

    def _finish_storage_change(self):
        updated = deepcopy(self.settings)
        updated[CONF_STORAGE_REVISION] = int(updated.get(CONF_STORAGE_REVISION, 0)) + 1
        return self._finish(updated)

    def _notify(self) -> None:
        runtime = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        if runtime is not None:
            coordinator = runtime["coordinator"]
            coordinator.async_set_updated_data(coordinator.data or {"prices": {}, "errors": [], "updated_at": None})

    async def _depot_options(self, include_all: bool = False) -> list[dict[str, str]]:
        storage = await self._storage()
        options = [{"value": str(item["id"]), "label": str(item["name"])} for item in storage.depots]
        if include_all:
            options.insert(0, {"value": ALL_DEPOTS, "label": "All depots / Alle Depots"})
        return options

    async def async_step_add_purchase(self, user_input: dict[str, Any] | None = None):
        return await self._transaction_step("add_purchase", "purchase", user_input)

    async def async_step_add_sale(self, user_input: dict[str, Any] | None = None):
        return await self._transaction_step("add_sale", "sale", user_input)

    async def _transaction_step(self, step_id: str, kind: str, user_input: dict[str, Any] | None):
        currencies = configured_currencies(self.settings)
        depots = await self._depot_options()
        errors: dict[str, str] = {}
        if user_input is not None:
            amount_btc = amount_to_btc(user_input[CONF_AMOUNT], user_input[CONF_AMOUNT_UNIT])
            if amount_btc <= 0 or decimal_value(user_input[CONF_PRICE]) <= 0:
                errors["base"] = "invalid_amount"
            else:
                storage = await self._storage()
                timestamp = parse_timestamp(user_input.get(CONF_TIMESTAMP_TEXT) or user_input.get(CONF_TIMESTAMP))
                if kind == "sale":
                    candidate = {
                        "id": "candidate_sale", "type": "sale", "timestamp": timestamp.isoformat(),
                        "depot_id": user_input[CONF_DEPOT_ID], "amount_btc": btc_string(amount_btc),
                        "currency": user_input[CONF_CURRENCY].upper(),
                        "price": money_string(decimal_value(user_input[CONF_PRICE])),
                        "fee": money_string(decimal_value(user_input.get(CONF_FEE, 0))), "note": "",
                    }
                    sale_check = await self.hass.async_add_executor_job(
                        partial(
                            fifo_result,
                            storage.entries + [candidate],
                            user_input[CONF_DEPOT_ID],
                            long_term_days=int(
                                storage.tax_settings.get("long_term_days", 365)
                            ),
                        )
                    )
                    if sale_check["oversold_btc"] > 0:
                        errors["base"] = "insufficient_stack"
                    else:
                        await storage.async_add_sale(
                            timestamp=timestamp, amount_btc=amount_btc,
                            currency=user_input[CONF_CURRENCY], price=user_input[CONF_PRICE],
                            fee=user_input.get(CONF_FEE, 0), note=user_input.get(CONF_NOTE, ""),
                            depot_id=user_input[CONF_DEPOT_ID],
                        )
                        self._notify()
                        return self._finish()
                else:
                    await storage.async_add_purchase(
                        timestamp=timestamp, amount_btc=amount_btc,
                        currency=user_input[CONF_CURRENCY], price=user_input[CONF_PRICE],
                        fee=user_input.get(CONF_FEE, 0), note=user_input.get(CONF_NOTE, ""),
                        depot_id=user_input[CONF_DEPOT_ID],
                    )
                    self._notify()
                    return self._finish()
        schema = vol.Schema({
            vol.Required(CONF_DEPOT_ID, default=depots[0]["value"]): _select(depots),
            vol.Required(CONF_AMOUNT): vol.Coerce(float),
            vol.Required(CONF_AMOUNT_UNIT, default=UNIT_BTC): _select(UNIT_OPTIONS),
            vol.Required(CONF_CURRENCY, default=currencies[0] if currencies else "EUR"): _select(currencies or ["EUR"]),
            vol.Required(CONF_PRICE): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Optional(CONF_FEE, default=0): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Optional(CONF_TIMESTAMP): selector.DateTimeSelector(),
            vol.Optional(CONF_TIMESTAMP_TEXT, default=""): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Optional(CONF_NOTE, default=""): str,
        })
        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)

    async def async_step_add_stack(self, user_input: dict[str, Any] | None = None):
        depots = await self._depot_options()
        errors: dict[str, str] = {}
        if user_input is not None:
            amount_btc = amount_to_btc(user_input[CONF_AMOUNT], user_input[CONF_AMOUNT_UNIT])
            if amount_btc <= 0:
                errors["base"] = "invalid_amount"
            else:
                storage = await self._storage()
                await storage.async_add_stack(
                    timestamp=parse_timestamp(user_input.get(CONF_TIMESTAMP_TEXT) or user_input.get(CONF_TIMESTAMP)),
                    amount_btc=amount_btc,
                    note=user_input.get(CONF_NOTE, ""),
                    depot_id=user_input[CONF_DEPOT_ID],
                )
                self._notify()
                return self._finish()
        return self.async_show_form(
            step_id="add_stack",
            data_schema=vol.Schema({
                vol.Required(CONF_DEPOT_ID, default=depots[0]["value"]): _select(depots),
                vol.Required(CONF_AMOUNT): vol.Coerce(float),
                vol.Required(CONF_AMOUNT_UNIT, default=UNIT_BTC): _select(UNIT_OPTIONS),
                vol.Optional(CONF_TIMESTAMP): selector.DateTimeSelector(),
                vol.Optional(CONF_TIMESTAMP_TEXT, default=""): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Optional(CONF_NOTE, default=""): str,
            }),
            errors=errors,
        )

    async def async_step_delete_ledger_entry(self, user_input: dict[str, Any] | None = None):
        storage = await self._storage()
        entries = storage.entries
        if not entries:
            return self.async_abort(reason="no_ledger_entries")
        options = [{
            "value": item["id"],
            "label": f"{str(item.get('timestamp', ''))[:10]} · {item.get('amount_btc', '0')} BTC · {item.get('type', 'entry')} · {item.get('depot_id', 'main')}",
        } for item in entries]
        if user_input is not None:
            item_id = user_input[CONF_LEDGER_ENTRY_ID]
            remaining = [item for item in entries if item.get("id") != item_id]
            remaining_check = await self.hass.async_add_executor_job(
                partial(
                    fifo_result,
                    remaining,
                    long_term_days=int(
                        storage.tax_settings.get("long_term_days", 365)
                    ),
                )
            )
            if remaining_check["oversold_btc"] > 0:
                return self.async_show_form(
                    step_id="delete_ledger_entry",
                    data_schema=vol.Schema(
                        {vol.Required(CONF_LEDGER_ENTRY_ID): _select(options)}
                    ),
                    errors={"base": "delete_breaks_fifo"},
                )
            await storage.async_delete(item_id)
            self._notify()
            return self._finish()
        return self.async_show_form(step_id="delete_ledger_entry", data_schema=vol.Schema({vol.Required(CONF_LEDGER_ENTRY_ID): _select(options)}))

    async def async_step_add_depot(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                storage = await self._storage()
                await storage.async_add_depot(user_input[CONF_DEPOT_NAME])
            except ValueError:
                errors["base"] = "invalid_name"
            else:
                return self._finish_storage_change()
        return self.async_show_form(step_id="add_depot", data_schema=vol.Schema({vol.Required(CONF_DEPOT_NAME): str}), errors=errors)

    async def async_step_delete_depot(self, user_input: dict[str, Any] | None = None):
        storage = await self._storage()
        options = [{"value": str(item["id"]), "label": str(item["name"])} for item in storage.depots if item["id"] != "main"]
        if not options:
            return self.async_abort(reason="no_depots_to_delete")
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await storage.async_delete_depot(user_input[CONF_DEPOT_ID])
            except ValueError:
                errors["base"] = "depot_not_empty"
            else:
                return self._finish_storage_change()
        return self.async_show_form(step_id="delete_depot", data_schema=vol.Schema({vol.Required(CONF_DEPOT_ID): _select(options)}), errors=errors)

    async def async_step_add_goal(self, user_input: dict[str, Any] | None = None):
        depots = await self._depot_options(include_all=True)
        errors: dict[str, str] = {}
        if user_input is not None:
            goal_btc = amount_to_btc(user_input[CONF_GOAL], user_input[CONF_GOAL_UNIT])
            if goal_btc <= 0:
                errors["base"] = "invalid_amount"
            else:
                storage = await self._storage()
                await storage.async_add_goal(
                    name=user_input[CONF_GOAL_NAME],
                    amount_btc=goal_btc,
                    depot_id=user_input[CONF_DEPOT_ID],
                    currency=user_input[CONF_CURRENCY],
                )
                return self._finish_storage_change()
        currencies = configured_currencies(self.settings) or ["EUR"]
        return self.async_show_form(
            step_id="add_goal",
            description_placeholders={"sensor_count": "5"},
            data_schema=vol.Schema({
                vol.Required(CONF_GOAL_NAME): str,
                vol.Required(CONF_GOAL): vol.All(vol.Coerce(float), vol.Range(min=0)),
                vol.Required(CONF_GOAL_UNIT, default=UNIT_BTC): _select(UNIT_OPTIONS),
                vol.Required(CONF_DEPOT_ID, default=ALL_DEPOTS): _select(depots),
                vol.Required(CONF_CURRENCY, default=currencies[0]): _select(currencies),
            }),
            errors=errors,
        )

    async def async_step_edit_goal(self, user_input: dict[str, Any] | None = None):
        storage = await self._storage()
        if not storage.goals:
            return self.async_abort(reason="no_goals")
        options = [
            {
                "value": str(item["id"]),
                "label": f"{item['name']} · {item['amount_btc']} BTC · {item.get('currency', 'EUR')}",
            }
            for item in storage.goals
        ]
        if user_input is not None:
            self._selected_goal_id = str(user_input[CONF_GOAL_ID])
            return await self.async_step_edit_goal_details()
        return self.async_show_form(
            step_id="edit_goal",
            data_schema=vol.Schema({vol.Required(CONF_GOAL_ID): _select(options)}),
        )

    async def async_step_edit_goal_details(self, user_input: dict[str, Any] | None = None):
        storage = await self._storage()
        selected = next(
            (item for item in storage.goals if str(item["id"]) == str(getattr(self, "_selected_goal_id", ""))),
            None,
        )
        if selected is None:
            return self.async_abort(reason="no_goals")
        depots = await self._depot_options(include_all=True)
        currencies = configured_currencies(self.settings) or ["EUR"]
        errors: dict[str, str] = {}
        if user_input is not None:
            goal_btc = amount_to_btc(user_input[CONF_GOAL], user_input[CONF_GOAL_UNIT])
            if goal_btc <= 0:
                errors["base"] = "invalid_amount"
            else:
                updated = await storage.async_update_goal(
                    str(selected["id"]),
                    name=user_input[CONF_GOAL_NAME],
                    amount_btc=goal_btc,
                    depot_id=user_input[CONF_DEPOT_ID],
                    currency=user_input[CONF_CURRENCY],
                )
                if updated:
                    return self._finish_storage_change()
                errors["base"] = "goal_not_found"
        return self.async_show_form(
            step_id="edit_goal_details",
            description_placeholders={"sensor_count": "5"},
            data_schema=vol.Schema({
                vol.Required(CONF_GOAL_NAME, default=str(selected.get("name", ""))): str,
                vol.Required(CONF_GOAL, default=float(decimal_value(selected.get("amount_btc")))): vol.All(vol.Coerce(float), vol.Range(min=0)),
                vol.Required(CONF_GOAL_UNIT, default=UNIT_BTC): _select(UNIT_OPTIONS),
                vol.Required(CONF_DEPOT_ID, default=str(selected.get("depot_id", ALL_DEPOTS))): _select(depots),
                vol.Required(CONF_CURRENCY, default=str(selected.get("currency", currencies[0]))): _select(currencies),
            }),
            errors=errors,
        )

    async def async_step_tax_settings(self, user_input: dict[str, Any] | None = None):
        storage = await self._storage()
        current = storage.tax_settings
        if user_input is not None:
            await storage.async_set_tax_settings(
                long_term_days=int(user_input[CONF_LONG_TERM_DAYS]),
                note=str(user_input[CONF_TAX_NOTE]),
            )
            self._notify()
            return self._finish()
        return self.async_show_form(
            step_id="tax_settings",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_LONG_TERM_DAYS,
                    default=int(current.get(CONF_LONG_TERM_DAYS, DEFAULT_LONG_TERM_DAYS)),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_LONG_TERM_DAYS, max=MAX_LONG_TERM_DAYS, step=1,
                        mode=selector.NumberSelectorMode.BOX, unit_of_measurement="d",
                    )
                ),
                vol.Optional(
                    CONF_TAX_NOTE,
                    default=str(current.get("note", DEFAULT_TAX_NOTE)),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
            }),
        )

    async def async_step_delete_goal(self, user_input: dict[str, Any] | None = None):
        storage = await self._storage()
        if not storage.goals:
            return self.async_abort(reason="no_goals")
        options = [{"value": str(item["id"]), "label": f"{item['name']} · {item['amount_btc']} BTC"} for item in storage.goals]
        if user_input is not None:
            await storage.async_delete_goal(user_input[CONF_GOAL_ID])
            return self._finish_storage_change()
        return self.async_show_form(step_id="delete_goal", data_schema=vol.Schema({vol.Required(CONF_GOAL_ID): _select(options)}))

    async def async_step_export_csv(self, user_input: dict[str, Any] | None = None):
        """Do not leave a durable plaintext copy of the encrypted ledger on disk."""
        return self.async_abort(reason="csv_export_ephemeral_only")

    async def async_step_settings(self, user_input: dict[str, Any] | None = None):
        current = self.settings
        if user_input is not None:
            updated = deepcopy(current)
            updated[CONF_UPDATE_INTERVAL] = int(user_input[CONF_UPDATE_INTERVAL])
            updated[CONF_PUBLIC_UPDATE_INTERVAL] = int(user_input[CONF_PUBLIC_UPDATE_INTERVAL])
            return self._finish(updated)
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema({
                vol.Required(CONF_UPDATE_INTERVAL, default=current.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL, step=30, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="s")
                ),
                vol.Required(CONF_PUBLIC_UPDATE_INTERVAL, default=current.get(CONF_PUBLIC_UPDATE_INTERVAL, DEFAULT_PUBLIC_UPDATE_INTERVAL)): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=MIN_PUBLIC_UPDATE_INTERVAL, max=MAX_PUBLIC_UPDATE_INTERVAL, step=30, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="s")
                ),
            }),
        )

    async def async_step_history_settings(self, user_input: dict[str, Any] | None = None):
        current = self.settings
        if user_input is not None:
            updated = deepcopy(current)
            updated[CONF_HISTORY_ENABLED] = bool(user_input[CONF_HISTORY_ENABLED])
            updated[CONF_HISTORY_AUTO_SYNC] = bool(user_input[CONF_HISTORY_AUTO_SYNC])
            updated[CONF_HISTORY_TOR_PROXY] = DEFAULT_HISTORY_TOR_PROXY
            updated[CONF_HISTORY_DAYS] = 0
            return self._finish(updated)
        return self.async_show_form(
            step_id="history_settings",
            data_schema=vol.Schema({
                vol.Required(CONF_HISTORY_ENABLED, default=current.get(CONF_HISTORY_ENABLED, True)): bool,
                vol.Required(CONF_HISTORY_AUTO_SYNC, default=current.get(CONF_HISTORY_AUTO_SYNC, True)): bool,
            }),
        )

    async def async_step_sync_history(self, user_input: dict[str, Any] | None = None):
        runtime = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        if runtime is None:
            return self.async_abort(reason="not_loaded")
        try:
            result = await async_sync_history(
                self.hass,
                self.config_entry,
                runtime["storage"],
                runtime["history_storage"],
            )
        except Exception as err:
            _LOGGER.exception("Manual Bitcoin history synchronization failed")
            await runtime["history_storage"].async_set_sync_status(
                dt_util.utcnow().isoformat(), [str(err)]
            )
            self._notify()
            return self.async_abort(reason="history_sync_failed")
        self._notify()
        if result.get("errors"):
            return self.async_abort(
                reason="history_synced_with_errors",
                description_placeholders={"errors": " | ".join(result["errors"])},
            )
        return self.async_abort(reason="history_synced")

    async def async_step_add_source(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return await getattr(self, f"async_step_add_{user_input[CONF_SOURCE_TYPE]}")()
        return self.async_show_form(step_id="add_source", data_schema=vol.Schema({vol.Required(CONF_SOURCE_TYPE): _select(SOURCE_OPTIONS)}))

    def _append_source(self, source: dict[str, Any]):
        updated = deepcopy(self.settings)
        sources = updated.setdefault(CONF_SOURCES, [])
        # Overlapping currencies are intentional: the first successful source is
        # used for the live price, while later public-average or mempool sources can act
        # as fallbacks and provide historical data for an entity-based source.
        if any(existing == source for existing in sources):
            return None
        sources.append(source)
        return self._finish(updated)

    async def async_step_add_kraken(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            currencies = [item.upper() for item in user_input[CONF_CURRENCIES]]
            try:
                await _async_validate_kraken(self.hass, currencies, self.settings)
            except (ClientError, asyncio.TimeoutError, ValueError):
                errors["base"] = "cannot_connect"
            else:
                result = self._append_source({CONF_SOURCE_TYPE: SOURCE_KRAKEN, CONF_CURRENCIES: currencies})
                if result is None:
                    errors["base"] = "duplicate_currency"
                else:
                    return result
        return self.async_show_form(step_id="add_kraken", data_schema=vol.Schema({vol.Required(CONF_CURRENCIES): _select(KRAKEN_CURRENCIES, multiple=True)}), errors=errors)

    async def async_step_add_mempool(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            currencies = [item.strip().upper() for item in user_input[CONF_CURRENCIES].split(",") if item.strip()]
            base_url = user_input[CONF_BASE_URL].rstrip("/")
            verify_ssl = bool(user_input[CONF_VERIFY_SSL])
            own_instance = bool(user_input[CONF_MEMPOOL_OWN_INSTANCE])
            route = automatic_mempool_route(
                base_url=base_url, own_instance=own_instance
            )
            source = {
                CONF_SOURCE_TYPE: SOURCE_MEMPOOL,
                CONF_BASE_URL: base_url,
                CONF_VERIFY_SSL: verify_ssl,
                CONF_CURRENCIES: currencies,
                CONF_MEMPOOL_OWN_INSTANCE: own_instance,
                CONF_MEMPOOL_ROUTE: route,
            }
            try:
                validate_mempool_route(
                    base_url=base_url, own_instance=own_instance, route=route
                )
            except ValueError:
                errors["base"] = "invalid_mempool_route"
            if not errors:
                try:
                    available = await _async_mempool_currencies(
                        self.hass, source, self.settings
                    )
                except (ClientError, asyncio.TimeoutError, ValueError):
                    errors["base"] = "cannot_connect"
                else:
                    if not currencies or any(currency not in available for currency in currencies):
                        errors["base"] = "unsupported_currency"
                    else:
                        result = self._append_source(source)
                        if result is None:
                            errors["base"] = "duplicate_currency"
                        else:
                            return result
        return self.async_show_form(step_id="add_mempool", data_schema=vol.Schema({
            vol.Required(CONF_BASE_URL, default=DEFAULT_MEMPOOL_URL): str,
            vol.Required(CONF_VERIFY_SSL, default=True): bool,
            vol.Required(CONF_CURRENCIES, default="EUR"): str,
            vol.Required(CONF_MEMPOOL_OWN_INSTANCE, default=False): bool,
        }), errors=errors)

    async def async_step_add_entity(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            result = self._append_source({CONF_SOURCE_TYPE: SOURCE_ENTITY, CONF_ENTITY_ID: user_input[CONF_ENTITY_ID], CONF_CURRENCY: user_input[CONF_CURRENCY].upper()})
            if result is None:
                errors["base"] = "duplicate_currency"
            else:
                return result
        return self.async_show_form(step_id="add_entity", data_schema=vol.Schema({
            vol.Required(CONF_ENTITY_ID): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Required(CONF_CURRENCY, default="EUR"): str,
        }), errors=errors)

    async def async_step_delete_source(self, user_input: dict[str, Any] | None = None):
        sources = self.settings.get(CONF_SOURCES, [])
        if len(sources) <= 1:
            return self.async_abort(reason="last_source")
        options = []
        for index, source in enumerate(sources):
            currencies = source.get(CONF_CURRENCY, "") if source.get(CONF_SOURCE_TYPE) == SOURCE_ENTITY else ", ".join(source.get(CONF_CURRENCIES, []))
            options.append({"value": str(index), "label": f"{source.get(CONF_SOURCE_TYPE)} · {currencies}"})
        if user_input is not None:
            updated = deepcopy(self.settings)
            updated[CONF_SOURCES].pop(int(user_input[CONF_SOURCE_INDEX]))
            return self._finish(updated)
        return self.async_show_form(step_id="delete_source", data_schema=vol.Schema({vol.Required(CONF_SOURCE_INDEX): _select(options)}))
