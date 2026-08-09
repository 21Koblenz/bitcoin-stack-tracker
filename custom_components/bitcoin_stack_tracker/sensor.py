"""Sensors for Bitcoin Stack Tracker."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ALL_DEPOTS, BRAND_NAME, CONF_NAME, DOMAIN, VERSION
from .coordinator import BitcoinPriceCoordinator
from .fifo import currency_summary_from_result
from .helpers import configured_currencies, effective_settings
from .models import SATOSHIS_PER_BTC, decimal_value, goal_reached_at, slugify
from .storage import BitcoinHistoryStore, BitcoinLedgerStore

GLOBAL_METRICS = [
    "stack_btc", "stack_sats", "purchase_count", "sale_count", "known_cost_btc",
    "unknown_cost_btc", "unresolved_fifo_btc", "long_term_btc", "short_term_btc",
    "next_long_term_date", "next_long_term_btc", "last_ledger_entry",
]
DEPOT_METRICS = [
    "depot_stack_btc", "depot_stack_sats", "depot_purchase_count", "depot_sale_count",
    "depot_known_cost_btc", "depot_unknown_cost_btc", "depot_unresolved_fifo_btc",
    "depot_long_term_btc", "depot_short_term_btc", "depot_next_long_term_date",
    "depot_next_long_term_btc",
]
GOAL_METRICS = [
    "goal_progress", "goal_remaining_btc", "goal_remaining_sats",
    "goal_remaining_fiat", "goal_target_fiat_value",
]
CURRENCY_METRICS = [
    "current_price", "portfolio_value", "known_cost_market_value", "invested",
    "average_buy_price", "unrealized_profit_loss", "unrealized_profit_loss_percent",
    "realized_profit_loss", "realized_long_term_profit_loss",
    "realized_short_term_profit_loss", "purchase_fees", "sale_fees",
]
DEPOT_CURRENCY_METRICS = [
    "depot_portfolio_value", "depot_invested", "depot_average_buy_price",
    "depot_unrealized_profit_loss", "depot_unrealized_profit_loss_percent",
    "depot_realized_profit_loss", "depot_realized_long_term_profit_loss",
    "depot_realized_short_term_profit_loss",
]
PRICE_DEPENDENT = {
    "current_price", "portfolio_value", "known_cost_market_value",
    "unrealized_profit_loss", "unrealized_profit_loss_percent",
    "depot_portfolio_value", "depot_unrealized_profit_loss",
    "depot_unrealized_profit_loss_percent", "goal_remaining_fiat",
    "goal_target_fiat_value",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    storage: BitcoinLedgerStore = runtime["storage"]
    history_storage: BitcoinHistoryStore = runtime["history_storage"]
    coordinator: BitcoinPriceCoordinator = runtime["coordinator"]
    currencies = configured_currencies(effective_settings(entry))
    # Password-protected portfolios never publish balances as global HA entity
    # states because entity permissions are not equivalent to this app's allowlist.
    private_mode = (
        runtime["security"].encryption_mode == "password"
        or not runtime["security"].expose_sensitive_sensors
        or storage.is_locked
    )

    entities: list[SensorEntity] = [
        BitcoinHistoryStatusSensor(
            entry, coordinator, storage, history_storage, "history_last_sync"
        ),
        BitcoinHistoryStatusSensor(
            entry, coordinator, storage, history_storage, "history_daily_points"
        ),
    ]
    if private_mode:
        # Home Assistant entity states are globally readable by ordinary users in
        # standard installations. Therefore secure mode exposes price-only sensors.
        registry = er.async_get(hass)
        safe_unique_ids = {
            f"{entry.entry_id}_history_last_sync",
            f"{entry.entry_id}_history_daily_points",
            *(
                f"{entry.entry_id}_current_price_{currency.lower()}"
                for currency in currencies
            ),
        }
        for registry_entry in er.async_entries_for_config_entry(
            registry, entry.entry_id
        ):
            if (
                registry_entry.domain == "sensor"
                and registry_entry.unique_id not in safe_unique_ids
            ):
                registry.async_remove(registry_entry.entity_id)
        entities.extend(
            BitcoinCurrencySensor(
                entry, coordinator, storage, "current_price", currency
            )
            for currency in currencies
        )
        async_add_entities(entities)
        return

    entities.extend(
        BitcoinLocalSensor(entry, coordinator, storage, metric)
        for metric in GLOBAL_METRICS
    )
    entities.extend(
        BitcoinCurrencySensor(entry, coordinator, storage, metric, currency)
        for currency in currencies
        for metric in CURRENCY_METRICS
    )

    if len(storage.depots) > 1:
        entities.extend(
            BitcoinLocalSensor(
                entry,
                coordinator,
                storage,
                metric,
                depot_id=str(depot["id"]),
                depot_name=str(depot["name"]),
            )
            for depot in storage.depots
            for metric in DEPOT_METRICS
        )
        entities.extend(
            BitcoinCurrencySensor(
                entry,
                coordinator,
                storage,
                metric,
                currency,
                depot_id=str(depot["id"]),
                depot_name=str(depot["name"]),
            )
            for depot in storage.depots
            for currency in currencies
            for metric in DEPOT_CURRENCY_METRICS
        )

    entities.extend(
        BitcoinGoalSensor(entry, coordinator, storage, metric, goal)
        for goal in storage.goals
        for metric in GOAL_METRICS
    )
    async_add_entities(entities)


class BitcoinBaseSensor(CoordinatorEntity[BitcoinPriceCoordinator], SensorEntity):
    """Base portfolio sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BitcoinPriceCoordinator,
        storage: BitcoinLedgerStore,
        metric: str,
        currency: str | None = None,
        depot_id: str | None = None,
        depot_name: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self.storage = storage
        self.metric = metric
        self.currency = currency
        self.depot_id = depot_id
        self.depot_name = depot_name
        suffixes = [metric]
        if currency:
            suffixes.append(currency.lower())
        if depot_id:
            suffixes.append(slugify(depot_id))
        self._attr_unique_id = f"{entry.entry_id}_{'_'.join(suffixes)}"
        self._attr_translation_key = metric
        placeholders: dict[str, str] = {}
        if currency:
            placeholders["currency"] = currency
        if depot_name:
            placeholders["depot"] = depot_name
        if placeholders:
            self._attr_translation_placeholders = placeholders
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=effective_settings(entry).get(CONF_NAME, entry.title),
            manufacturer=BRAND_NAME,
            model="Only Bitcoin · local portfolio tracker",
            sw_version=VERSION,
        )

    @property
    def available(self) -> bool:
        if self.metric in PRICE_DEPENDENT and self.currency:
            return self.currency in (self.coordinator.data or {}).get("prices", {})
        return True

    @property
    def ledger(self) -> list[dict[str, Any]]:
        return self.storage.entries

    @property
    def long_term_days(self) -> int:
        return int(self.storage.tax_settings.get("long_term_days", 365))

    def fifo(self, depot_id: str | None = None) -> dict[str, Any]:
        return self.storage.fifo_summary(depot_id)


class BitcoinLocalSensor(BitcoinBaseSensor):
    """Stack, count, FIFO status, and holding-period sensors."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        metric = self.metric
        if metric.endswith((
            "stack_btc", "known_cost_btc", "unknown_cost_btc",
            "unresolved_fifo_btc", "long_term_btc", "short_term_btc",
            "next_long_term_btc",
        )):
            self._attr_native_unit_of_measurement = "BTC"
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_suggested_display_precision = 8
        elif metric.endswith("stack_sats"):
            self._attr_native_unit_of_measurement = "sats"
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_suggested_display_precision = 0
        elif metric.endswith("count"):
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_suggested_display_precision = 0
        elif metric in {
            "last_ledger_entry", "next_long_term_date", "depot_next_long_term_date"
        }:
            self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> float | int | datetime | None:
        summary = self.fifo(self.depot_id)
        total = summary["total_btc"]
        metric = self.metric.removeprefix("depot_")
        scoped_entries = [
            item for item in self.ledger
            if self.depot_id is None or item.get("depot_id", "main") == self.depot_id
        ]
        if metric == "stack_btc":
            return float(total)
        if metric == "stack_sats":
            return int((total * SATOSHIS_PER_BTC).quantize(Decimal("1")))
        if metric == "purchase_count":
            return sum(1 for item in scoped_entries if item.get("type") == "purchase")
        if metric == "sale_count":
            return sum(1 for item in scoped_entries if item.get("type") == "sale")
        if metric == "known_cost_btc":
            return float(summary["known_btc"])
        if metric == "unknown_cost_btc":
            return float(summary["unknown_btc"])
        if metric == "unresolved_fifo_btc":
            return float(summary["unresolved_btc"])
        if metric == "long_term_btc":
            return float(summary["long_term_btc"])
        if metric == "short_term_btc":
            return float(summary["short_term_btc"])
        if metric == "next_long_term_btc":
            return float(summary["next_long_term_btc"])
        if metric == "next_long_term_date":
            value = summary.get("next_long_term_date")
            return dt_util.parse_datetime(value) if value else None
        if metric == "last_ledger_entry":
            if not scoped_entries:
                return None
            return dt_util.parse_datetime(str(scoped_entries[-1].get("timestamp", "")))
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.metric in {"stack_btc", "depot_stack_btc"}:
            return {
                "ledger_entries": len(self.ledger),
                "storage": "local_home_assistant_storage",
                "asset": "BTC",
                "depot_id": self.depot_id or ALL_DEPOTS,
            }
        if "long_term" in self.metric or "short_term" in self.metric:
            return {
                "holding_period_days": self.long_term_days,
                "classification_only": True,
                "tax_advice": False,
                "note": self.storage.tax_settings.get("note", ""),
                "depot_id": self.depot_id or ALL_DEPOTS,
            }
        if self.metric in {"unresolved_fifo_btc", "depot_unresolved_fifo_btc"}:
            return {
                "reason": "unknown cost basis, mixed fiat currencies, or insufficient earlier stack",
                "fifo_scope": "per_depot",
            }
        return None


class BitcoinCurrencySensor(BitcoinBaseSensor):
    """Currency-specific valuation, basis, fees, and FIFO gain sensor."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        metric = self.metric.removeprefix("depot_")
        if metric.endswith("percent"):
            self._attr_native_unit_of_measurement = "%"
            self._attr_suggested_display_precision = 2
        elif metric in {"current_price", "average_buy_price"}:
            self._attr_native_unit_of_measurement = f"{self.currency}/BTC"
            self._attr_suggested_display_precision = 2
        else:
            self._attr_native_unit_of_measurement = self.currency
            self._attr_suggested_display_precision = 2
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        assert self.currency is not None
        price_value = (self.coordinator.data or {}).get("prices", {}).get(self.currency)
        price = decimal_value(price_value) if price_value is not None else None
        metric = self.metric.removeprefix("depot_")

        # The public BTC price sensor must remain usable while the private ledger
        # is password-locked. Do not touch storage for this metric.
        if metric == "current_price":
            return float(price) if price is not None else None

        summary = currency_summary_from_result(
            self.fifo(self.depot_id), self.currency
        )
        total = summary["total_btc"]
        known = summary["known_btc"]
        invested = summary["invested"]
        if metric == "portfolio_value":
            return float(total * price) if price is not None else None
        if metric == "known_cost_market_value":
            return float(known * price) if price is not None else None
        if metric == "invested":
            return float(invested)
        if metric == "average_buy_price":
            return float(invested / known) if known > 0 else 0.0
        if metric == "unrealized_profit_loss":
            return float(known * price - invested) if price is not None else None
        if metric == "unrealized_profit_loss_percent":
            if price is None:
                return None
            return float(
                ((known * price - invested) / invested * Decimal("100"))
                if invested > 0 else Decimal("0")
            )
        if metric == "realized_profit_loss":
            return float(summary["realized_gain"])
        if metric == "realized_long_term_profit_loss":
            return float(summary["realized_long_term_gain"])
        if metric == "realized_short_term_profit_loss":
            return float(summary["realized_short_term_gain"])
        if metric == "purchase_fees":
            return float(summary["purchase_fees"])
        if metric == "sale_fees":
            return float(summary["sale_fees"])
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        assert self.currency is not None
        if self.metric == "current_price":
            details = (self.coordinator.data or {}).get("price_details", {}).get(self.currency, {})
            providers = [
                {
                    "name": item.get("name"),
                    "price": item.get("price"),
                    "used": item.get("used"),
                    "status": item.get("status"),
                }
                for item in details.get("providers", [])
                if isinstance(item, dict)
            ] if isinstance(details, dict) else []
            return {
                "currency": self.currency,
                "last_price_update": (self.coordinator.data or {}).get("updated_at"),
                "price_method": details.get("method") if isinstance(details, dict) else None,
                "source_count": details.get("source_count") if isinstance(details, dict) else None,
                "spread_percent": details.get("spread_pct") if isinstance(details, dict) else None,
                "providers": providers,
                "network_route": "Tor" if details else None,
                "source_errors": (self.coordinator.data or {}).get("errors", []),
            }
        summary = currency_summary_from_result(
            self.fifo(self.depot_id), self.currency
        )
        return {
                "remaining_cost_basis_btc": float(summary["known_btc"]),
                "currency": self.currency,
                "fees_included": True,
                "fifo_scope": "per_depot",
                "mixed_currency_gain_excluded": True,
                "holding_period_days": self.long_term_days,
                "tax_overview_only": True,
            "depot_id": self.depot_id or ALL_DEPOTS,
        }


class BitcoinGoalSensor(BitcoinBaseSensor):
    """One of any number of user-defined BTC and fiat milestones."""

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BitcoinPriceCoordinator,
        storage: BitcoinLedgerStore,
        metric: str,
        goal: dict[str, Any],
    ) -> None:
        self.goal = goal
        currency = str(goal.get("currency", "EUR")).upper()
        super().__init__(entry, coordinator, storage, metric, currency=currency)
        self._attr_unique_id = f"{entry.entry_id}_{metric}_{goal['id']}"
        self._attr_translation_placeholders = {
            "goal": str(goal.get("name", "Goal")),
            "currency": currency,
        }
        if metric == "goal_progress":
            self._attr_native_unit_of_measurement = "%"
            self._attr_suggested_display_precision = 2
        elif metric == "goal_remaining_btc":
            self._attr_native_unit_of_measurement = "BTC"
            self._attr_suggested_display_precision = 8
        elif metric == "goal_remaining_sats":
            self._attr_native_unit_of_measurement = "sats"
            self._attr_suggested_display_precision = 0
        else:
            self._attr_native_unit_of_measurement = currency
            self._attr_suggested_display_precision = 2
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | int | None:
        scope = str(self.goal.get("depot_id", ALL_DEPOTS))
        total = self.fifo(None if scope == ALL_DEPOTS else scope)["total_btc"]
        target = decimal_value(self.goal.get("amount_btc"))
        remaining = max(target - total, Decimal("0"))
        if self.metric == "goal_progress":
            return float(min(total / target * Decimal("100"), Decimal("100"))) if target > 0 else 0.0
        if self.metric == "goal_remaining_btc":
            return float(remaining)
        if self.metric == "goal_remaining_sats":
            return int((remaining * SATOSHIS_PER_BTC).quantize(Decimal("1")))
        price_value = (self.coordinator.data or {}).get("prices", {}).get(self.currency)
        if price_value is None:
            return None
        price = decimal_value(price_value)
        if self.metric == "goal_remaining_fiat":
            return float(remaining * price)
        if self.metric == "goal_target_fiat_value":
            return float(target * price)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        scope = str(self.goal.get("depot_id", ALL_DEPOTS))
        target = decimal_value(self.goal.get("amount_btc"))
        total = self.fifo(None if scope == ALL_DEPOTS else scope)["total_btc"]
        reached_at = goal_reached_at(self.ledger, target, scope) if target > 0 else None
        attributes = {
            "goal_id": self.goal.get("id"),
            "goal_name": self.goal.get("name"),
            "target_btc": self.goal.get("amount_btc"),
            "depot_id": scope,
            "fiat_currency": self.currency,
            "storage_note": (
                "Each additional goal creates five sensors and corresponding recorder/statistics series."
            ),
        }
        if self.metric == "goal_progress":
            attributes.update({
                "goal_reached": bool(target > 0 and total >= target),
                "goal_ever_reached": reached_at is not None,
                "goal_reached_at": reached_at,
            })
        return attributes


class BitcoinHistoryStatusSensor(BitcoinBaseSensor):
    """Status of locally cached daily history."""

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BitcoinPriceCoordinator,
        storage: BitcoinLedgerStore,
        history_storage: BitcoinHistoryStore,
        metric: str,
    ) -> None:
        self.history_storage = history_storage
        super().__init__(entry, coordinator, storage, metric)
        if metric == "history_last_sync":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        else:
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_suggested_display_precision = 0

    @property
    def native_value(self) -> datetime | int | None:
        data = self.history_storage.data
        if self.metric == "history_last_sync":
            return dt_util.parse_datetime(data.get("last_sync")) if data.get("last_sync") else None
        return sum(len(series) for series in data.get("prices", {}).values())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.history_storage.data
        return {
            "points_per_currency": {
                currency: len(values)
                for currency, values in data.get("prices", {}).items()
            },
            "errors": data.get("errors", []),
            "storage": "local_home_assistant_storage",
        }
