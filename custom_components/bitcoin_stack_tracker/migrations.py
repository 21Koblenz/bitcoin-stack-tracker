"""Pure migrations for config entries and locally stored Bitcoin ledgers."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from ipaddress import ip_address, ip_network
from urllib.parse import urlparse
from typing import Any

from .const import (
    ALL_DEPOTS,
    CONF_ENCRYPTION_MODE,
    CONF_HISTORY_AUTO_SYNC,
    CONF_HISTORY_ENABLED,
    CONF_HISTORY_TOR_PROXY,
    CONF_MEMPOOL_OWN_INSTANCE,
    CONF_MEMPOOL_ROUTE,
    CONF_SETUP_TOKEN,
    CONF_SOURCES,
    CONF_SOURCE_TYPE,
    CONF_BASE_URL,
    DEFAULT_DEPOT_ID,
    DEFAULT_HISTORY_TOR_PROXY,
    LEGACY_HISTORY_TOR_PROXY,
    LOCAL_HISTORY_TOR_PROXY,
    DEFAULT_LONG_TERM_DAYS,
    DEFAULT_TAX_NOTE,
    STORAGE_SCHEMA_VERSION,
    MEMPOOL_ROUTE_DIRECT,
    MEMPOOL_ROUTE_TOR,
    SOURCE_MEMPOOL,
)

ENCRYPTION_NONE = "none"
VALID_ENCRYPTION_MODES = {"none", "password", "installation_key_legacy"}
LATEST_CONFIG_VERSION = 10


def _entry_sort_key(row: dict[str, Any]) -> tuple[datetime, int, str]:
    """Sort legacy rows by the represented UTC instant, not ISO text."""
    try:
        parsed = datetime.fromisoformat(str(row.get("timestamp") or "").replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        parsed = datetime.max.replace(tzinfo=timezone.utc)
    return (
        parsed,
        1 if row.get("type") in {"sale", "expense"} else 0,
        str(row.get("id", "")),
    )


def _legacy_local_url(url: str) -> bool:
    host = (urlparse(str(url)).hostname or "").lower().rstrip(".")
    if host in {"localhost", "homeassistant", "supervisor"}:
        return True
    if host.endswith((".local", ".home.arpa", ".lan", ".internal")):
        return True
    try:
        address = ip_address(host)
    except ValueError:
        return False
    local_networks = (
        ip_network("10.0.0.0/8"),
        ip_network("172.16.0.0/12"),
        ip_network("192.168.0.0/16"),
        ip_network("127.0.0.0/8"),
        ip_network("169.254.0.0/16"),
        ip_network("fc00::/7"),
        ip_network("fe80::/10"),
        ip_network("::1/128"),
    )
    return any(address in network for network in local_networks)


def _migrate_mempool_source(source: dict[str, Any]) -> dict[str, Any]:
    migrated = deepcopy(source)
    base_url = str(migrated.get(CONF_BASE_URL, ""))
    host = (urlparse(base_url).hostname or "").lower().rstrip(".")
    public = host == "mempool.space" or host.endswith(".mempool.space")
    onion = host.endswith(".onion")
    migrated.setdefault(CONF_MEMPOOL_OWN_INSTANCE, not public)
    migrated[CONF_MEMPOOL_ROUTE] = (
        MEMPOOL_ROUTE_DIRECT
        if bool(migrated[CONF_MEMPOOL_OWN_INSTANCE])
        and _legacy_local_url(base_url)
        and not onion
        else MEMPOOL_ROUTE_TOR
    )
    return migrated


def migrate_config_data(version: int, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Migrate config data from every published beta entry version."""
    if version < 1 or version > LATEST_CONFIG_VERSION:
        raise ValueError(f"Unsupported config entry version: {version}")
    migrated = deepcopy(data)

    migrated.setdefault(CONF_ENCRYPTION_MODE, ENCRYPTION_NONE)

    mode = str(migrated.get(CONF_ENCRYPTION_MODE, ENCRYPTION_NONE))
    if mode not in VALID_ENCRYPTION_MODES:
        migrated[CONF_ENCRYPTION_MODE] = ENCRYPTION_NONE

    # These fields are safe defaults for every published config version.
    # setdefault keeps deliberately disabled history on current entries intact.
    migrated.pop(CONF_SETUP_TOKEN, None)
    migrated.setdefault(CONF_HISTORY_ENABLED, True)
    migrated.setdefault(CONF_HISTORY_AUTO_SYNC, True)
    sources = migrated.get(CONF_SOURCES, [])
    migrated[CONF_SOURCES] = sources if isinstance(sources, list) else []

    if version < 7:
        # 0 means: retain and use every daily value available from the sources.
        migrated["history_days"] = 0

    if version < 8:
        migrated.setdefault(CONF_HISTORY_TOR_PROXY, DEFAULT_HISTORY_TOR_PROXY)
        migrated[CONF_SOURCES] = [
            _migrate_mempool_source(source)
            if isinstance(source, dict)
            and source.get(CONF_SOURCE_TYPE) == SOURCE_MEMPOOL
            else source
            for source in migrated[CONF_SOURCES]
        ]

    if version < 9:
        # beta.10 stored localhost as its default even though Home Assistant Core
        # cannot reach a Tor process inside a separate app at 127.0.0.1.
        if migrated.get(CONF_HISTORY_TOR_PROXY) == LEGACY_HISTORY_TOR_PROXY:
            migrated[CONF_HISTORY_TOR_PROXY] = DEFAULT_HISTORY_TOR_PROXY
        migrated[CONF_SOURCES] = [
            _migrate_mempool_source(source)
            if isinstance(source, dict)
            and source.get(CONF_SOURCE_TYPE) == SOURCE_MEMPOOL
            else source
            for source in migrated[CONF_SOURCES]
        ]

    if version < 10:
        # Repository-installed apps use the Supervisor repository hash in their
        # internal DNS alias. The runtime still accepts the local alias as a
        # fail-closed development fallback.
        if migrated.get(CONF_HISTORY_TOR_PROXY) in {
            LOCAL_HISTORY_TOR_PROXY,
            LEGACY_HISTORY_TOR_PROXY,
        }:
            migrated[CONF_HISTORY_TOR_PROXY] = DEFAULT_HISTORY_TOR_PROXY

    return LATEST_CONFIG_VERSION, migrated


def migrate_ledger_data(data: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
    """Normalize ledger formats written by versions 0.1 through 0.4.

    Existing entries, goals and depots are preserved. Missing depot assignments from
    0.1 are attached to the default depot. No existing data is silently truncated.
    """
    original = deepcopy(data) if isinstance(data, dict) else {}
    migrated = deepcopy(original)

    if not isinstance(migrated.get("entries"), list):
        migrated["entries"] = []
    if not isinstance(migrated.get("depots"), list) or not migrated["depots"]:
        migrated["depots"] = [{"id": DEFAULT_DEPOT_ID, "name": "Main"}]
    if not isinstance(migrated.get("goals"), list):
        migrated["goals"] = []
    if not isinstance(migrated.get("tax_settings"), dict):
        migrated["tax_settings"] = {}

    tax_settings = migrated["tax_settings"]
    try:
        days = int(tax_settings.get("long_term_days", DEFAULT_LONG_TERM_DAYS))
    except (TypeError, ValueError):
        days = DEFAULT_LONG_TERM_DAYS
    tax_settings["long_term_days"] = days if days >= 1 else DEFAULT_LONG_TERM_DAYS
    if not isinstance(tax_settings.get("note"), str):
        tax_settings["note"] = DEFAULT_TAX_NOTE

    normalized_depots: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in migrated["depots"]:
        if not isinstance(raw, dict):
            continue
        depot_id = str(raw.get("id") or "").strip()
        if not depot_id or depot_id in seen:
            continue
        seen.add(depot_id)
        normalized_depots.append(
            {"id": depot_id, "name": str(raw.get("name") or depot_id).strip() or depot_id}
        )
    if DEFAULT_DEPOT_ID not in seen:
        normalized_depots.insert(0, {"id": DEFAULT_DEPOT_ID, "name": "Main"})
        seen.add(DEFAULT_DEPOT_ID)
    migrated["depots"] = normalized_depots

    normalized_entries: list[dict[str, Any]] = []
    for raw in migrated["entries"]:
        if not isinstance(raw, dict):
            continue
        item = deepcopy(raw)
        if str(item.get("depot_id") or "") not in seen:
            item["depot_id"] = DEFAULT_DEPOT_ID
        normalized_entries.append(item)
    normalized_entries.sort(key=_entry_sort_key)
    migrated["entries"] = normalized_entries

    normalized_goals: list[dict[str, Any]] = []
    for raw in migrated["goals"]:
        if not isinstance(raw, dict):
            continue
        goal = deepcopy(raw)
        if str(goal.get("depot_id") or ALL_DEPOTS) not in seen | {ALL_DEPOTS}:
            goal["depot_id"] = ALL_DEPOTS
        else:
            goal["depot_id"] = str(goal.get("depot_id") or ALL_DEPOTS)
        goal["currency"] = str(goal.get("currency") or "EUR").upper()
        normalized_goals.append(goal)
    migrated["goals"] = normalized_goals
    if not isinstance(migrated.get("chart_cache"), dict):
        migrated["chart_cache"] = {"revision": None, "data": {}}
    else:
        migrated["chart_cache"].setdefault("revision", None)
        migrated["chart_cache"].setdefault("data", {})
    migrated["schema_version"] = STORAGE_SCHEMA_VERSION
    return migrated, migrated != original
