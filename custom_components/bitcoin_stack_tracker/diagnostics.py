"""Privacy-preserving diagnostics for Bitcoin Stack Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .helpers import configured_currencies, effective_settings
from .limits import (
    MAX_DEPOTS,
    MAX_GOALS,
    MAX_HISTORY_CURRENCIES,
    MAX_LEDGER_ENTRIES,
    MAX_STATISTIC_POINTS_PER_SERIES,
    MAX_STATISTIC_POINTS_PER_SYNC,
    MAX_STATISTIC_SERIES,
)


def _source_summary(settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Describe source policy without exposing URLs, entity IDs, or local hosts."""
    result: list[dict[str, Any]] = []
    for source in settings.get("sources", []):
        if not isinstance(source, dict):
            continue
        source_type = str(source.get("source_type") or "unknown")
        currencies = source.get("currencies")
        if not isinstance(currencies, list):
            currency = str(source.get("currency") or "").upper()
            currencies = [currency] if currency else []
        item: dict[str, Any] = {
            "source_type": source_type,
            "currencies": [str(value).upper() for value in currencies if value],
        }
        if source_type == "mempool":
            item.update({
                "own_instance": bool(source.get("mempool_own_instance", False)),
                "route": str(source.get("mempool_route") or "tor"),
                "tls_verification": bool(source.get("verify_ssl", True)),
            })
        result.append(item)
    return result


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    runtime = hass.data[DOMAIN][entry.entry_id]
    storage = runtime["storage"]
    history = runtime["history_storage"].data
    settings = dict(effective_settings(entry))
    history_errors = history.get("errors", [])
    coordinator_errors = (runtime["coordinator"].data or {}).get("errors", [])
    result: dict[str, Any] = {
        "settings_summary": {
            "source_count": len(settings.get("sources", [])),
            "sources": _source_summary(settings),
            "currencies": configured_currencies(settings),
            "update_interval": settings.get("update_interval"),
            "history_enabled": bool(settings.get("history_enabled", True)),
            "history_auto_sync": bool(settings.get("history_auto_sync", True)),
            "tor_proxy_configured": bool(settings.get("history_tor_proxy")),
        },
        "security": {
            "encryption_mode": runtime["security"].encryption_mode,
            "vault_locked": storage.is_locked,
            "password_setup_required": storage.setup_required,
            "allowed_user_count": len(runtime["security"].allowed_user_ids),
            "sensitive_sensors_exposed": runtime["security"].expose_sensitive_sensors,
        },
        "historical_points_per_currency": {
            currency: len(values)
            for currency, values in history.get("prices", {}).items()
        },
        "history_last_sync": history.get("last_sync"),
        "history_statistic_series_count": len(history.get("statistics_ids", [])),
        "history_fingerprint_count": len(history.get("statistics_hashes", {})),
        "history_error_count": len(history_errors) if isinstance(history_errors, list) else 0,
        "coordinator_error_count": len(coordinator_errors) if isinstance(coordinator_errors, list) else 0,
        "hardening_limits": {
            "max_depots": MAX_DEPOTS,
            "max_goals": MAX_GOALS,
            "max_ledger_entries": MAX_LEDGER_ENTRIES,
            "max_history_currencies": MAX_HISTORY_CURRENCIES,
            "max_statistic_series": MAX_STATISTIC_SERIES,
            "max_statistic_points_per_series": MAX_STATISTIC_POINTS_PER_SERIES,
            "max_statistic_points_per_sync": MAX_STATISTIC_POINTS_PER_SYNC,
        },
    }
    if not storage.is_locked:
        ledger = await storage.async_export()
        result["ledger_counts"] = {
            "entries": len(ledger.get("entries", [])),
            "depots": len(ledger.get("depots", [])),
            "goals": len(ledger.get("goals", [])),
        }
        result["holding_period_days"] = ledger.get("tax_settings", {}).get(
            "long_term_days"
        )
    return result
