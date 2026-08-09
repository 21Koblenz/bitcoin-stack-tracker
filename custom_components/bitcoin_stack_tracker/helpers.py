"""Shared helpers for Bitcoin Stack Tracker."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CURRENCIES,
    CONF_CURRENCY,
    CONF_SOURCE_TYPE,
    CONF_SOURCES,
    SOURCE_ENTITY,
)
from .fifo import fifo_result


def effective_settings(entry: ConfigEntry) -> dict[str, Any]:
    """Merge original config data and current options."""
    return {**entry.data, **entry.options}


def configured_currencies(settings: dict[str, Any]) -> list[str]:
    """Return all configured currencies without duplicates."""
    result: list[str] = []
    for source in settings.get(CONF_SOURCES, []):
        currencies = (
            [source.get(CONF_CURRENCY)]
            if source.get(CONF_SOURCE_TYPE) == SOURCE_ENTITY
            else source.get(CONF_CURRENCIES, [])
        )
        for currency in currencies:
            upper = str(currency).upper() if currency else ""
            if upper and upper not in result:
                result.append(upper)
    return result


def parse_timestamp(value: Any) -> datetime:
    """Parse a Home Assistant datetime selector value and return UTC."""
    if isinstance(value, datetime):
        parsed = value
    elif value:
        parsed = dt_util.parse_datetime(str(value))
        if parsed is None:
            raise ValueError("Invalid timestamp")
    else:
        parsed = dt_util.now()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return parsed.astimezone(timezone.utc)


def ledger_summary(entries: list[dict[str, Any]], depot_id: str | None = None) -> dict[str, Any]:
    """Return FIFO-aware stack summary."""
    return fifo_result(entries, depot_id)
