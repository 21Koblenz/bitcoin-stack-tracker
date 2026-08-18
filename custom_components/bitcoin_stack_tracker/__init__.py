"""Bitcoin Stack Tracker integration."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
import asyncio
import base64
from decimal import Decimal
from functools import partial
import json
import logging
from time import monotonic
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import parse_qs, urlparse, urlsplit

import voluptuous as vol
from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Context, HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ALL_DEPOTS,
    BRAND_NAME,
    BRAND_WATERMARK,
    CONF_GOAL_BTC,
    CONF_ENCRYPTION_MODE,
    CONF_SETUP_TOKEN,
    CONF_HISTORY_AUTO_SYNC,
    CONF_HISTORY_ENABLED,
    CONF_HISTORY_TOR_PROXY,
    CONF_BASE_URL,
    CONF_BUY_OPPORTUNITY_SETTINGS,
    CONF_MEMPOOL_OWN_INSTANCE,
    CONF_SOURCE_TYPE,
    CONF_SOURCES,
    CONF_VERIFY_SSL,
    DEFAULT_HISTORY_TOR_PROXY,
    DEFAULT_MEMPOOL_URL,
    DEFAULT_DEPOT_ID,
    DEFAULT_LONG_TERM_DAYS,
    DEFAULT_TAX_NOTE,
    DOMAIN,
    KRAKEN_CURRENCIES,
    PLATFORMS,
    SOURCE_MEMPOOL,
    UNIT_BTC,
    UNIT_SATS,
    V4V_LIGHTNING_ADDRESS,
    VERSION,
)
from .buy_opportunity import (
    DEFAULT_MODEL_SETTINGS,
    DEFAULT_SIGNAL_WEIGHTS,
    DEFAULT_TURNING_POINT_WEIGHTS,
    PROFILE_WEIGHTS,
    calculate_buy_opportunity_history,
    calculate_buy_opportunity_history_scores,
    normalize_buy_opportunity_settings,
)
from .coordinator import BitcoinPriceCoordinator
from .crypto import (
    PasswordDecryptionError,
    PasswordValidationError,
    create_backup_envelope,
    decrypt_backup_envelope,
)
from .export import write_csv_export
from .fifo import cumulative_average_entry_price_by_disposition, currency_summary_from_result, fifo_result
from .helpers import configured_currencies, effective_settings, parse_timestamp
from .http_limits import MAX_ERROR_RESPONSE_BYTES, async_json_limited, async_text_limited
from .history import (
    async_clear_entry_statistics,
    async_ensure_chart_cache,
    async_sync_history,
    async_sync_intraday_history,
    market_ohlc_interval_for_days,
)
from .limits import MAX_DEPOTS, MAX_GOALS, MAX_LEDGER_ENTRIES, RATE_LIMITS
from .migrations import LATEST_CONFIG_VERSION, migrate_config_data
from .models import amount_to_btc, btc_string, decimal_value, goal_reached_at, money_string
from .reference_price import historical_reference_price
from .metrics import build_dashboard_metrics
from .market_assessment_runtime import async_market_assessment, invalidate_market_assessment_cache
from .market_assessment_intraday_cache import (
    MarketAssessmentIntradayCache,
    market_assessment_intraday_signature,
)
from .market_assessment_history_cache import (
    MarketAssessmentHistoryCache,
    market_assessment_history_signature,
)
from .network import async_routed_session, async_tor_gateway_host, mempool_source_uses_tor, network_security_snapshot, rotate_tor_isolation, tor_proxy_from_settings
from .rate_limit import OperationRateLimiter
from .csv_import import MAX_IMPORT_BYTES, parse_transaction_upload
from .storage import BitcoinHistoryStore, BitcoinLedgerStore
from .wallet_watch import WalletWatchManager, normalize_watch_config
from .security import (
    BitcoinSecurityStore,
    ENCRYPTION_NONE,
    ENCRYPTION_PASSWORD,
    VaultAccessDenied,
    VaultLockedError,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_ADD_PURCHASE = "add_purchase"
SERVICE_ADD_INCOME = "add_income"
SERVICE_ADD_SALE = "add_sale"
SERVICE_ADD_EXPENSE = "add_expense"
SERVICE_ADD_NETWORK_FEE = "add_network_fee"
SERVICE_ADD_STACK = "add_stack"
SERVICE_BULK_IMPORT = "bulk_import"
SERVICE_ADD_DEPOT = "add_depot"
SERVICE_DELETE_DEPOT = "delete_depot"
SERVICE_ADD_GOAL = "add_goal"
SERVICE_UPDATE_GOAL = "update_goal"
SERVICE_DELETE_GOAL = "delete_goal"
SERVICE_DELETE_ENTRY = "delete_entry"
SERVICE_UPDATE_ENTRY = "update_entry"
SERVICE_DELETE_ALL_ENTRIES = "delete_all_entries"
SERVICE_SET_GOAL = "set_goal"
SERVICE_SET_TAX_SETTINGS = "set_tax_settings"
SERVICE_EXPORT_LEDGER = "export_ledger"
SERVICE_EXPORT_CSV = "export_csv"
SERVICE_SYNC_HISTORY = "sync_history"
SERVICE_LIST_PORTFOLIOS = "list_portfolios"
SERVICE_DASHBOARD_DATA = "dashboard_data"
SERVICE_LIST_USERS = "list_users"
SERVICE_SET_ALLOWED_USERS = "set_allowed_users"
SERVICE_SECURITY_STATUS = "security_status"
SERVICE_SET_SENSITIVE_SENSORS = "set_sensitive_sensors"
SERVICE_UNLOCK_VAULT = "unlock_vault"
SERVICE_LOCK_VAULT = "lock_vault"
SERVICE_SET_ENCRYPTION = "set_encryption"
SERVICE_CHANGE_VAULT_PASSWORD = "change_vault_password"
SERVICE_PURGE_STATISTICS = "purge_statistics"
SERVICE_SET_HISTORY_SETTINGS = "set_history_settings"
SERVICE_SET_BUY_OPPORTUNITY_SETTINGS = "set_buy_opportunity_settings"

DASHBOARD_ACTION_SERVICES = {
    SERVICE_LIST_PORTFOLIOS,
    SERVICE_DASHBOARD_DATA,
    SERVICE_ADD_PURCHASE,
    SERVICE_ADD_INCOME,
    SERVICE_ADD_SALE,
    SERVICE_ADD_EXPENSE,
    SERVICE_ADD_NETWORK_FEE,
    SERVICE_ADD_STACK,
    SERVICE_BULK_IMPORT,
    SERVICE_DELETE_ENTRY,
    SERVICE_UPDATE_ENTRY,
    SERVICE_DELETE_ALL_ENTRIES,
    SERVICE_ADD_DEPOT,
    SERVICE_DELETE_DEPOT,
    SERVICE_ADD_GOAL,
    SERVICE_UPDATE_GOAL,
    SERVICE_DELETE_GOAL,
    SERVICE_SET_TAX_SETTINGS,
    SERVICE_EXPORT_CSV,
    SERVICE_SYNC_HISTORY,
    SERVICE_SET_HISTORY_SETTINGS,
    SERVICE_SET_BUY_OPPORTUNITY_SETTINGS,
    SERVICE_LIST_USERS,
    SERVICE_SET_ALLOWED_USERS,
    SERVICE_SECURITY_STATUS,
    SERVICE_SET_SENSITIVE_SENSORS,
    SERVICE_LOCK_VAULT,
    SERVICE_PURGE_STATISTICS,
}

CONF_CONFIG_ENTRY_ID = "config_entry_id"
CONF_AMOUNT = "amount"
CONF_AMOUNT_UNIT = "amount_unit"
CONF_PRICE = "price"
CONF_CURRENCY = "currency"
CONF_FEE = "fee"
CONF_FEE_BTC = "fee_btc"
CONF_FEE_BTC_AFFECTS_STACK = "fee_btc_affects_stack"
CONF_NETWORK = "network"
CONF_TIMESTAMP = "timestamp"
CONF_NOTE = "note"
CONF_LEDGER_ENTRY_ID = "ledger_entry_id"
CONF_GOAL = "goal"
CONF_GOAL_UNIT = "goal_unit"
CONF_GOAL_NAME = "goal_name"
CONF_GOAL_ID = "goal_id"
CONF_DEPOT_ID = "depot_id"
CONF_DEPOT_NAME = "depot_name"
CONF_DELIMITER = "delimiter"
CONF_LONG_TERM_DAYS = "long_term_days"
CONF_TAX_NOTE = "tax_note"
CONF_HISTORY_DAYS = "history_days"
CONF_HISTORY_INTERVAL = "history_interval"
CONF_ALLOWED_USER_IDS = "allowed_user_ids"
CONF_ENABLED = "enabled"
CONF_AUTO_SYNC = "auto_sync"
CONF_PASSWORD = "password"
CONF_CURRENT_PASSWORD = "current_password"
CONF_NEW_PASSWORD = "new_password"
CONF_CONFIRM = "confirm"
CONF_TRANSACTIONS = "transactions"

TRANSACTION_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_AMOUNT): vol.Coerce(float),
    vol.Optional(CONF_AMOUNT_UNIT, default=UNIT_BTC): vol.In([UNIT_BTC, UNIT_SATS]),
    vol.Required(CONF_PRICE): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Required(CONF_CURRENCY): cv.string,
    vol.Optional(CONF_FEE, default=0): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Optional(CONF_FEE_BTC, default=0): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Optional(CONF_FEE_BTC_AFFECTS_STACK, default=True): cv.boolean,
    vol.Optional(CONF_TIMESTAMP): cv.string,
    vol.Optional(CONF_NOTE, default=""): cv.string,
    vol.Optional(CONF_DEPOT_ID, default=DEFAULT_DEPOT_ID): cv.string,
})
NETWORK_FEE_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_AMOUNT): vol.Coerce(float),
    vol.Optional(CONF_AMOUNT_UNIT, default=UNIT_SATS): vol.In([UNIT_BTC, UNIT_SATS]),
    vol.Required(CONF_PRICE): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Required(CONF_CURRENCY): cv.string,
    vol.Optional(CONF_NETWORK, default="onchain"): vol.In(["onchain", "lightning"]),
    vol.Optional(CONF_TIMESTAMP): cv.string,
    vol.Optional(CONF_NOTE, default=""): cv.string,
    vol.Optional(CONF_DEPOT_ID, default=DEFAULT_DEPOT_ID): cv.string,
})
ADD_STACK_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_AMOUNT): vol.Coerce(float),
    vol.Optional(CONF_AMOUNT_UNIT, default=UNIT_BTC): vol.In([UNIT_BTC, UNIT_SATS]),
    vol.Optional(CONF_TIMESTAMP): cv.string,
    vol.Optional(CONF_NOTE, default=""): cv.string,
    vol.Optional(CONF_DEPOT_ID, default=DEFAULT_DEPOT_ID): cv.string,
})
IMPORT_TRANSACTION_SCHEMA = vol.Schema({
    vol.Required("type"): vol.In(["purchase", "income", "sale", "expense"]),
    vol.Required("timestamp"): cv.string,
    vol.Required("amount_btc"): vol.Any(str, int, float),
    vol.Optional(CONF_CURRENCY, default=""): cv.string,
    vol.Optional(CONF_PRICE, default=0): vol.Any(str, int, float),
    vol.Optional(CONF_FEE, default=0): vol.Any(str, int, float),
    # Analytics-only fee already embedded in a broker execution price.
    vol.Optional("included_fee", default=0): vol.Any(str, int, float),
    vol.Optional("included_fee_estimated", default=False): cv.boolean,
    vol.Optional("fee_btc", default=0): vol.Any(str, int, float),
    vol.Optional(CONF_NOTE, default=""): cv.string,
    vol.Optional(CONF_DEPOT_ID, default=DEFAULT_DEPOT_ID): cv.string,
    # One-way SHA-256 source-row identity used only for duplicate detection.
    vol.Optional("import_ref_hash", default=""): cv.string,
})
BULK_IMPORT_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_TRANSACTIONS): vol.All(
        [IMPORT_TRANSACTION_SCHEMA], vol.Length(min=1, max=5000)
    ),
})
ADD_DEPOT_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_DEPOT_NAME): cv.string,
})
DELETE_DEPOT_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_DEPOT_ID): cv.string,
})
ADD_GOAL_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_GOAL_NAME): cv.string,
    vol.Required(CONF_GOAL): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Optional(CONF_GOAL_UNIT, default=UNIT_BTC): vol.In([UNIT_BTC, UNIT_SATS]),
    vol.Optional(CONF_DEPOT_ID, default=ALL_DEPOTS): cv.string,
    vol.Required(CONF_CURRENCY): cv.string,
})
UPDATE_GOAL_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_GOAL_ID): cv.string,
    vol.Optional(CONF_GOAL_NAME): cv.string,
    vol.Optional(CONF_GOAL): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Optional(CONF_GOAL_UNIT, default=UNIT_BTC): vol.In([UNIT_BTC, UNIT_SATS]),
    vol.Optional(CONF_DEPOT_ID): cv.string,
    vol.Optional(CONF_CURRENCY): cv.string,
})
DELETE_GOAL_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_GOAL_ID): cv.string,
})
DELETE_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_LEDGER_ENTRY_ID): cv.string,
})
UPDATE_ENTRY_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_LEDGER_ENTRY_ID): cv.string,
    vol.Optional("type"): vol.In(["purchase", "income", "sale", "expense", "network_fee", "stack"]),
    vol.Required(CONF_AMOUNT): vol.Coerce(float),
    vol.Optional(CONF_AMOUNT_UNIT, default=UNIT_BTC): vol.In([UNIT_BTC, UNIT_SATS]),
    vol.Optional(CONF_PRICE): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Optional(CONF_CURRENCY): cv.string,
    vol.Optional(CONF_FEE): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Optional(CONF_FEE_BTC): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Optional(CONF_FEE_BTC_AFFECTS_STACK): cv.boolean,
    vol.Optional(CONF_NETWORK): vol.In(["onchain", "lightning"]),
    vol.Optional(CONF_TIMESTAMP): cv.string,
    vol.Optional(CONF_NOTE): cv.string,
    vol.Optional(CONF_DEPOT_ID): cv.string,
})
SET_GOAL_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_GOAL): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Optional(CONF_GOAL_UNIT, default=UNIT_BTC): vol.In([UNIT_BTC, UNIT_SATS]),
})
SET_TAX_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_LONG_TERM_DAYS): vol.All(vol.Coerce(int), vol.Range(min=1, max=36500)),
    vol.Optional(CONF_TAX_NOTE, default=DEFAULT_TAX_NOTE): cv.string,
})
ENTRY_SCHEMA = vol.Schema({vol.Required(CONF_CONFIG_ENTRY_ID): cv.string})
EXPORT_CSV_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Optional(CONF_DELIMITER, default=";"): vol.In([";", ","]),
})
CONF_DASHBOARD_SECTION = "dashboard_section"
DASHBOARD_SECTIONS = {"all", "summary", "chart", "ledger", "fifo"}


DASHBOARD_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    # 0 means every locally cached day. This setting changes only the view;
    # it never deletes or redownloads durable history.
    vol.Optional(CONF_HISTORY_DAYS, default=365): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=36500)
    ),
    vol.Optional(CONF_HISTORY_INTERVAL, default=1440): vol.All(
        vol.Coerce(int), vol.In([5, 15, 30, 60, 120, 240, 720, 1440])
    ),
    # The native panel asks for sensitive/heavy sections only when the
    # corresponding tab actually needs them. Manual service calls keep the
    # legacy all-in-one response by default.
    vol.Optional(CONF_DASHBOARD_SECTION, default="all"): vol.In(DASHBOARD_SECTIONS),
})
SET_HISTORY_SETTINGS_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_ENABLED): cv.boolean,
    vol.Required(CONF_AUTO_SYNC): cv.boolean,
})
BUY_OPPORTUNITY_WEIGHTS_SCHEMA = vol.Schema({
    vol.Optional("long_term"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    vol.Optional("drawdown"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    vol.Optional("range"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    vol.Optional("deviation"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    vol.Optional("momentum"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    vol.Optional("cycle"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
})
BUY_OPPORTUNITY_THRESHOLDS_SCHEMA = vol.Schema({
    vol.Optional("very_expensive_max"): vol.All(vol.Coerce(float), vol.Range(min=1, max=99)),
    vol.Optional("expensive_max"): vol.All(vol.Coerce(float), vol.Range(min=1, max=99)),
    vol.Optional("interesting"): vol.All(vol.Coerce(float), vol.Range(min=1, max=99)),
    vol.Optional("cheap"): vol.All(vol.Coerce(float), vol.Range(min=1, max=99)),
    vol.Optional("very_cheap"): vol.All(vol.Coerce(float), vol.Range(min=1, max=99)),
    vol.Optional("extreme"): vol.All(vol.Coerce(float), vol.Range(min=1, max=99)),
})
BUY_OPPORTUNITY_MODEL_SCHEMA = vol.Schema({
    vol.Optional("minimum_history_points"): vol.All(vol.Coerce(int), vol.Range(min=90, max=3650)),
    vol.Optional("adaptive_window_days"): vol.All(vol.Coerce(int), vol.Range(min=365, max=3650)),
    vol.Optional("adaptive_min_reference_points"): vol.All(vol.Coerce(int), vol.Range(min=60, max=1460)),
    vol.Optional("volatility_window_days"): vol.All(vol.Coerce(int), vol.Range(min=30, max=1460)),
    vol.Optional("volatility_min_points"): vol.All(vol.Coerce(int), vol.Range(min=20, max=730)),
    vol.Optional("volatility_floor_pct"): vol.All(vol.Coerce(float), vol.Range(min=1, max=100)),
    vol.Optional("drawdown_window_days"): vol.All(vol.Coerce(int), vol.Range(min=30, max=3650)),
    vol.Optional("drawdown_min_points"): vol.All(vol.Coerce(int), vol.Range(min=20, max=1460)),
    vol.Optional("regime_high_min_points"): vol.All(vol.Coerce(int), vol.Range(min=60, max=1460)),
    vol.Optional("percentile_window_days"): vol.All(vol.Coerce(int), vol.Range(min=30, max=3650)),
    vol.Optional("percentile_min_points"): vol.All(vol.Coerce(int), vol.Range(min=20, max=1460)),
    vol.Optional("short_deviation_days"): vol.All(vol.Coerce(int), vol.Range(min=5, max=365)),
    vol.Optional("trend_short_days"): vol.All(vol.Coerce(int), vol.Range(min=10, max=730)),
    vol.Optional("pi_short_days"): vol.All(vol.Coerce(int), vol.Range(min=20, max=730)),
    vol.Optional("trend_base_days"): vol.All(vol.Coerce(int), vol.Range(min=30, max=1460)),
    vol.Optional("pi_long_days"): vol.All(vol.Coerce(int), vol.Range(min=50, max=1460)),
    vol.Optional("trend_mid_days"): vol.All(vol.Coerce(int), vol.Range(min=60, max=1460)),
    vol.Optional("trend_long_days"): vol.All(vol.Coerce(int), vol.Range(min=120, max=2500)),
    vol.Optional("trend_cycle_days"): vol.All(vol.Coerce(int), vol.Range(min=365, max=3650)),
    vol.Optional("rsi_period_days"): vol.All(vol.Coerce(int), vol.Range(min=5, max=60)),
    vol.Optional("momentum_short_days"): vol.All(vol.Coerce(int), vol.Range(min=7, max=180)),
    vol.Optional("momentum_long_days"): vol.All(vol.Coerce(int), vol.Range(min=14, max=365)),
    vol.Optional("two_year_multiplier"): vol.All(vol.Coerce(float), vol.Range(min=1, max=10)),
    vol.Optional("power_law_min_points"): vol.All(vol.Coerce(int), vol.Range(min=180, max=1460)),
    vol.Optional("volatility_regime_low_ratio"): vol.All(vol.Coerce(float), vol.Range(min=0.25, max=1.0)),
    vol.Optional("volatility_regime_high_ratio"): vol.All(vol.Coerce(float), vol.Range(min=1.0, max=4.0)),
    vol.Optional("turning_point_lookback_days"): vol.All(vol.Coerce(int), vol.Range(min=30, max=730)),
    vol.Optional("turning_point_separation_days"): vol.All(vol.Coerce(int), vol.Range(min=3, max=90)),
    vol.Optional("turning_zone_memory_days"): vol.All(vol.Coerce(int), vol.Range(min=5, max=180)),
    vol.Optional("divergence_price_tolerance_pct"): vol.All(vol.Coerce(float), vol.Range(min=1, max=30)),
    vol.Optional("volatility_fast_window_days"): vol.All(vol.Coerce(int), vol.Range(min=7, max=180)),
    vol.Optional("volatility_slow_window_days"): vol.All(vol.Coerce(int), vol.Range(min=30, max=365)),
    vol.Optional("volatility_cooling_lookback_days"): vol.All(vol.Coerce(int), vol.Range(min=10, max=180)),
    vol.Optional("exhaustion_short_days"): vol.All(vol.Coerce(int), vol.Range(min=3, max=30)),
    vol.Optional("confirmation_zone_gate"): vol.All(vol.Coerce(float), vol.Range(min=0, max=1)),
    vol.Optional("turning_zone_threshold"): vol.All(vol.Coerce(float), vol.Range(min=50, max=95)),
    vol.Optional("turning_confirmation_threshold"): vol.All(vol.Coerce(float), vol.Range(min=25, max=95)),
    vol.Optional("turning_extreme_threshold"): vol.All(vol.Coerce(float), vol.Range(min=60, max=99)),
})
BUY_OPPORTUNITY_SIGNAL_COMPONENT_SCHEMA = vol.Schema({str: vol.All(vol.Coerce(float), vol.Range(min=0, max=100))})
BUY_OPPORTUNITY_SIGNAL_WEIGHTS_SCHEMA = vol.Schema({
    vol.Optional(component): BUY_OPPORTUNITY_SIGNAL_COMPONENT_SCHEMA
    for component in DEFAULT_SIGNAL_WEIGHTS
})
BUY_OPPORTUNITY_TURNING_WEIGHTS_SCHEMA = vol.Schema({
    vol.Optional(model_name): BUY_OPPORTUNITY_SIGNAL_COMPONENT_SCHEMA
    for model_name in DEFAULT_TURNING_POINT_WEIGHTS
})
SET_BUY_OPPORTUNITY_SETTINGS_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Optional("profile"): vol.In([*PROFILE_WEIGHTS.keys(), "custom"]),
    vol.Optional(CONF_CURRENCY): cv.string,
    vol.Optional("weights"): BUY_OPPORTUNITY_WEIGHTS_SCHEMA,
    vol.Optional("signal_weights"): BUY_OPPORTUNITY_SIGNAL_WEIGHTS_SCHEMA,
    vol.Optional("turning_point_weights"): BUY_OPPORTUNITY_TURNING_WEIGHTS_SCHEMA,
    vol.Optional("thresholds"): BUY_OPPORTUNITY_THRESHOLDS_SCHEMA,
    vol.Optional("model"): BUY_OPPORTUNITY_MODEL_SCHEMA,
    vol.Optional("reset_defaults"): cv.boolean,
})



REQUESTER_SCHEMA: dict[Any, Any] = {}
SET_ALLOWED_USERS_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_ALLOWED_USER_IDS): [cv.string],
})
SET_SENSITIVE_SENSORS_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_ENABLED): cv.boolean,
})
UNLOCK_VAULT_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
})
LOCK_VAULT_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
})
SET_ENCRYPTION_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_ENABLED): cv.boolean,
    vol.Optional(CONF_PASSWORD, default=""): cv.string,
})
PURGE_STATISTICS_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_CONFIRM): vol.In(["DELETE"]),
})
CHANGE_PASSWORD_SCHEMA = vol.Schema({
    vol.Required(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Required(CONF_CURRENT_PASSWORD): cv.string,
    vol.Required(CONF_NEW_PASSWORD): cv.string,
})


def _rate_limiter(hass: HomeAssistant) -> OperationRateLimiter:
    domain_data = hass.data.setdefault(DOMAIN, {})
    limiter = domain_data.get("_rate_limiter")
    if not isinstance(limiter, OperationRateLimiter):
        limiter = OperationRateLimiter()
        domain_data["_rate_limiter"] = limiter
    return limiter


def _enforce_rate_limit(
    hass: HomeAssistant,
    *,
    entry_id: str,
    user_id: str,
    operation: str,
) -> None:
    rule = RATE_LIMITS.get(operation)
    if rule is None:
        return
    result = _rate_limiter(hass).check(
        entry_id=entry_id,
        user_id=user_id,
        operation=operation,
        limit=rule[0],
        window_seconds=rule[1],
    )
    if not result.allowed:
        _LOGGER.warning(
            "Rate limit reached for operation %s on portfolio %s by user %s; retry in %ss",
            operation,
            entry_id,
            user_id,
            result.retry_after,
        )
        raise vol.Invalid(
            f"Too many {operation} requests. Try again in {result.retry_after} seconds"
        )


def _validate_and_decrypt_backup_bytes(backup_bytes: bytes, password: str) -> dict[str, Any]:
    envelope = json.loads(backup_bytes.decode("utf-8"))
    if not isinstance(envelope, dict):
        raise ValueError("Backup envelope is invalid")
    payload = decrypt_backup_envelope(envelope, password=password)
    _validate_backup_payload(payload)
    return payload


def _build_dashboard_calculations(
    entries: list[dict[str, Any]],
    depots: list[dict[str, Any]],
    goals: list[dict[str, Any]],
    prices: dict[str, Any],
    long_term_days: int,
    fifo: dict[str, Any] | None = None,
    depot_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # Storage already maintains FIFO summaries for the current ledger revision.
    # Reuse them for dashboard rendering instead of recalculating the complete
    # ledger after every unlock, import, or page refresh.  The optional fallback
    # keeps this pure helper usable in tests and migration tooling.
    fifo = fifo or fifo_result(entries, long_term_days=long_term_days)
    depot_summaries = []
    depot_results = depot_results or {}
    for depot in depots:
        depot_id = str(depot["id"])
        scoped = depot_results.get(depot_id)
        if scoped is None:
            scoped = fifo_result(entries, depot_id, long_term_days=long_term_days)
            depot_results[depot_id] = scoped
        depot_summaries.append({
            **depot,
            "total_btc": scoped["total_btc"],
            "known_btc": scoped["known_btc"],
            "unknown_btc": scoped["unknown_btc"],
            "long_term_btc": scoped["long_term_btc"],
            "short_term_btc": scoped["short_term_btc"],
            "next_long_term_date": scoped["next_long_term_date"],
            "next_long_term_btc": scoped["next_long_term_btc"],
            "unresolved_btc": scoped["unresolved_btc"],
        })
    goal_overview = []
    for goal in goals:
        depot_id = str(goal.get("depot_id", ALL_DEPOTS))
        scoped = fifo if depot_id == ALL_DEPOTS else depot_results.get(depot_id, fifo_result([], long_term_days=long_term_days))
        target = decimal_value(goal.get("amount_btc"))
        current = scoped["total_btc"]
        remaining = max(target - current, Decimal("0"))
        currency = str(goal.get("currency", "EUR")).upper()
        raw_price = prices.get(currency)
        price = decimal_value(raw_price) if raw_price is not None else None
        reached_at = goal_reached_at(entries, target, depot_id) if target > 0 else None
        is_reached = bool(target > 0 and current >= target)
        goal_overview.append({
            **goal,
            "current_btc": current,
            "remaining_btc": remaining,
            "progress_percent": min(current / target * Decimal("100"), Decimal("100")) if target > 0 else ZERO,
            "is_reached": is_reached,
            "ever_reached": reached_at is not None,
            "goal_reached_at": reached_at,
            "current_fiat": current * price if price is not None else None,
            "target_fiat": target * price if price is not None else None,
            "remaining_fiat": remaining * price if price is not None else None,
        })
    return {"fifo": fifo, "depot_summaries": depot_summaries, "goals": goal_overview}


def _dashboard_fifo_summary(
    fifo: dict[str, Any], currencies: list[str]
) -> dict[str, Any]:
    """Return aggregate FIFO values without exposing individual lots/trades."""
    keys = (
        "total_btc", "known_btc", "unknown_btc", "long_term_btc",
        "short_term_btc", "unknown_holding_btc", "next_long_term_date",
        "next_long_term_btc", "realized", "realized_long_term",
        "realized_short_term", "purchase_fees", "income_fees", "sale_fees",
        "unresolved_btc", "oversold_btc", "long_term_days", "as_of",
    )
    result = {key: deepcopy(fifo.get(key)) for key in keys}
    result["currency_summaries"] = {
        str(currency).upper(): currency_summary_from_result(fifo, str(currency).upper())
        for currency in currencies
    }
    return result


def _dashboard_purchase_totals(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return only overview purchase aggregates, never notes or source IDs."""
    totals: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if entry.get("type") != "purchase":
            continue
        currency = str(entry.get("currency") or "").upper()
        if not currency:
            continue
        amount = max(decimal_value(entry.get("amount_btc")), Decimal("0"))
        price = max(decimal_value(entry.get("price")), Decimal("0"))
        fee = max(decimal_value(entry.get("fee")), Decimal("0"))
        if amount <= 0 or price <= 0:
            continue
        item = totals.setdefault(
            currency,
            {"fiat": Decimal("0"), "btc": Decimal("0"), "fees": Decimal("0"), "count": 0},
        )
        item["fiat"] += amount * price
        item["btc"] += amount
        item["fees"] += fee
        item["count"] += 1
    for item in totals.values():
        item["total_outlay"] = item["fiat"] + item["fees"]
    return totals


def _dashboard_depot_entry_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        depot_id = str(entry.get("depot_id") or DEFAULT_DEPOT_ID)
        counts[depot_id] = counts.get(depot_id, 0) + 1
    return counts


def _dashboard_ledger_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only fields required to render/edit the booking ledger.

    In particular, persisted source-identity hashes and exact BTC-fee metadata
    stay in Home Assistant Core.  Edit operations preserve those fields
    server-side, so the browser never needs them.
    """
    allowed = (
        "id", "type", "timestamp", "depot_id", "amount_btc",
        "currency", "price", "fee", "fee_btc", "fee_btc_affects_stack", "network", "note",
    )
    return [
        {key: deepcopy(entry.get(key)) for key in allowed if key in entry}
        for entry in entries
        if isinstance(entry, dict)
    ]


def _dashboard_ledger_fifo(fifo: dict[str, Any]) -> dict[str, Any]:
    """Return the minimum FIFO detail required by the ledger tab."""
    match_statuses: dict[str, list[str]] = {}
    for match in fifo.get("matches", []):
        sale_id = str(match.get("sale_id") or "")
        status = str(match.get("status") or "")
        if not sale_id or not status:
            continue
        values = match_statuses.setdefault(sale_id, [])
        if status not in values:
            values.append(status)
    return {
        "open_lots": [
            {
                "entry_id": lot.get("entry_id"),
                "holding_status": lot.get("holding_status", "unknown"),
                "long_term_date": lot.get("long_term_date"),
            }
            for lot in fifo.get("open_lots", [])
        ],
        "sales": {
            str(entry_id): {
                "status": value.get("status", "unknown"),
                "holding_status": value.get("holding_status", "unknown"),
            }
            for entry_id, value in fifo.get("sales", {}).items()
        },
        "expenses": {
            str(entry_id): {
                "status": value.get("status", "unknown"),
                "holding_status": value.get("holding_status", "unknown"),
            }
            for entry_id, value in fifo.get("expenses", {}).items()
        },
        "transaction_fees": {
            str(entry_id): {
                "status": value.get("status", "unknown"),
                "holding_status": value.get("holding_status", "unknown"),
            }
            for entry_id, value in fifo.get("transaction_fees", {}).items()
        },
        "match_statuses_by_sale": match_statuses,
    }


def _dashboard_fifo_matches(
    fifo: dict[str, Any], entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return FIFO disposal rows without exposing full ledger records or notes.

    Sales and priced BTC expenses both dispose of FIFO lots. The tax/FIFO view
    needs prices and currencies for display, but it does not
    need provider/import identifiers, notes, or the internal transaction IDs
    used to link the stored ledger. Resolve those links server-side and return
    a display-only row instead.
    """
    by_id = {str(entry.get("id")): entry for entry in entries if entry.get("id")}
    average_entry_by_disposition = cumulative_average_entry_price_by_disposition(entries)
    result: list[dict[str, Any]] = []
    # The UI may need to know whether several FIFO rows belong to one outgoing
    # booking, but it must not receive the internal ledger UUID. Map every
    # outgoing entry to a short response-local sequence number instead.
    disposition_indexes: dict[str, int] = {}
    for raw in fifo.get("matches", []):
        if not isinstance(raw, dict):
            continue
        purchase = by_id.get(str(raw.get("purchase_id") or ""), {})
        outgoing_id = str(raw.get("disposition_id") or raw.get("sale_id") or "")
        sale = by_id.get(outgoing_id, {})
        if outgoing_id and outgoing_id not in disposition_indexes:
            disposition_indexes[outgoing_id] = len(disposition_indexes) + 1
        row = {
            key: deepcopy(value)
            for key, value in raw.items()
            if key not in {"purchase_id", "sale_id", "disposition_id"}
        }
        row["disposition_index"] = disposition_indexes.get(outgoing_id)
        row["purchase_price"] = purchase.get("price")
        row["sale_price"] = sale.get("price")
        # Currency already exists on FIFO matches, but keep a safe fallback for
        # legacy cached rows without the newer fields.
        row["purchase_currency"] = raw.get("purchase_currency") or purchase.get("currency")
        row["sale_currency"] = raw.get("sale_currency") or sale.get("currency")

        # Separate, non-FIFO comparison: use the BTC-weighted effective average
        # acquisition price of every purchase in the same fiat currency up to
        # this disposal.  This answers whether the outgoing booking was above or
        # below the portfolio's average buy-in at that moment without changing
        # the legal/accounting FIFO result.  Only aggregate numbers cross the
        # panel boundary; no additional ledger identifiers are exposed.
        average_entry_price = average_entry_by_disposition.get(outgoing_id)
        row["average_entry_price_to_date"] = average_entry_price
        amount = decimal_value(raw.get("amount_btc"))
        net_proceeds = raw.get("net_proceeds")
        if average_entry_price is not None and amount > 0 and net_proceeds is not None:
            average_basis = amount * average_entry_price
            average_gain = decimal_value(net_proceeds) - average_basis
            row["average_entry_gain"] = average_gain
            row["average_entry_return_percent"] = (
                average_gain / average_basis * Decimal("100")
                if average_basis > 0
                else None
            )
        else:
            row["average_entry_gain"] = None
            row["average_entry_return_percent"] = None
        result.append(row)
    return result


def _dashboard_chart_ledger_events(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return note-free ledger events needed for local chart/performance math.

    The browser never needs notes, import fingerprints, provider transaction IDs
    or internal entry UUIDs to draw charts. Omitting them reduces both payload
    size and the amount of sensitive data present in the overview tab.
    """
    result: list[dict[str, Any]] = []
    for sequence, entry in enumerate(entries):
        kind = str(entry.get("type") or "")
        if kind not in {"purchase", "income", "stack", "sale", "expense", "network_fee"}:
            continue
        event = {
            "sequence": sequence,
            "type": kind,
            "timestamp": entry.get("timestamp"),
            "amount_btc": entry.get("amount_btc"),
            "depot_id": entry.get("depot_id", DEFAULT_DEPOT_ID),
        }
        if kind != "stack":
            event.update({
                "currency": entry.get("currency"),
                "price": entry.get("price"),
                "fee": entry.get("fee", 0),
            })
        if kind == "network_fee":
            event["network"] = entry.get("network", "onchain")
        if decimal_value(entry.get("fee_btc")) > 0:
            event["fee_btc"] = entry.get("fee_btc")
            if bool(entry.get("fee_btc_affects_stack")):
                event["fee_btc_affects_stack"] = True
        result.append(event)
    return result


def _with_requester(schema: vol.Schema) -> vol.Schema:
    """Compatibility wrapper: identity now comes only from ServiceCall.context."""
    return schema


async def _authenticated_service_user_id(hass: HomeAssistant, call: ServiceCall) -> str:
    """Return only the real authenticated Home Assistant service-call user.

    Caller-supplied user ids are deliberately unsupported. System-generated or
    user-less contexts cannot borrow a real user's portfolio permissions. Multiple
    HA users remain supported through the portfolio allowlist.
    """
    if not call.context.user_id:
        raise Unauthorized()
    context_user = await hass.auth.async_get_user(call.context.user_id)
    if context_user is None or getattr(context_user, "system_generated", False):
        raise Unauthorized()
    return str(context_user.id)


async def _authorize_call(
    hass: HomeAssistant,
    call: ServiceCall,
    entry_id: str,
    *,
    owner_only: bool = False,
    require_unlocked: bool = True,
) -> str:
    requester = await _authenticated_service_user_id(hass, call)
    security: BitcoinSecurityStore = _runtime(hass, entry_id)["security"]
    try:
        if owner_only:
            security.require_owner(requester)
        else:
            security.require_allowed(requester)
        if require_unlocked:
            security.require_unlocked(requester)
    except (VaultAccessDenied, VaultLockedError) as err:
        raise Unauthorized() from err
    return requester

def _runtime(hass: HomeAssistant, entry_id: str) -> dict[str, Any]:
    runtime = hass.data.get(DOMAIN, {}).get(entry_id)
    if not isinstance(runtime, dict) or "storage" not in runtime:
        raise vol.Invalid(f"Bitcoin Stack Tracker entry {entry_id} is not loaded")
    return runtime


def _notify_entities(runtime: dict[str, Any]) -> None:
    coordinator: BitcoinPriceCoordinator = runtime["coordinator"]
    coordinator.async_set_updated_data(
        coordinator.data or {"prices": {}, "errors": [], "updated_at": None}
    )


async def _refresh_structure_after_write(
    hass: HomeAssistant, entry_id: str, runtime: dict[str, Any]
) -> None:
    """Refresh structure changes without destroying an unlocked password session.

    Password unlock state intentionally exists only in RAM. Reloading the config
    entry after a goal write recreates BitcoinSecurityStore and therefore locks
    the user even though saving a goal is ordinary in-app activity. Password
    mode never exposes goal/depot balance sensors globally anyway, so a normal
    coordinator refresh is sufficient there. Unencrypted installations keep the
    historical reload behavior so newly-created structure sensors still appear.
    """
    security: BitcoinSecurityStore = runtime["security"]
    if security.encryption_mode == ENCRYPTION_PASSWORD:
        _notify_entities(runtime)
        return
    await hass.config_entries.async_reload(entry_id)


def _host_label(value: str) -> str:
    parsed = urlparse(str(value or ""))
    return (parsed.hostname or str(value or "")).strip() or "–"


def _connection_inventory(
    settings: dict[str, Any],
    history_data: dict[str, Any],
    network_security: dict[str, Any],
    price_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe configured and recently observed network paths for the owner UI."""
    observed = [
        dict(item)
        for item in network_security.get("connections", [])
        if isinstance(item, dict)
    ]
    observed_by_target = {
        str(item.get("target") or "").lower(): item for item in observed
    }
    active_by_target = {
        target: int(item.get("active", 0) or 0)
        for target, item in observed_by_target.items()
    }
    price_details = price_details if isinstance(price_details, dict) else {}

    live_sources: list[dict[str, Any]] = []
    for source in settings.get("sources", []):
        if not isinstance(source, dict):
            continue
        source_type = str(source.get("source_type") or "unknown")
        currencies = source.get("currencies")
        if not isinstance(currencies, list):
            currency = str(source.get("currency") or "").upper()
            currencies = [currency] if currency else []
        currencies = [str(value).upper() for value in currencies if value]
        if source_type == "kraken":
            # The legacy source id remains "kraken" for migration compatibility,
            # but live pricing is now a Tor-only arithmetic market average.
            providers = (
                ("Kraken public Ticker", "api.kraken.com", "Kraken"),
                ("Coinbase Exchange Ticker", "api.exchange.coinbase.com", "Coinbase"),
                ("Bitstamp public Ticker", "www.bitstamp.net", "Bitstamp"),
                ("CoinGecko Simple Price", "api.coingecko.com", "CoinGecko"),
            )
            for label, target, provider_name in providers:
                observed_item = observed_by_target.get(target.lower(), {})
                provider_prices: dict[str, float] = {}
                provider_status: dict[str, str] = {}
                for currency in currencies:
                    details = price_details.get(currency, {})
                    for row in details.get("providers", []) if isinstance(details, dict) else []:
                        if isinstance(row, dict) and row.get("name") == provider_name:
                            if isinstance(row.get("price"), (int, float)):
                                provider_prices[currency] = float(row["price"])
                            provider_status[currency] = str(row.get("status") or "unknown")
                live_sources.append({
                    "label": label,
                    "target": target,
                    "route": "tor",
                    "purpose": "live-price",
                    "currencies": currencies,
                    "active": active_by_target.get(target.lower(), 0),
                    "last_success_at": observed_item.get("last_success_at"),
                    "last_failure_at": observed_item.get("last_failure_at"),
                    "configured": True,
                    "provider_prices": provider_prices,
                    "provider_status": provider_status,
                })
            continue
        if source_type == "mempool":
            base_url = str(source.get("base_url") or "")
            target = _host_label(base_url)
            route = "tor" if mempool_source_uses_tor(source) else "local-direct"
            label = "Eigene mempool-Instanz" if bool(source.get("mempool_own_instance")) else "mempool API"
        elif source_type == "entity":
            target = str(source.get("entity_id") or "Home Assistant entity")
            route = "ha-local"
            label = "Home-Assistant-Kurssensor"
        else:
            target = source_type
            route = "unknown"
            label = source_type
        observed_item = observed_by_target.get(target.lower(), {})
        live_sources.append({
            "label": label,
            "target": target,
            "route": route,
            "purpose": "live-price",
            "currencies": currencies,
            "active": active_by_target.get(target.lower(), 0),
            "last_success_at": observed_item.get("last_success_at"),
            "last_failure_at": observed_item.get("last_failure_at"),
            "configured": True,
        })

    history_sources: list[dict[str, Any]] = []
    metadata = history_data.get("source_metadata", {})
    seen: set[tuple[str, str]] = set()
    if isinstance(metadata, dict):
        for currency, item in metadata.items():
            if not isinstance(item, dict):
                continue
            labels = [
                str(item.get("primary_history_source") or ""),
                str(item.get("fallback_history_source") or ""),
                str(item.get("preferred_history_source") or ""),
            ]
            configured_url = str(item.get("configured_base_url") or "")
            for label in labels:
                lower = label.lower()
                targets: list[str] = []
                if "blockchain.com" in lower:
                    targets.append("api.blockchain.info")
                if "coin metrics" in lower:
                    targets.append("community-api.coinmetrics.io")
                if "ecb" in lower:
                    targets.append("data-api.ecb.europa.eu")
                if "coingecko" in lower:
                    targets.append("api.coingecko.com")
                if "kraken" in lower:
                    targets.append("api.kraken.com")
                if "mempool" in lower and configured_url:
                    targets.append(_host_label(configured_url))
                for target in targets:
                    key = (target, str(currency).upper())
                    if key in seen:
                        continue
                    seen.add(key)
                    observed_item = observed_by_target.get(target.lower(), {})
                    history_sources.append({
                        "label": label or target,
                        "target": target,
                        "route": (
                            str(item.get("own_mempool_network_route") or "local-direct").lower()
                            if "mempool" in lower and configured_url
                            else "tor"
                        ),
                        "purpose": "history",
                        "currencies": [str(currency).upper()],
                        "active": active_by_target.get(target.lower(), 0),
                        "last_success_at": observed_item.get("last_success_at"),
                        "last_update": item.get("last_update"),
                        "configured": True,
                    })

    configured_currencies_list = configured_currencies(settings)
    for source in settings.get("sources", []):
        if not isinstance(source, dict) or source.get("source_type") != "mempool":
            continue
        if not bool(source.get("mempool_own_instance")):
            continue
        for currency in source.get("currencies", []):
            target = _host_label(str(source.get("base_url") or ""))
            key = (target, str(currency).upper())
            if key not in seen:
                seen.add(key)
                observed_item = observed_by_target.get(target.lower(), {})
                history_sources.append({
                    "label": "Eigene mempool-Instanz (bevorzugte Historie)",
                    "target": target,
                    "route": "tor" if mempool_source_uses_tor(source) else "local-direct",
                    "purpose": "history",
                    "currencies": [str(currency).upper()],
                    "active": active_by_target.get(target.lower(), 0),
                    "last_success_at": observed_item.get("last_success_at"),
                    "last_update": None,
                    "configured": True,
                })
    public_history = configured_currencies_list
    if bool(settings.get("history_enabled", True)) and public_history:
        policy_sources = [
            ("Blockchain.com market-price", "api.blockchain.info", public_history),
            ("Coin Metrics Community", "community-api.coinmetrics.io", public_history),
            ("ECB reference rates", "data-api.ecb.europa.eu", [code for code in public_history if code != "USD"]),
            ("CoinGecko fallback", "api.coingecko.com", public_history),
            ("Kraken layered OHLC", "api.kraken.com", [code for code in public_history if code in KRAKEN_CURRENCIES]),
            ("Bitstamp 2h/12h OHLC", "www.bitstamp.net", public_history),
        ]
        for label, target, currencies in policy_sources:
            for currency in currencies:
                key = (target, str(currency).upper())
                if key in seen:
                    continue
                seen.add(key)
                observed_item = observed_by_target.get(target.lower(), {})
                history_sources.append({
                    "label": label,
                    "target": target,
                    "route": "tor",
                    "purpose": "history",
                    "currencies": [str(currency).upper()],
                    "active": active_by_target.get(target.lower(), 0),
                    "last_success_at": observed_item.get("last_success_at"),
                    "last_update": None,
                    "configured": True,
                })

    averages = {
        str(currency).upper(): {
            "price": details.get("price"),
            "source_count": details.get("source_count"),
            "available_source_count": details.get("available_source_count"),
            "spread_pct": details.get("spread_pct"),
            "method": details.get("method"),
        }
        for currency, details in price_details.items()
        if isinstance(details, dict)
    }

    return {
        "policy": "local-direct-or-tor-only",
        "live_price_method": "arithmetic_mean_of_valid_public_quotes",
        "live_price_averages": averages,
        "live_price_sources": live_sources,
        "history_sources": history_sources,
        "observed_connections": observed,
        "system_sources": [
            {
                "label": "Tor SOCKS Gateway",
                "target": "Home Assistant internal Tor Gateway:9050",
                "route": "ha-local",
                "purpose": "internal",
                "active": 0,
                "configured": True,
            },
            {
                "label": "Core Fail-Closed Routing Policy",
                "target": "public direct networking blocked before connect",
                "route": "internal",
                "purpose": "internal",
                "active": 0,
                "configured": True,
            },
        ],
        "inventory_origin": "integration",
    }


async def _async_unlock_for_requester(
    hass: HomeAssistant,
    *,
    entry_id: str,
    requester: str,
    password: str,
    enforce_rate_limit: bool,
) -> dict[str, Any]:
    runtime = _runtime(hass, entry_id)
    storage: BitcoinLedgerStore = runtime["storage"]
    security: BitcoinSecurityStore = runtime["security"]
    try:
        security.require_allowed(requester)
    except VaultAccessDenied as err:
        raise Unauthorized() from err
    if enforce_rate_limit:
        _enforce_rate_limit(
            hass, entry_id=entry_id, user_id=requester, operation=SERVICE_UNLOCK_VAULT
        )
    try:
        await storage.async_unlock(password)
    except (PasswordDecryptionError, PasswordValidationError) as err:
        raise vol.Invalid(str(err)) from err
    security.mark_user_unlocked(requester)
    _rate_limiter(hass).clear_user(entry_id, requester, SERVICE_UNLOCK_VAULT)

    # Rehydrate Sats Sentinel from the authoritative encrypted user vault after
    # every successful unlock. The device-bound runtime cache normally survives
    # Home Assistant restarts and keeps monitoring while the vault is locked, but
    # this gives us a deterministic recovery path if that cache was missing,
    # damaged, or came from an older schema. Never block the vault unlock on
    # Fulcrum/mempool reachability: gap discovery runs as an integration task and
    # async_apply_full_config keeps the saved configuration even when the node is
    # temporarily unavailable.
    try:
        watch_config = normalize_watch_config(storage.wallet_watch_config)
        watch_manager = runtime.get("wallet_watch")
        if isinstance(watch_manager, WalletWatchManager):
            async def _restore_wallet_watch_after_unlock() -> None:
                try:
                    await watch_manager.async_restore_full_config(watch_config, poll=False)
                except Exception as err:  # recovery must never break vault unlock
                    _LOGGER.warning("Sats Sentinel restart recovery after vault unlock failed: %s", err)

            hass.async_create_task(
                _restore_wallet_watch_after_unlock(),
                f"Bitcoin Stack Tracker Sats Sentinel recovery {entry_id}",
            )
    except Exception as err:  # malformed legacy config must not block vault access
        _LOGGER.warning("Sats Sentinel configuration could not be queued after vault unlock: %s", err)

    entry = hass.config_entries.async_get_entry(entry_id)
    currencies = configured_currencies(effective_settings(entry)) if entry else []
    await storage.async_ensure_legacy_goal(
        effective_settings(entry).get(CONF_GOAL_BTC, 0) if entry else 0,
        currency=currencies[0] if currencies else "EUR",
    )
    if entry is not None and CONF_GOAL_BTC in entry.data:
        data = dict(entry.data)
        data.pop(CONF_GOAL_BTC, None)
        hass.config_entries.async_update_entry(entry, data=data)
    _notify_entities(runtime)
    result = security.public_status(requester)
    result["setup_required"] = storage.setup_required
    return result


_HISTORY_AUTO_CHECK_INTERVAL = timedelta(hours=6)
_HISTORY_COMPLETE_SYNC_INTERVAL = timedelta(hours=20)


async def _async_warm_market_assessment_history_scores(
    hass: HomeAssistant, entry: ConfigEntry, runtime: dict[str, Any]
) -> str:
    """Persist the causal score series after durable daily history changes.

    Intraday coordinator quotes are intentionally not part of this path. The
    history signature is derived only from the durable daily price series plus
    model inputs, so an unchanged history is a cheap cache hit while a newly
    added/corrected daily value triggers exactly one executor rebuild.
    """
    current_settings = effective_settings(entry)
    currencies = configured_currencies(current_settings)
    market_settings = normalize_buy_opportunity_settings(
        current_settings.get(CONF_BUY_OPPORTUNITY_SETTINGS), currencies
    )
    currency = market_settings["currency"]
    history_prices = runtime["history_storage"].data.get("prices", {}).get(currency, {})
    signature = await hass.async_add_executor_job(partial(
        market_assessment_history_signature,
        history_prices,
        currency=currency,
        settings=market_settings,
    ))
    cache: MarketAssessmentHistoryCache = runtime["market_assessment_history_cache"]
    if await cache.async_get_scores(signature) is not None:
        runtime["market_assessment_history_warm_status"] = "persistent-hit"
        return "persistent-hit"

    await cache.async_prepare(signature)
    compute_lock = runtime.setdefault("_market_assessment_history_compute_lock", asyncio.Lock())
    async with compute_lock:
        # A panel request may have filled the same generation while this warm-up
        # was waiting for the single history-model CPU slot.
        if await cache.async_get_scores(signature) is not None:
            runtime["market_assessment_history_warm_status"] = "persistent-hit"
            return "persistent-hit"
        score_cache = await hass.async_add_executor_job(partial(
            calculate_buy_opportunity_history_scores,
            history_prices,
            None,
            currency=currency,
            settings=market_settings,
            as_of_day=dt_util.utcnow().date(),
        ))
        stored = await cache.async_put_scores(signature, score_cache)
        status = "rebuilt" if stored else "stale-superseded"
        runtime["market_assessment_history_warm_status"] = status
        runtime["market_assessment_history_warmed_at"] = dt_util.utcnow().isoformat()
        return status


def _history_bootstrap_incomplete(entry: ConfigEntry, runtime: dict[str, Any]) -> bool:
    """Return True while any configured fiat history still needs all-time backfill."""
    settings = effective_settings(entry)
    currencies = configured_currencies(settings)
    state = runtime["history_storage"].data
    bootstrap = state.get("bootstrap_complete", {})
    return any(not bool(bootstrap.get(code)) for code in currencies)


def _configure_history_timer(
    hass: HomeAssistant,
    entry: ConfigEntry,
    runtime: dict[str, Any],
    *,
    enabled: bool | None = None,
    auto_sync: bool | None = None,
    sync_if_stale: bool = False,
) -> bool:
    """Update automatic history sync without reloading or locking the vault.

    Complete histories are refreshed about once per day.  Incomplete all-time
    histories are rechecked every six hours so a temporary Tor/provider outage
    does not leave Max history truncated until somebody presses the manual
    button.  The scheduled path calls ``async_sync_history`` directly and is
    therefore independent from the manual service rate limiter and from an open
    browser session.
    """
    if cancel := runtime.pop("cancel_history_sync", None):
        cancel()
    runtime["history_auto_timer_active"] = False

    settings = effective_settings(entry)
    history_enabled = (
        bool(settings.get(CONF_HISTORY_ENABLED, True))
        if enabled is None
        else bool(enabled)
    )
    history_auto_sync = (
        bool(settings.get(CONF_HISTORY_AUTO_SYNC, True))
        if auto_sync is None
        else bool(auto_sync)
    )
    if not history_enabled or not history_auto_sync:
        runtime["history_auto_last_result"] = "disabled"
        return False

    async def _scheduled_sync(_now: Any) -> None:
        now = dt_util.utcnow()
        runtime["history_auto_last_attempt"] = now.isoformat()
        try:
            incomplete = _history_bootstrap_incomplete(entry, runtime)
            last_sync = runtime["history_storage"].data.get("last_sync")
            last_sync_dt = dt_util.parse_datetime(last_sync) if last_sync else None
            if (
                not incomplete
                and last_sync_dt is not None
                and now - last_sync_dt < _HISTORY_COMPLETE_SYNC_INTERVAL
            ):
                runtime["history_auto_last_result"] = "complete-recent-skip"
                return
            result = await async_sync_history(
                hass, entry, runtime["storage"], runtime["history_storage"]
            )
            runtime["history_auto_last_result"] = (
                "completed-with-notes" if result.get("errors") else "success"
            )
            runtime["history_auto_last_success"] = dt_util.utcnow().isoformat()
            try:
                runtime["history_auto_market_cache"] = await _async_warm_market_assessment_history_scores(
                    hass, entry, runtime
                )
            except Exception:
                runtime["history_auto_market_cache"] = "warm-failed"
                _LOGGER.exception("Automatic market-assessment history cache warm-up failed")
            _notify_entities(runtime)
        except Exception:
            runtime["history_auto_last_result"] = "failed"
            _LOGGER.exception("Automatic Bitcoin history synchronization failed")

    runtime["cancel_history_sync"] = async_track_time_interval(
        hass, _scheduled_sync, _HISTORY_AUTO_CHECK_INTERVAL
    )
    runtime["history_auto_timer_active"] = True
    runtime["history_auto_check_interval_hours"] = int(
        _HISTORY_AUTO_CHECK_INTERVAL.total_seconds() // 3600
    )

    if sync_if_stale:
        last_sync = runtime["history_storage"].data.get("last_sync")
        last_sync_dt = dt_util.parse_datetime(last_sync) if last_sync else None
        recent_samples = runtime["history_storage"].price_samples_for_days(2)
        configured = configured_currencies(settings)
        intraday_missing = any(
            code in KRAKEN_CURRENCIES and len(recent_samples.get(code, {})) < 12
            for code in configured
        )
        incomplete = _history_bootstrap_incomplete(entry, runtime)
        if (
            last_sync_dt is None
            or dt_util.utcnow() - last_sync_dt > timedelta(hours=24)
            or intraday_missing
            or incomplete
        ):
            runtime["history_auto_last_result"] = "startup-sync-scheduled"
            hass.async_create_task(_scheduled_sync(dt_util.utcnow()))
    return True


def _validate_positive_transaction(amount_btc: Decimal, price: Any) -> None:
    if amount_btc <= 0 or decimal_value(price) <= 0:
        raise vol.Invalid("Amount and price must be greater than zero")


def _candidate_sale(call: ServiceCall, amount_btc: Decimal) -> dict[str, Any]:
    timestamp = parse_timestamp(call.data.get(CONF_TIMESTAMP))
    return {
        "id": "candidate_sale",
        "type": "sale",
        "timestamp": timestamp.isoformat(),
        "depot_id": call.data.get(CONF_DEPOT_ID, DEFAULT_DEPOT_ID),
        "amount_btc": btc_string(amount_btc),
        "currency": str(call.data[CONF_CURRENCY]).upper(),
        "price": money_string(decimal_value(call.data[CONF_PRICE])),
        "fee": money_string(decimal_value(call.data.get(CONF_FEE, 0))),
        "note": call.data.get(CONF_NOTE, ""),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _goal_overview(
    storage: BitcoinLedgerStore, prices: dict[str, Any]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    days = int(storage.tax_settings.get("long_term_days", DEFAULT_LONG_TERM_DAYS))
    for goal in storage.goals:
        depot_id = str(goal.get("depot_id", ALL_DEPOTS))
        fifo = fifo_result(
            storage.entries,
            None if depot_id == ALL_DEPOTS else depot_id,
            long_term_days=days,
        )
        target = decimal_value(goal.get("amount_btc"))
        current = fifo["total_btc"]
        remaining = max(target - current, Decimal("0"))
        currency = str(goal.get("currency", "EUR")).upper()
        price = decimal_value(prices.get(currency)) if prices.get(currency) is not None else None
        reached_at = goal_reached_at(storage.entries, target, depot_id) if target > 0 else None
        is_reached = bool(target > 0 and current >= target)
        result.append({
            **goal,
            "current_btc": current,
            "remaining_btc": remaining,
            "progress_percent": min(current / target * Decimal("100"), Decimal("100")) if target > 0 else ZERO,
            "is_reached": is_reached,
            "ever_reached": reached_at is not None,
            "goal_reached_at": reached_at,
            "current_fiat": current * price if price is not None else None,
            "target_fiat": target * price if price is not None else None,
            "remaining_fiat": remaining * price if price is not None else None,
        })
    return result


ZERO = Decimal("0")


async def _async_create_csv_export(
    hass: HomeAssistant, entry_id: str, delimiter: str = ";",
    output_dir: Path | None = None,
) -> dict[str, str]:
    """Create one private CSV/ZIP export and return its local paths."""
    runtime = _runtime(hass, entry_id)
    entry = hass.config_entries.async_get_entry(entry_id)
    storage: BitcoinLedgerStore = runtime["storage"]
    tax = storage.tax_settings
    return await hass.async_add_executor_job(
        partial(
            write_csv_export,
            output_dir=output_dir or Path(hass.config.path(f"{DOMAIN}_exports")),
            portfolio_name=entry.title if entry else "Bitcoin Stack",
            entries=storage.entries,
            depots=storage.depots,
            delimiter=delimiter,
            long_term_days=int(tax.get("long_term_days", DEFAULT_LONG_TERM_DAYS)),
            tax_note=str(tax.get("note", "")),
        )
    )


async def _request_user_from_http(
    hass: HomeAssistant,
    request: web.Request,
    forwarded_user_id: str = "",
) -> tuple[Any, str]:
    """Resolve the real authenticated Home Assistant user for a Core HTTP request.

    Never trust a caller-controlled header or query parameter for identity. Multiple
    HA users remain supported through the per-portfolio allowlist; this only prevents
    one authenticated request from pretending to be a different user.
    """
    del hass, forwarded_user_id
    user = request["hass_user"]
    if getattr(user, "system_generated", False):
        raise Unauthorized()
    return user, str(user.id)


async def _async_backup_payload(
    hass: HomeAssistant, entry_id: str, actor_user_id: str
) -> dict[str, Any]:
    runtime = _runtime(hass, entry_id)
    security: BitcoinSecurityStore = runtime["security"]
    security.require_owner(actor_user_id)
    security.require_unlocked(actor_user_id)
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None:
        raise vol.Invalid("Config entry was not found")
    storage: BitcoinLedgerStore = runtime["storage"]
    history_data = runtime["history_storage"].data
    return {
        "backup_type": "bitcoin_stack_tracker",
        "backup_schema": 2,
        "asset": "BTC",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "integration_version": VERSION,
        "portfolio_title": entry.title,
        # Portable backups intentionally contain only user-owned portfolio data.
        # Network routes, Tor/mempool configuration, HA access lists, encryption,
        # tax settings, chart caches and sync/source metadata are not portable.
        "ledger": {
            "entries": storage.entries,
            "depots": storage.depots,
            "goals": storage.goals,
        },
        "history": {
            "prices": history_data.get("prices", {}),
            "price_samples": history_data.get("price_samples", {}),
            "market_candles": history_data.get("market_candles", {}),
        },
        "notice": "Encrypted data-only backup: transactions, depots, goals and history.",
    }


def _validate_backup_payload(payload: dict[str, Any]) -> None:
    if payload.get("backup_type") != "bitcoin_stack_tracker":
        raise ValueError("Unsupported backup type")
    if int(payload.get("backup_schema", 0)) not in {1, 2}:
        raise ValueError("Unsupported backup schema")
    if payload.get("asset") != "BTC":
        raise ValueError("Only Bitcoin backups are accepted")
    ledger = payload.get("ledger")
    if not isinstance(ledger, dict):
        raise ValueError("Backup ledger is missing")
    entries = ledger.get("entries", [])
    depots = ledger.get("depots", [])
    goals = ledger.get("goals", [])
    if not isinstance(entries, list):
        raise ValueError("Backup ledger entries are invalid")
    if len(entries) > MAX_LEDGER_ENTRIES:
        raise ValueError("Backup contains too many ledger entries")
    if not isinstance(depots, list) or len(depots) > MAX_DEPOTS:
        raise ValueError("Backup contains too many depots")
    if not isinstance(goals, list) or len(goals) > MAX_GOALS:
        raise ValueError("Backup contains too many goals")
    for item in entries:
        if not isinstance(item, dict) or item.get("type") not in {
            "purchase", "income", "sale", "stack", "expense", "network_fee"
        }:
            raise ValueError("Backup contains an invalid ledger entry")
    if fifo_result(entries, long_term_days=365)["oversold_btc"] > 0:
        raise ValueError("Backup contains a sale without enough earlier BTC")



async def _async_update_encryption_entry(
    hass: HomeAssistant, entry_id: str, security: BitcoinSecurityStore
) -> None:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None:
        raise web.HTTPNotFound(text="Config entry was not found")
    data = dict(entry.data)
    data[CONF_ENCRYPTION_MODE] = security.encryption_mode
    data.pop(CONF_SETUP_TOKEN, None)
    hass.config_entries.async_update_entry(entry, data=data)



_HALVING_INTERVAL = 210_000
_HALVING_CACHE_TTL = timedelta(minutes=1)
_HALVING_CACHE_KEY = "_halving_markers"


def _halving_source_candidates(settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Return own mempool nodes first, with mempool.space as Tor fallback.

    Only sources explicitly marked as the user's own mempool instance may be
    contacted directly. The public fallback always goes through bundled Tor via
    ``async_routed_session`` and can never silently downgrade to Clearnet.
    """
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in settings.get(CONF_SOURCES, []):
        if not isinstance(raw, dict) or raw.get(CONF_SOURCE_TYPE) != SOURCE_MEMPOOL:
            continue
        if not bool(raw.get(CONF_MEMPOOL_OWN_INSTANCE, False)):
            continue
        base_url = str(raw.get(CONF_BASE_URL) or "").rstrip("/")
        if not base_url or base_url in seen:
            continue
        seen.add(base_url)
        sources.append(dict(raw))
    if DEFAULT_MEMPOOL_URL.rstrip("/") not in seen:
        sources.append({
            CONF_SOURCE_TYPE: SOURCE_MEMPOOL,
            CONF_BASE_URL: DEFAULT_MEMPOOL_URL,
            CONF_MEMPOOL_OWN_INSTANCE: False,
            CONF_VERIFY_SSL: True,
        })
    return sources


def _halving_source_label(source: dict[str, Any]) -> str:
    if bool(source.get(CONF_MEMPOOL_OWN_INSTANCE, False)):
        return "own mempool instance"
    return "mempool.space through Tor"


async def _halving_mempool_text(
    hass: HomeAssistant,
    settings: dict[str, Any],
    source: dict[str, Any],
    path: str,
) -> str:
    base_url = str(source.get(CONF_BASE_URL) or "").rstrip("/")
    target_url = f"{base_url}{path}"
    uses_tor = mempool_source_uses_tor(source)
    async with async_routed_session(
        hass,
        target_url=target_url,
        proxy_url=tor_proxy_from_settings(settings) if uses_tor else None,
        allow_local_direct=not uses_tor,
        verify_ssl=bool(source.get(CONF_VERIFY_SSL, True)),
    ) as (session, request_kwargs):
        async with asyncio.timeout(25):
            response = await session.get(target_url, **request_kwargs)
            response.raise_for_status()
            return (await async_text_limited(response, max_bytes=MAX_ERROR_RESPONSE_BYTES)).strip()


async def _halving_mempool_json(
    hass: HomeAssistant,
    settings: dict[str, Any],
    source: dict[str, Any],
    path: str,
) -> dict[str, Any]:
    base_url = str(source.get(CONF_BASE_URL) or "").rstrip("/")
    target_url = f"{base_url}{path}"
    uses_tor = mempool_source_uses_tor(source)
    async with async_routed_session(
        hass,
        target_url=target_url,
        proxy_url=tor_proxy_from_settings(settings) if uses_tor else None,
        allow_local_direct=not uses_tor,
        verify_ssl=bool(source.get(CONF_VERIFY_SSL, True)),
    ) as (session, request_kwargs):
        async with asyncio.timeout(25):
            response = await session.get(target_url, **request_kwargs)
            response.raise_for_status()
            payload = await async_json_limited(response)
    if not isinstance(payload, dict):
        raise ValueError("mempool block endpoint returned an invalid payload")
    return payload


async def _async_halving_markers(
    hass: HomeAssistant,
    settings: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Resolve historical Bitcoin halving timestamps from a mempool API.

    Block heights are the source of truth. Known past marker timestamps are
    immutable and therefore retained in a Core-local cache. The tip height is
    refreshed at most every minute, so the homepage block height and countdown stay current and when a future 210,000-block boundary
    becomes historical it is picked up automatically without an app update.
    """
    domain_data = hass.data.setdefault(DOMAIN, {})
    cached = domain_data.get(_HALVING_CACHE_KEY)
    if not isinstance(cached, dict):
        cached = {}
    now = datetime.now(timezone.utc)
    checked_at = dt_util.parse_datetime(str(cached.get("checked_at") or ""))
    cached_markers = cached.get("halvings") if isinstance(cached.get("halvings"), list) else []
    if (
        not force
        and cached_markers
        and checked_at is not None
        and now - checked_at.astimezone(timezone.utc) < _HALVING_CACHE_TTL
    ):
        return {**cached, "cached": True}

    by_height: dict[int, dict[str, Any]] = {}
    for item in cached_markers:
        if not isinstance(item, dict):
            continue
        try:
            height = int(item.get("height") or 0)
        except (TypeError, ValueError):
            continue
        if height > 0 and item.get("timestamp"):
            by_height[height] = dict(item)

    errors: list[str] = []
    for source in _halving_source_candidates(settings):
        label = _halving_source_label(source)
        try:
            tip_text = await _halving_mempool_text(hass, settings, source, "/api/blocks/tip/height")
            tip_height = int(tip_text)
            if tip_height < 0:
                raise ValueError("negative Bitcoin tip height")
            latest_halving = (tip_height // _HALVING_INTERVAL) * _HALVING_INTERVAL
            for height in range(_HALVING_INTERVAL, latest_halving + 1, _HALVING_INTERVAL):
                if height in by_height:
                    continue
                block_hash = await _halving_mempool_text(
                    hass, settings, source, f"/api/block-height/{height}"
                )
                if len(block_hash) != 64 or any(char not in "0123456789abcdefABCDEF" for char in block_hash):
                    raise ValueError(f"invalid block hash returned for height {height}")
                block = await _halving_mempool_json(
                    hass, settings, source, f"/api/block/{block_hash}"
                )
                timestamp = int(block.get("timestamp") or 0)
                returned_height = int(block.get("height") or height)
                if returned_height != height or timestamp <= 0:
                    raise ValueError(f"invalid block metadata returned for height {height}")
                moment = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                by_height[height] = {
                    "number": height // _HALVING_INTERVAL,
                    "height": height,
                    "timestamp": moment.isoformat(),
                    "date": moment.date().isoformat(),
                    "block_hash": block_hash,
                    "source": label,
                }
            next_height = ((tip_height // _HALVING_INTERVAL) + 1) * _HALVING_INTERVAL
            result = {
                "halvings": [by_height[key] for key in sorted(by_height)],
                "tip_height": tip_height,
                "next_halving_height": next_height,
                "blocks_to_next_halving": max(0, next_height - tip_height),
                "source": label,
                "checked_at": now.isoformat(),
                "cached": False,
                "errors": errors,
            }
            domain_data[_HALVING_CACHE_KEY] = result
            return result
        except Exception as err:  # noqa: BLE001 - cascade to Tor-routed public fallback
            errors.append(f"{label}: {type(err).__name__}: {err}"[:400])

    if by_height:
        result = {
            **cached,
            "halvings": [by_height[key] for key in sorted(by_height)],
            "checked_at": now.isoformat(),
            "cached": True,
            "stale": True,
            "errors": errors,
        }
        domain_data[_HALVING_CACHE_KEY] = result
        return result
    raise ValueError("Could not resolve Bitcoin halving blocks: " + " | ".join(errors))


_PANEL_STATE_VERSION = 1
_PANEL_STATE_KEY = f"{DOMAIN}.panel_state"
_PANEL_RPC_MAX_BYTES = 36 * 1024 * 1024
_PANEL_TOR_STATUS_CACHE_SECONDS = 30.0
_TECHNICAL_LOG_MAX_ENTRIES = 500
_TOR_ROTATION_INTERVALS = {10, 15, 30, 60, 120, 180, 360, 720, 1440}
_TOR_ROTATION_ENTRY_CHECK = timedelta(seconds=30)


def _technical_log_buffer(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Return the bounded non-secret technical log kept inside Core memory."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    log = domain_data.setdefault("_technical_log", [])
    if not isinstance(log, list):
        log = []
        domain_data["_technical_log"] = log
    return log


def _technical_log_append(hass: HomeAssistant, level: str, message: str) -> None:
    """Append technical metadata only; never pass request bodies or ledger data."""
    log = _technical_log_buffer(hass)
    log.append({
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "level": str(level or "INFO").upper()[:12],
        "message": str(message or "")[:1000],
    })
    if len(log) > _TECHNICAL_LOG_MAX_ENTRIES:
        del log[:-_TECHNICAL_LOG_MAX_ENTRIES]


def _technical_log_clear(hass: HomeAssistant) -> None:
    _technical_log_buffer(hass).clear()

_PANEL_BACKUP_WARNING_DAYS = {7, 14, 30, 60, 90}
_PANEL_RESTORE_WARNING_DAYS = {30, 90, 180, 365}


async def _panel_state(hass: HomeAssistant) -> dict[str, Any]:
    domain_data = hass.data.setdefault(DOMAIN, {})
    cached = domain_data.get("_panel_state")
    if isinstance(cached, dict):
        return cached
    store = Store[dict[str, Any]](hass, _PANEL_STATE_VERSION, _PANEL_STATE_KEY)
    loaded = await store.async_load()
    state = loaded if isinstance(loaded, dict) else {}
    state.setdefault("entries", {})
    domain_data["_panel_state"] = state
    domain_data["_panel_state_store"] = store
    return state


async def _save_panel_state(hass: HomeAssistant, state: dict[str, Any]) -> None:
    store = hass.data.setdefault(DOMAIN, {}).get("_panel_state_store")
    if store is None:
        await _panel_state(hass)
        store = hass.data[DOMAIN].get("_panel_state_store")
    if store is None:
        raise RuntimeError("Native panel state store is unavailable")
    await store.async_save(state)


async def _async_rotate_tor_if_due(
    hass: HomeAssistant,
    _now: Any = None,
    *,
    entry_id: str | None = None,
    trigger: str = "timer",
) -> dict[str, Any]:
    """Rotate SOCKS-auth isolation groups when their persisted deadline is due.

    The rotation scheduler has three deliberately redundant callers: the global
    Core timer, an entry-local timer, and the network-status poll used by the
    native panel.  A single lock plus the persisted ``last_rotated_at`` value
    make these callers idempotent.  This prevents a missed Home Assistant timer
    callback from leaving a configured 30-minute rotation dormant for hours.
    """
    domain_data = hass.data.setdefault(DOMAIN, {})
    lock = domain_data.get("_tor_rotation_lock")
    if not isinstance(lock, asyncio.Lock):
        lock = asyncio.Lock()
        domain_data["_tor_rotation_lock"] = lock

    async with lock:
        state = await _panel_state(hass)
        rotations = state.setdefault("tor_rotation", {})
        if not isinstance(rotations, dict):
            rotations = {}
            state["tor_rotation"] = rotations

        now = _now if isinstance(_now, datetime) else datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        else:
            now = now.astimezone(timezone.utc)

        candidates = (
            [(str(entry_id), rotations.get(str(entry_id)))]
            if entry_id
            else list(rotations.items())
        )
        due_entries: list[tuple[str, int]] = []
        for candidate_id, raw in candidates:
            if not isinstance(raw, dict) or not bool(raw.get("enabled")):
                continue
            try:
                interval = int(raw.get("interval_minutes") or 30)
            except (TypeError, ValueError):
                interval = 30
            if interval not in _TOR_ROTATION_INTERVALS:
                interval = 30

            last: datetime | None = None
            last_raw = raw.get("last_rotated_at")
            if last_raw:
                try:
                    last = datetime.fromisoformat(str(last_raw).replace("Z", "+00:00"))
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    else:
                        last = last.astimezone(timezone.utc)
                except ValueError:
                    last = None
            if last is None or now - last >= timedelta(minutes=interval):
                due_entries.append((str(candidate_id), interval))

        if not due_entries:
            return {"rotated": False, "entries": []}

        result = rotate_tor_isolation(hass)
        rotated_at = str(result["last_rotated_at"])
        for candidate_id, interval in due_entries:
            item = dict(rotations.get(candidate_id) or {})
            item["last_rotated_at"] = rotated_at
            item["method"] = "IsolateSOCKSAuth"
            item["last_trigger"] = trigger
            item["next_rotation_at"] = (
                datetime.fromisoformat(rotated_at.replace("Z", "+00:00"))
                + timedelta(minutes=interval)
            ).isoformat()
            rotations[candidate_id] = item

        await _save_panel_state(hass, state)
        _technical_log_append(
            hass,
            "INFO",
            "tor_auto_rotation status=rotated "
            f"trigger={trigger} interval_min={due_entries[0][1]} "
            f"entries={len(due_entries)} generation={result['tor_identity_generation']}",
        )
        _LOGGER.info(
            "Automatic Tor SOCKS isolation rotation completed (%s, %s minute interval, generation %s)",
            trigger,
            due_entries[0][1],
            result["tor_identity_generation"],
        )
        return {"rotated": True, "entries": [item[0] for item in due_entries], **result}


def _tor_rotation_settings_view(settings: dict[str, Any]) -> dict[str, Any]:
    """Return settings with a deterministic next rotation timestamp."""
    result = dict(settings)
    result.setdefault("enabled", False)
    try:
        interval = int(result.get("interval_minutes") or 30)
    except (TypeError, ValueError):
        interval = 30
    if interval not in _TOR_ROTATION_INTERVALS:
        interval = 30
    result["interval_minutes"] = interval
    result["method"] = "IsolateSOCKSAuth"
    last_raw = result.get("last_rotated_at")
    if bool(result.get("enabled")) and last_raw:
        try:
            last = datetime.fromisoformat(str(last_raw).replace("Z", "+00:00"))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            result["next_rotation_at"] = (
                last.astimezone(timezone.utc) + timedelta(minutes=interval)
            ).isoformat()
        except ValueError:
            result.pop("next_rotation_at", None)
    elif not bool(result.get("enabled")):
        result.pop("next_rotation_at", None)
    return result


async def _async_expire_vault_sessions(hass: HomeAssistant) -> None:
    """Enforce password-vault auto-lock in Core, even after the browser closes.

    Browser timers remain a UX convenience, but this Core timer is the security
    boundary: once the last finite unlock session expires, decrypted ledger data
    and the DEK are removed from the Home Assistant process. A timeout of zero
    is intentionally supported and means disabled for long setup sessions.
    """
    domain_data = hass.data.get(DOMAIN, {})
    for entry_id, runtime in list(domain_data.items()):
        if not isinstance(runtime, dict) or "security" not in runtime or "storage" not in runtime:
            continue
        security: BitcoinSecurityStore = runtime["security"]
        storage: BitcoinLedgerStore = runtime["storage"]
        expired = security.expire_unlock_sessions()
        if not expired or security.encryption_mode != ENCRYPTION_PASSWORD:
            continue
        if security.unlocked_user_count == 0 and not storage.is_locked:
            await storage.async_lock()
            _notify_entities(runtime)
            _LOGGER.info(
                "Core auto-lock cleared decrypted Bitcoin Stack Tracker state entry=%s expired_sessions=%d",
                str(entry_id)[-8:], len(expired),
            )


def _panel_backup_health(entry_id: str, raw: Any) -> dict[str, Any]:
    item = raw if isinstance(raw, dict) else {}
    backup_days = int(item.get("backup_warning_days", 30) or 30)
    restore_days = int(item.get("restore_test_warning_days", 180) or 180)
    if backup_days not in _PANEL_BACKUP_WARNING_DAYS:
        backup_days = 30
    if restore_days not in _PANEL_RESTORE_WARNING_DAYS:
        restore_days = 180
    now = datetime.now(timezone.utc)

    def age_days(value: Any) -> int | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0, int((now - parsed.astimezone(timezone.utc)).total_seconds() // 86400))
        except ValueError:
            return None

    backup_age = age_days(item.get("last_backup_at"))
    restore_age = age_days(item.get("last_restore_test_at"))
    return {
        "entry_id": entry_id,
        "backup_warning_days": backup_days,
        "restore_test_warning_days": restore_days,
        "last_backup_at": item.get("last_backup_at"),
        "last_restore_at": item.get("last_restore_at"),
        "last_restore_test_at": item.get("last_restore_test_at"),
        "backup_age_days": backup_age,
        "restore_test_age_days": restore_age,
        "backup_stale": backup_age is None or backup_age >= backup_days,
        "restore_test_due": restore_age is None or restore_age >= restore_days,
        "storage": "Home Assistant Core .storage",
    }


async def _panel_mark_health(hass: HomeAssistant, entry_id: str, **updates: Any) -> dict[str, Any]:
    state = await _panel_state(hass)
    entries = state.setdefault("entries", {})
    item = dict(entries.get(entry_id) or {})
    item.update(updates)
    entries[entry_id] = item
    await _save_panel_state(hass, state)
    return _panel_backup_health(entry_id, item)


async def _panel_call_service(
    hass: HomeAssistant,
    request: web.Request,
    service: str,
    data: dict[str, Any],
    actor_user_id: str,
) -> Any:
    if not hass.services.has_service(DOMAIN, service):
        raise web.HTTPServiceUnavailable(text="Bitcoin Stack Tracker actions are not ready")
    payload = dict(data)
    try:
        response = await hass.services.async_call(
            DOMAIN,
            service,
            payload,
            blocking=True,
            context=Context(user_id=actor_user_id),
            return_response=True,
        )
    except Unauthorized as err:
        raise web.HTTPForbidden(text="Access denied") from err
    except vol.Invalid as err:
        raise web.HTTPBadRequest(text=str(err)) from err
    return _json_safe(response)


def _panel_json_body(body_text: Any) -> dict[str, Any]:
    if body_text in {None, ""}:
        return {}
    try:
        value = json.loads(str(body_text))
    except json.JSONDecodeError as err:
        raise web.HTTPBadRequest(text="Request body must be JSON") from err
    if not isinstance(value, dict):
        raise web.HTTPBadRequest(text="Request body must be a JSON object")
    return value


def _panel_form_parts(body: Any) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    if body is None:
        return result
    if not isinstance(body, list) or len(body) > 32:
        raise web.HTTPBadRequest(text="Invalid native panel form")
    for raw in body:
        if not isinstance(raw, dict):
            raise web.HTTPBadRequest(text="Invalid native panel form item")
        name = str(raw.get("name") or "")[:128]
        if not name:
            continue
        result.setdefault(name, []).append(raw)
    return result


def _panel_text_part(parts: dict[str, list[dict[str, Any]]], name: str) -> str:
    values = parts.get(name, [])
    if not values:
        return ""
    item = values[-1]
    return str(item.get("value") or "") if item.get("kind") == "text" else ""


def _panel_file_part(parts: dict[str, list[dict[str, Any]]], name: str, max_bytes: int) -> tuple[str, bytes]:
    values = parts.get(name, [])
    if not values:
        raise web.HTTPBadRequest(text=f"{name} is required")
    item = values[-1]
    if item.get("kind") != "file":
        raise web.HTTPBadRequest(text=f"{name} must be a file")
    encoded = str(item.get("data_base64") or "")
    if len(encoded) > ((max_bytes + 2) // 3) * 4 + 8:
        raise web.HTTPRequestEntityTooLarge(max_size=max_bytes, actual_size=len(encoded))
    try:
        data = base64.b64decode(encoded, validate=True)
    except Exception as err:
        raise web.HTTPBadRequest(text=f"Invalid {name} encoding") from err
    if len(data) > max_bytes:
        raise web.HTTPRequestEntityTooLarge(max_size=max_bytes, actual_size=len(data))
    return str(item.get("filename") or name)[:255], data


async def _panel_restore_payload(
    hass: HomeAssistant, entry_id: str, actor_user_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    runtime = _runtime(hass, entry_id)
    security: BitcoinSecurityStore = runtime["security"]
    security.require_owner(actor_user_id)
    security.require_unlocked(actor_user_id)

    previous_ledger = await runtime["storage"].async_export()
    previous_history = runtime["history_storage"].data
    incoming_ledger = payload["ledger"]
    # Restore only the three portable ledger collections. Keep installation-local
    # tax settings, and invalidate the derived chart cache so it is rebuilt from
    # the restored transactions/history instead of accepting cache state from a file.
    restored_ledger = {
        "entries": incoming_ledger.get("entries", []),
        "depots": incoming_ledger.get("depots", []),
        "goals": incoming_ledger.get("goals", []),
        "tax_settings": previous_ledger.get("tax_settings", {}),
        "chart_cache": {"revision": None, "data": {}},
        # Sats Sentinel is installation-sensitive and not imported from a portable
        # backup, but an existing local watch configuration must survive restore.
        "wallet_watch": previous_ledger.get("wallet_watch", {}),
    }
    try:
        await runtime["storage"].async_replace(restored_ledger)
        if isinstance(payload.get("history"), dict):
            incoming_history = payload["history"]
            await runtime["history_storage"].async_replace({
                "prices": incoming_history.get("prices", {}),
                "price_samples": incoming_history.get("price_samples", {}),
                "market_candles": incoming_history.get("market_candles", {}),
            })
    except Exception as err:
        _LOGGER.exception("Native panel backup restore failed; rolling back")
        await runtime["storage"].async_replace(previous_ledger)
        await runtime["history_storage"].async_replace(previous_history)
        raise web.HTTPBadRequest(text=f"Backup restore failed: {err}") from err

    # Restores are data-only by design. Keep this installation's owner/allowlist,
    # encryption mode, Tor/mempool routes and all other configuration unchanged.
    security.mark_user_unlocked(actor_user_id)
    _notify_entities(runtime)
    return {
        "restored": True,
        "asset": "BTC",
        "entries": len(payload["ledger"].get("entries", [])),
        "depots": len(payload["ledger"].get("depots", [])),
        "goals": len(payload["ledger"].get("goals", [])),
    }


async def _panel_tor_exit_ip(hass: HomeAssistant, *, force: bool = False) -> str | None:
    """Resolve the public Tor exit IP through the fail-closed SOCKS route only."""
    state = network_security_snapshot(hass)
    generation = int(state.get("tor_identity_generation", 1) or 1)
    domain_data = hass.data.setdefault(DOMAIN, {})
    cache = domain_data.get("_tor_exit_ip_cache")
    now = datetime.now(timezone.utc)
    if isinstance(cache, dict) and cache.get("ip") and int(cache.get("generation", 0) or 0) == generation and not force:
        checked = dt_util.parse_datetime(str(cache.get("checked_at") or ""))
        if checked is not None and now - checked.astimezone(timezone.utc) < timedelta(minutes=10):
            return str(cache["ip"])

    providers = (
        # The route is already cryptographically constrained to the Tor SOCKS
        # connector, so the small IP-only endpoint can answer first.
        ("https://api.ipify.org?format=json", "ip", None),
        ("https://check.torproject.org/api/ip", "IP", "IsTor"),
    )
    for target_url, ip_key, tor_key in providers:
        try:
            async with async_routed_session(
                hass, target_url=target_url, proxy_url=DEFAULT_HISTORY_TOR_PROXY
            ) as (session, request_kwargs):
                async with asyncio.timeout(8):
                    response = await session.get(target_url, **request_kwargs)
                    response.raise_for_status()
                    payload = await async_json_limited(response)
            if tor_key is not None and payload.get(tor_key) is not True:
                continue
            candidate = str(payload.get(ip_key) or "").strip()
            ip_address(candidate)
            domain_data["_tor_exit_ip_cache"] = {
                "ip": candidate,
                "generation": generation,
                "checked_at": now.isoformat(),
                "source": target_url,
            }
            return candidate
        except Exception:  # noqa: BLE001 - display probe must never break Tor availability
            continue
    return None


async def _panel_tor_status(hass: HomeAssistant, *, force: bool = False) -> dict[str, Any]:
    """Return Core route status plus independently reported gateway transport state."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    now_monotonic = monotonic()
    cache = domain_data.get("_panel_tor_status_cache")
    if not force and isinstance(cache, dict):
        cached_at = float(cache.get("monotonic_at") or 0.0)
        cached_value = cache.get("value")
        if (
            cached_at > 0
            and now_monotonic - cached_at < _PANEL_TOR_STATUS_CACHE_SECONDS
            and isinstance(cached_value, dict)
        ):
            return deepcopy(cached_value)

    state = network_security_snapshot(hass)
    socks_connected = False
    socks_error: str | None = None
    gateway_host: str | None = None
    try:
        gateway_host = await async_tor_gateway_host()
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(gateway_host, 9050), timeout=2.5
        )
        socks_connected = True
        writer.close()
        await writer.wait_closed()
    except Exception as err:
        socks_error = f"{type(err).__name__}: Tor SOCKS proxy is not reachable"

    gateway: dict[str, Any] = {}
    gateway_error: str | None = None
    gateway_url = (
        f"http://{gateway_host}:8099/network-status" if gateway_host else None
    )
    try:
        if gateway_url is None:
            raise RuntimeError("Tor gateway DNS alias is unavailable")
        async with async_routed_session(
            hass,
            target_url=gateway_url,
            proxy_url=None,
            allow_local_direct=True,
            verify_ssl=False,
        ) as (session, request_kwargs):
            async with asyncio.timeout(3.0):
                response = await session.get(gateway_url, **request_kwargs)
                response.raise_for_status()
                payload = await async_json_limited(response)
        if isinstance(payload, dict):
            gateway = payload
    except Exception as err:
        gateway_error = f"{type(err).__name__}: Tor gateway telemetry is not reachable"

    firewall = bool(gateway.get("firewall_active"))
    tor_process = bool(gateway.get("tor_process_running"))
    leak = bool(gateway.get("clearnet_leak_detected"))
    tor_public = [str(value) for value in gateway.get("tor_public_socket_targets", []) if value]
    non_tor_public = [str(value) for value in gateway.get("non_tor_public_socket_targets", []) if value]
    blocked_gateway = int(gateway.get("blocked_ipv4_packets", 0) or 0) + int(gateway.get("blocked_ipv6_packets", 0) or 0)
    connected = socks_connected and firewall and tor_process and not leak
    error = socks_error or gateway_error or (
        "Tor gateway reported a non-Tor public socket" if leak else None
    )
    tor_exit_ip = await _panel_tor_exit_ip(hass, force=force) if connected else None
    result = {
        "killswitch_active": firewall,
        "killswitch_scope": "Tor-gateway nftables namespace + Core fail-closed route policy",
        "firewall_verified_from_core": bool(gateway),
        "tor_verified": connected,
        "tor_verification_scope": "SOCKS reachability + gateway nftables + Tor process + live transport sockets",
        "tor_connection_state": "connected" if connected else ("connecting" if socks_connected else "not-established"),
        "tor_bootstrap_percent": 100 if socks_connected and tor_process else 0,
        "tor_exit_ip": tor_exit_ip,
        "remote_dns_enforced": True,
        "safe_socks_enforced": True,
        # This field is intentionally gateway-only. Core route-policy rejects are
        # exposed separately via network_security_snapshot(); combining the two
        # made the UI look as if every pre-connect policy rejection was an
        # actual packet that tried to bypass Tor.
        "blocked_direct_packets": blocked_gateway,
        "gateway_blocked_direct_packets": blocked_gateway,
        "core_blocked_direct_requests": int(state.get("blocked_direct_requests", 0)),
        "non_tor_public_socket_count": len(non_tor_public),
        "non_tor_public_socket_targets": non_tor_public,
        "app_local_socket_targets": [
            f"Home Assistant Core → Tor Gateway SOCKS {gateway_host or 'unresolved'}:9050"
        ],
        "tor_public_socket_targets": tor_public,
        "clearnet_leak_detected": leak,
        "tor_error": error,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "gateway_status_at": gateway.get("updated_at"),
        "gateway_version": gateway.get("version"),
        "app_version": VERSION,
        "architecture": "native-core-panel + network-only Tor add-on",
        "transport_chain": [
            "Home Assistant Core",
            "internal SOCKS5 gateway",
            "Tor guard / circuit",
            "Tor exit relay",
            "HTTPS public API",
        ],
        "public_direct_fallback": False,
        "tor_identity_method": state.get("tor_identity_method"),
        "tor_identity_generation": state.get("tor_identity_generation"),
        "tor_last_rotated_at": state.get("tor_last_rotated_at"),
    }
    domain_data["_panel_tor_status_cache"] = {
        "monotonic_at": monotonic(),
        "value": deepcopy(result),
    }
    return result


class BitcoinStackNativePanelRpcView(HomeAssistantView):
    """Authenticated Browser → Home Assistant Core RPC for the native panel.

    This is deliberately hosted in Core. The Tor/network add-on is not an HTTP
    hop for portfolio data, CSV uploads, exports, master passwords or backup
    passwords.
    """

    url = "/api/bitcoin_stack_tracker/panel/rpc"
    name = "api:bitcoin_stack_tracker:native_panel_rpc"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def post(self, request: web.Request) -> web.Response:
        if request.content_length is not None and request.content_length > _PANEL_RPC_MAX_BYTES:
            raise web.HTTPRequestEntityTooLarge(max_size=_PANEL_RPC_MAX_BYTES, actual_size=request.content_length)
        _user, requester = await _request_user_from_http(self.hass, request)
        try:
            try:
                raw_body = await request.content.readexactly(_PANEL_RPC_MAX_BYTES + 1)
            except asyncio.IncompleteReadError as err:
                raw_body = err.partial
            if len(raw_body) > _PANEL_RPC_MAX_BYTES:
                raise web.HTTPRequestEntityTooLarge(
                    max_size=_PANEL_RPC_MAX_BYTES, actual_size=len(raw_body)
                )
            body = json.loads(raw_body.decode("utf-8"))
        except web.HTTPRequestEntityTooLarge:
            raise
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as err:
            raise web.HTTPBadRequest(text="Native panel request must be JSON") from err
        if not isinstance(body, dict):
            raise web.HTTPBadRequest(text="Native panel request must be an object")

        path = str(body.get("path") or "").lstrip("/")
        method = str(body.get("method") or "GET").upper()
        body_text = body.get("body_text")
        form = body.get("form")
        # Do not log body_text/form: either can carry passwords or portfolio CSV.
        parsed = urlsplit("/" + path)
        route = parsed.path.lstrip("/")
        query = parse_qs(parsed.query, keep_blank_values=True)
        q = lambda name, default="": str((query.get(name) or [default])[-1])

        request_started = monotonic()

        def respond(payload: Any) -> web.Response:
            _technical_log_append(
                self.hass,
                "INFO",
                f"route={route or '-'} method={method} status=200 duration_ms={int((monotonic() - request_started) * 1000)}",
            )
            response = self.json(payload)
            # Portfolio, ledger, FIFO and chart responses are authenticated but
            # financially sensitive. Never permit browser/proxy disk caching.
            response.headers["Cache-Control"] = "no-store, private, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response

        if route == "api/whoami" and method == "GET":
            user = request["hass_user"]
            return respond({"user_id": requester, "user_name": str(getattr(user, "name", "") or requester), "dev_mode": False, "architecture": "native-core-panel"})

        if route == "api/portfolios" and method == "GET":
            result = await _panel_call_service(self.hass, request, SERVICE_LIST_PORTFOLIOS, {}, requester)
            return respond(result)

        if route == "api/dashboard" and method == "GET":
            entry_id = q("entry_id")
            if not entry_id:
                raise web.HTTPBadRequest(text="entry_id is required")
            section = q("section", "summary") or "summary"
            if section not in DASHBOARD_SECTIONS:
                raise web.HTTPBadRequest(text="invalid dashboard section")
            result = await _panel_call_service(
                self.hass, request, SERVICE_DASHBOARD_DATA,
                {
                    CONF_CONFIG_ENTRY_ID: entry_id,
                    CONF_HISTORY_DAYS: int(q("history_days", "365") or 365),
                    CONF_HISTORY_INTERVAL: int(q("history_interval", "1440") or 1440),
                    CONF_DASHBOARD_SECTION: section,
                }, requester,
            )
            if isinstance(result, dict):
                result["addon_version"] = VERSION
                result["integration_version"] = VERSION
                result["architecture"] = "native-core-panel"
                # Never overwrite the redacted non-owner inventory produced by
                # dashboard_data. This used to reintroduce internal source
                # details after the authorization-aware service returned.
                if section in {"summary", "all"}:
                    security = _runtime(self.hass, entry_id)["security"]
                    if security.is_owner(requester):
                        result["connection_inventory"] = _connection_inventory(
                            effective_settings(self.hass.config_entries.async_get_entry(entry_id)),
                            _runtime(self.hass, entry_id)["history_storage"].data,
                            network_security_snapshot(self.hass),
                            (self.hass.data[DOMAIN][entry_id]["coordinator"].data or {}).get("price_details", {}),
                        )
            return respond(result)

        if route == "api/security/users" and method == "GET":
            result = await _panel_call_service(
                self.hass, request, SERVICE_LIST_USERS, {CONF_CONFIG_ENTRY_ID: q("entry_id")}, requester
            )
            return respond(result)

        if route == "api/security/session" and method == "POST":
            incoming = _panel_json_body(body_text)
            entry_id = str(incoming.get("entry_id") or "")
            if not entry_id:
                raise web.HTTPBadRequest(text="entry_id is required")
            runtime = _runtime(self.hass, entry_id)
            security: BitcoinSecurityStore = runtime["security"]
            try:
                minutes = int(incoming.get("auto_lock_minutes", 15))
                security.configure_user_auto_lock(requester, minutes, touch=bool(incoming.get("touch", True)))
            except VaultAccessDenied as err:
                raise web.HTTPForbidden(text="Access denied") from err
            except VaultLockedError as err:
                raise web.HTTPForbidden(text="Vault must be unlocked") from err
            except (TypeError, ValueError) as err:
                raise web.HTTPBadRequest(text=str(err)) from err
            return respond({
                "auto_lock_minutes": security.user_auto_lock_minutes(requester),
                "unlock_expires_in_seconds": security.user_unlock_expires_in_seconds(requester),
                "core_enforced": True,
            })

        if route.startswith("api/service/") and method == "POST":
            service = route.removeprefix("api/service/")
            if service not in DASHBOARD_ACTION_SERVICES:
                raise web.HTTPForbidden(text="Service is not allowed from the native panel")
            result = await _panel_call_service(self.hass, request, service, _panel_json_body(body_text), requester)
            return respond(result)

        if route.startswith("api/vault/") and method == "POST":
            # Secret-bearing operations deliberately bypass Home Assistant's
            # service bus. Passwords are handled only inside this authenticated
            # Core request and the ledger store; the Tor add-on and service-call
            # event/logging path never receive them.
            operation = route.removeprefix("api/vault/")
            entry_id = q("entry_id")
            if not entry_id:
                raise web.HTTPBadRequest(text="entry_id is required")
            runtime = _runtime(self.hass, entry_id)
            storage: BitcoinLedgerStore = runtime["storage"]
            security: BitcoinSecurityStore = runtime["security"]
            password = ""
            current_password = ""
            new_password = ""
            secrets_body: dict[str, Any] | None = None
            try:
                if operation == "unlock":
                    password = str(body_text or "")
                    result = await _async_unlock_for_requester(
                        self.hass,
                        entry_id=entry_id,
                        requester=requester,
                        password=password,
                        enforce_rate_limit=True,
                    )
                elif operation == "enable":
                    security.require_owner(requester)
                    _enforce_rate_limit(
                        self.hass, entry_id=entry_id, user_id=requester,
                        operation=SERVICE_SET_ENCRYPTION,
                    )
                    password = str(body_text or "")
                    if storage.is_locked and not storage.setup_required:
                        raise vol.Invalid("Unlock the current vault before changing encryption")
                    if storage.setup_required:
                        await storage.async_initialize_password(password)
                    elif security.encryption_mode != ENCRYPTION_PASSWORD:
                        await storage.async_enable_password(password)
                    else:
                        raise vol.Invalid("Password encryption is already enabled")
                    security.mark_user_unlocked(requester)
                    await _async_update_encryption_entry(self.hass, entry_id, security)
                    result = security.public_status(requester)
                elif operation == "disable":
                    security.require_owner(requester)
                    security.require_unlocked(requester)
                    watch_config = storage.wallet_watch_config
                    if isinstance(watch_config, dict) and (watch_config.get("monitors") or watch_config.get("notification_targets")):
                        raise vol.Invalid("Remove all Sats Sentinel targets and notification endpoints before disabling vault encryption")
                    if security.encryption_mode == ENCRYPTION_PASSWORD:
                        await storage.async_disable_password()
                    elif security.encryption_mode == ENCRYPTION_NONE:
                        raise vol.Invalid("Password encryption is already disabled")
                    else:
                        await security.async_set_encryption_mode(ENCRYPTION_NONE)
                        await storage._async_save()  # migrate legacy beta encryption
                    await _async_update_encryption_entry(self.hass, entry_id, security)
                    result = security.public_status(requester)
                elif operation == "change-password":
                    security.require_owner(requester)
                    security.require_unlocked(requester)
                    _enforce_rate_limit(
                        self.hass, entry_id=entry_id, user_id=requester,
                        operation=SERVICE_CHANGE_VAULT_PASSWORD,
                    )
                    secrets_body = _panel_json_body(body_text)
                    current_password = str(secrets_body.get(CONF_CURRENT_PASSWORD) or "")
                    new_password = str(secrets_body.get(CONF_NEW_PASSWORD) or "")
                    if not current_password or not new_password:
                        raise vol.Invalid("Current and new passwords are required")
                    await storage.async_change_password(current_password, new_password)
                    security.lock_all_users()
                    security.mark_user_unlocked(requester)
                    result = security.public_status(requester)
                else:
                    raise web.HTTPNotFound(text="Unknown vault operation")
            except VaultAccessDenied as err:
                raise web.HTTPForbidden(text="Access denied") from err
            except VaultLockedError as err:
                raise web.HTTPForbidden(text="Vault must be unlocked") from err
            except Unauthorized as err:
                raise web.HTTPForbidden(text="Access denied") from err
            except (PasswordDecryptionError, PasswordValidationError, ValueError, vol.Invalid) as err:
                raise web.HTTPBadRequest(text=str(err)) from err
            finally:
                password = ""
                current_password = ""
                new_password = ""
                if secrets_body is not None:
                    secrets_body.clear()
                body_text = None
            if operation in {"enable", "disable"}:
                # Encryption-mode changes affect entity exposure. Reload only
                # after secrets have gone out of scope.
                await self.hass.config_entries.async_reload(entry_id)
            return respond(result)

        if route == "api/import/preview" and method == "POST":
            parts = _panel_form_parts(form)
            entry_id = _panel_text_part(parts, "entry_id")
            if not entry_id:
                raise web.HTTPBadRequest(text="entry_id is required")
            runtime = _runtime(self.hass, entry_id)
            try:
                runtime["security"].require_unlocked(requester)
            except (VaultAccessDenied, VaultLockedError) as err:
                raise web.HTTPForbidden(text="Access denied") from err
            _enforce_rate_limit(
                self.hass, entry_id=entry_id, user_id=requester, operation="import_preview"
            )
            filename, upload = _panel_file_part(parts, "file", MAX_IMPORT_BYTES)
            depot_id = _panel_text_part(parts, "depot_id") or DEFAULT_DEPOT_ID
            if not runtime["storage"].has_depot(depot_id):
                raise web.HTTPBadRequest(text="Unknown depot")
            try:
                result = await self.hass.async_add_executor_job(parse_transaction_upload, upload, filename)
                preview_rows = [
                    {**row, "depot_id": depot_id}
                    for row in result.get("rows", [])
                    if isinstance(row, dict)
                ]
                flags = await runtime["storage"].async_import_duplicate_flags(preview_rows)
                for row, duplicate in zip(result.get("rows", []), flags, strict=False):
                    if isinstance(row, dict):
                        row["duplicate"] = bool(duplicate)
            except ValueError as err:
                raise web.HTTPBadRequest(text=str(err)) from err
            finally:
                upload = b""
            result["entry_id"] = entry_id
            return respond(result)

        if route == "api/import/duplicates" and method == "POST":
            payload = _panel_json_body(body_text)
            entry_id = str(payload.get("entry_id") or "")
            runtime = _runtime(self.hass, entry_id)
            try:
                runtime["security"].require_unlocked(requester)
            except (VaultAccessDenied, VaultLockedError) as err:
                raise web.HTTPForbidden(text="Access denied") from err
            rows = payload.get("rows")
            if not isinstance(rows, list) or len(rows) > 5_000:
                raise web.HTTPBadRequest(text="Invalid import duplicate-check payload")
            try:
                _enforce_rate_limit(
                    self.hass, entry_id=entry_id, user_id=requester,
                    operation="import_duplicates",
                )
            except vol.Invalid as err:
                raise web.HTTPTooManyRequests(text=str(err)) from err
            # Only normalized financial/import-identity fields are accepted by
            # the storage checker; notes and optional source fields are neither
            # required nor returned. Existing ledger hashes remain Core-only.
            flags = await runtime["storage"].async_import_duplicate_flags(rows)
            return respond({"duplicates": flags})

        if route == "api/download" and method == "GET":
            entry_id, delimiter = q("entry_id"), q("delimiter", ";")
            runtime = _runtime(self.hass, entry_id)
            runtime["security"].require_unlocked(requester)
            with TemporaryDirectory(prefix="bitcoin-stack-export-") as temp_dir:
                paths = await _async_create_csv_export(self.hass, entry_id, delimiter, Path(temp_dir))
                zip_path = Path(paths["zip"])
                data = await self.hass.async_add_executor_job(zip_path.read_bytes)
                return respond({"__file__": {"filename": zip_path.name, "mime": "application/zip", "data_base64": base64.b64encode(data).decode("ascii")}})

        if route == "api/backup" and method == "POST":
            entry_id = q("entry_id")
            _enforce_rate_limit(
                self.hass, entry_id=entry_id, user_id=requester, operation="backup"
            )
            password = str(body_text or "")
            try:
                payload = await _async_backup_payload(self.hass, entry_id, requester)
                envelope = await self.hass.async_add_executor_job(partial(create_backup_envelope, payload, password=password))
            except (VaultAccessDenied, VaultLockedError) as err:
                raise web.HTTPForbidden(text="Owner access and unlocked vault are required") from err
            except (PasswordValidationError, ValueError) as err:
                raise web.HTTPBadRequest(text=str(err)) from err
            finally:
                password = ""
                body_text = None
            data = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            await _panel_mark_health(self.hass, entry_id, last_backup_at=datetime.now(timezone.utc).isoformat())
            return respond({"__file__": {"filename": f"bitcoin-stack-backup-{stamp}.bstbackup", "mime": "application/octet-stream", "data_base64": base64.b64encode(data).decode("ascii")}})

        if route == "api/restore" and method == "POST":
            entry_id = q("entry_id")
            runtime = _runtime(self.hass, entry_id)
            try:
                runtime["security"].require_owner(requester)
                runtime["security"].require_unlocked(requester)
            except (VaultAccessDenied, VaultLockedError) as err:
                raise web.HTTPForbidden(text="Owner access and unlocked vault are required") from err
            _enforce_rate_limit(
                self.hass, entry_id=entry_id, user_id=requester, operation="restore"
            )
            parts = _panel_form_parts(form)
            password = _panel_text_part(parts, "password")
            _filename, backup_bytes = _panel_file_part(parts, "backup", 25 * 1024 * 1024)
            try:
                payload = await self.hass.async_add_executor_job(_validate_and_decrypt_backup_bytes, backup_bytes, password)
                result = await _panel_restore_payload(self.hass, entry_id, requester, payload)
            except (PasswordDecryptionError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as err:
                raise web.HTTPBadRequest(text=str(err)) from err
            finally:
                password = ""
                backup_bytes = b""
            now = datetime.now(timezone.utc).isoformat()
            await _panel_mark_health(self.hass, entry_id, last_restore_at=now, last_restore_test_at=now)
            return respond(result)

        if route == "api/wallet-watch" and method == "GET":
            entry_id = q("entry_id")
            runtime = _runtime(self.hass, entry_id)
            try:
                runtime["security"].require_owner(requester)
                runtime["security"].require_unlocked(requester)
            except (VaultAccessDenied, VaultLockedError) as err:
                raise web.HTTPForbidden(text="Owner access and unlocked vault are required") from err
            manager: WalletWatchManager = runtime["wallet_watch"]
            # Reconcile the unlocked password-vault copy with the richer
            # device-bound Sentinel runtime vault before returning settings.
            # This prevents an older/empty vault snapshot from hiding existing
            # wallet cards or making Auto incorrectly fall back to the own
            # mempool source after lock -> unlock.
            config = await manager.async_recover_unlocked_config(
                normalize_watch_config(runtime["storage"].wallet_watch_config)
            )
            notify_services = sorted(self.hass.services.async_services().get("notify", {}).keys())
            return respond({
                "config": config,
                "status": manager.public_status(include_addresses=True),
                "notify_services": notify_services,
                "activity_log": manager.public_activity_log(config, page=1, category="all"),
            })

        if route == "api/wallet-watch/status" and method == "GET":
            entry_id = q("entry_id")
            runtime = _runtime(self.hass, entry_id)
            try:
                runtime["security"].require_owner(requester)
            except VaultAccessDenied as err:
                raise web.HTTPForbidden(text="Owner access is required") from err
            return respond(runtime["wallet_watch"].public_status(include_addresses=False))

        if route == "api/wallet-watch/manage" and method == "GET":
            entry_id = q("entry_id")
            runtime = _runtime(self.hass, entry_id)
            try:
                runtime["security"].require_owner(requester)
            except VaultAccessDenied as err:
                raise web.HTTPForbidden(text="Owner access is required") from err
            manager: WalletWatchManager = runtime["wallet_watch"]
            return respond({
                "config": manager.public_locked_management_config(),
                "status": manager.public_status(include_addresses=True),
            })

        if route == "api/wallet-watch/log" and method == "GET":
            entry_id = q("entry_id")
            runtime = _runtime(self.hass, entry_id)
            try:
                runtime["security"].require_owner(requester)
                runtime["security"].require_unlocked(requester)
            except (VaultAccessDenied, VaultLockedError) as err:
                raise web.HTTPForbidden(text="Owner access and unlocked vault are required") from err
            config = normalize_watch_config(runtime["storage"].wallet_watch_config)
            try:
                page = max(1, int(q("page") or 1))
            except ValueError:
                page = 1
            try:
                page_size = min(25, max(1, int(q("page_size") or 10)))
            except ValueError:
                page_size = 10
            category = str(q("category") or "all").lower()
            return respond(runtime["wallet_watch"].public_activity_log(config, page=page, category=category, page_size=page_size))

        if route == "api/wallet-watch/transactions" and method == "GET":
            entry_id = q("entry_id")
            runtime = _runtime(self.hass, entry_id)
            try:
                runtime["security"].require_owner(requester)
                runtime["security"].require_unlocked(requester)
            except (VaultAccessDenied, VaultLockedError) as err:
                raise web.HTTPForbidden(text="Owner access and unlocked vault are required") from err
            config = normalize_watch_config(runtime["storage"].wallet_watch_config)
            monitor_id = str(q("monitor_id") or "")
            try:
                raw_limit = q("limit")
                requested_limit = None if raw_limit in {None, ""} else int(raw_limit)
            except ValueError:
                requested_limit = None
            try:
                page = max(1, int(q("page") or 1))
            except ValueError:
                page = 1
            try:
                result = await runtime["wallet_watch"].async_monitor_transactions(
                    config, monitor_id=monitor_id, limit=requested_limit, page=page
                )
            except (ValueError, OSError, asyncio.TimeoutError, ConnectionError, RuntimeError) as err:
                raise web.HTTPBadRequest(text=f"Sats Sentinel transaction overview failed: {type(err).__name__}: {err}") from err
            return respond(result)

        if route == "api/wallet-watch/upsert-monitor" and method == "POST":
            incoming = _panel_json_body(body_text)
            entry_id = str(incoming.get("entry_id") or "")
            monitor = incoming.get("monitor")
            runtime = _runtime(self.hass, entry_id)
            try:
                runtime["security"].require_owner(requester)
            except VaultAccessDenied as err:
                raise web.HTTPForbidden(text="Owner access is required") from err
            if runtime["security"].encryption_mode != ENCRYPTION_PASSWORD:
                raise web.HTTPBadRequest(text="Sats Sentinel requires the password-encrypted vault before watch-only data can be stored")
            manager: WalletWatchManager = runtime["wallet_watch"]
            unlocked = runtime["security"].is_user_unlocked(requester)
            try:
                if unlocked:
                    result = await manager.async_upsert_monitor(monitor)
                else:
                    result = await manager.async_upsert_runtime_monitor(monitor)
            except ValueError as err:
                raise web.HTTPBadRequest(text=f"Sats Sentinel watch save failed: {err}") from err
            except Exception as err:
                _LOGGER.exception("Sats Sentinel monitor save failed")
                raise web.HTTPInternalServerError(
                    text=f"Sats Sentinel watch save failed: {type(err).__name__}: {err}"
                ) from err
            result["notify_services"] = sorted(self.hass.services.async_services().get("notify", {}).keys())
            result["activity_log"] = (
                manager.public_activity_log(result["config"], page=1, category="all")
                if unlocked else {"items": [], "page": 1, "pages": 1, "total": 0, "stored_total": 0}
            )
            result["locked_runtime_edit"] = not unlocked
            return respond(result)

        if route == "api/wallet-watch/remove-monitor" and method == "POST":
            incoming = _panel_json_body(body_text)
            entry_id = str(incoming.get("entry_id") or "")
            monitor_id = str(incoming.get("monitor_id") or "")
            runtime = _runtime(self.hass, entry_id)
            try:
                runtime["security"].require_owner(requester)
            except VaultAccessDenied as err:
                raise web.HTTPForbidden(text="Owner access is required") from err
            manager: WalletWatchManager = runtime["wallet_watch"]
            unlocked = runtime["security"].is_user_unlocked(requester)
            try:
                if unlocked:
                    result = await manager.async_remove_monitor(monitor_id)
                else:
                    result = await manager.async_remove_runtime_monitor(monitor_id)
            except ValueError as err:
                raise web.HTTPBadRequest(text=f"Sats Sentinel remove failed: {err}") from err
            except Exception as err:  # defensive: return an actionable message instead of an opaque 500
                _LOGGER.exception("Sats Sentinel monitor removal failed")
                raise web.HTTPInternalServerError(
                    text=f"Sats Sentinel remove failed: {type(err).__name__}: {err}"
                ) from err
            result["notify_services"] = sorted(self.hass.services.async_services().get("notify", {}).keys())
            result["activity_log"] = (
                manager.public_activity_log(result["config"], page=1, category="all")
                if unlocked else {"items": [], "page": 1, "pages": 1, "total": 0, "stored_total": 0}
            )
            result["locked_runtime_edit"] = not unlocked
            return respond(result)

        if route == "api/wallet-watch" and method == "POST":
            incoming = _panel_json_body(body_text)
            entry_id = str(incoming.get("entry_id") or "")
            runtime = _runtime(self.hass, entry_id)
            try:
                runtime["security"].require_owner(requester)
                runtime["security"].require_unlocked(requester)
            except (VaultAccessDenied, VaultLockedError) as err:
                raise web.HTTPForbidden(text="Owner access and unlocked vault are required") from err
            try:
                config = normalize_watch_config(incoming.get("config"))
                if (config.get("monitors") or config.get("notification_targets")) and runtime["security"].encryption_mode != ENCRYPTION_PASSWORD:
                    raise ValueError("Sats Sentinel requires the password-encrypted vault before watch-only data or notification credentials can be stored")
                # Server/global settings are isolated from the watch list. Saving
                # Fulcrum/Tor/poll defaults must never rebuild, delete or collapse
                # already discovered address/xpub runtime state.
                result = await runtime["wallet_watch"].async_update_settings(config)
                config = result["config"]
                status = result["status"]
            except ValueError as err:
                raise web.HTTPBadRequest(text=str(err)) from err
            return respond({"saved": True, "config": config, "status": status, "notify_services": sorted(self.hass.services.async_services().get("notify", {}).keys()), "activity_log": runtime["wallet_watch"].public_activity_log(config, page=1, category="all")})

        if route == "api/wallet-watch/source-test" and method == "POST":
            incoming = _panel_json_body(body_text)
            entry_id = str(incoming.get("entry_id") or "")
            runtime = _runtime(self.hass, entry_id)
            try:
                runtime["security"].require_owner(requester)
                runtime["security"].require_unlocked(requester)
            except (VaultAccessDenied, VaultLockedError) as err:
                raise web.HTTPForbidden(text="Owner access and unlocked vault are required") from err
            try:
                config = normalize_watch_config(incoming.get("config"))
                result = await runtime["wallet_watch"].async_test_source(config)
            except (ValueError, OSError, asyncio.TimeoutError, ConnectionError, RuntimeError) as err:
                raise web.HTTPBadRequest(text=f"Sats Sentinel source test failed: {type(err).__name__}: {err}") from err
            return respond(result)

        if route == "api/wallet-watch/poll" and method == "POST":
            incoming = _panel_json_body(body_text)
            entry_id = str(incoming.get("entry_id") or "")
            runtime = _runtime(self.hass, entry_id)
            try:
                runtime["security"].require_owner(requester)
            except VaultAccessDenied as err:
                raise web.HTTPForbidden(text="Owner access is required") from err
            return respond(await runtime["wallet_watch"].async_poll(force=True))

        if route == "api/wallet-watch/simulate" and method == "POST":
            incoming = _panel_json_body(body_text)
            entry_id = str(incoming.get("entry_id") or "")
            runtime = _runtime(self.hass, entry_id)
            try:
                runtime["security"].require_owner(requester)
                runtime["security"].require_unlocked(requester)
            except (VaultAccessDenied, VaultLockedError) as err:
                raise web.HTTPForbidden(text="Owner access and unlocked vault are required") from err
            try:
                result = await runtime["wallet_watch"].async_simulate_activity(
                    monitor_id=str(incoming.get("monitor_id") or ""),
                    direction=str(incoming.get("direction") or "outgoing"),
                    amount_sats=int(incoming.get("amount_sats") or 100000),
                    confirmed=bool(incoming.get("confirmed", False)),
                    rbf=bool(incoming.get("rbf", False)),
                )
            except (TypeError, ValueError) as err:
                raise web.HTTPBadRequest(text=str(err)) from err
            return respond(result)

        if route == "api/wallet-watch/live-test" and method == "POST":
            incoming = _panel_json_body(body_text)
            entry_id = str(incoming.get("entry_id") or "")
            runtime = _runtime(self.hass, entry_id)
            try:
                runtime["security"].require_owner(requester)
                runtime["security"].require_unlocked(requester)
            except (VaultAccessDenied, VaultLockedError) as err:
                raise web.HTTPForbidden(text="Owner access and unlocked vault are required") from err
            try:
                result = await runtime["wallet_watch"].async_live_test_transaction(
                    txid=str(incoming.get("txid") or ""),
                    direction=str(incoming.get("direction") or "outgoing"),
                )
            except ValueError as err:
                raise web.HTTPBadRequest(text=str(err)) from err
            return respond(result)

        if route == "api/wallet-watch/notify-test" and method == "POST":
            incoming = _panel_json_body(body_text)
            entry_id = str(incoming.get("entry_id") or "")
            runtime = _runtime(self.hass, entry_id)
            try:
                runtime["security"].require_owner(requester)
                runtime["security"].require_unlocked(requester)
            except (VaultAccessDenied, VaultLockedError) as err:
                raise web.HTTPForbidden(text="Owner access and unlocked vault are required") from err
            return respond(await runtime["wallet_watch"].async_test_notifications())

        if route == "api/live-price" and method == "GET":
            entry_id = q("entry_id")
            runtime = _runtime(self.hass, entry_id)
            try:
                runtime["security"].require_owner(requester)
            except VaultAccessDenied as err:
                raise web.HTTPForbidden(text="Owner access is required") from err
            live = runtime["coordinator"].data or {}
            return respond({
                "prices": live.get("prices", {}),
                "price_details": live.get("price_details", {}),
                "live_source_by_currency": live.get("live_source_by_currency", {}),
                "live_data_available": bool(live.get("live_data_available")),
                "errors": live.get("errors", []),
                "updated_at": live.get("updated_at"),
                "local_interval_seconds": live.get("local_interval_seconds", getattr(runtime["coordinator"], "local_interval_seconds", 300)),
                "public_interval_seconds": live.get("public_interval_seconds", getattr(runtime["coordinator"], "public_interval_seconds", 60)),
                "dashboard_poll_seconds": 30,
            })

        if route == "api/market-assessment/history" and method == "GET":
            entry_id = q("entry_id")
            runtime = _runtime(self.hass, entry_id)
            try:
                runtime["security"].require_owner(requester)
            except VaultAccessDenied as err:
                raise web.HTTPForbidden(text="Owner access is required") from err
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry is None:
                raise web.HTTPBadRequest(text="Config entry was not found")
            current_settings = effective_settings(entry)
            currencies = configured_currencies(current_settings)
            market_settings = normalize_buy_opportunity_settings(
                current_settings.get(CONF_BUY_OPPORTUNITY_SETTINGS), currencies
            )
            currency = market_settings["currency"]
            history_data = runtime["history_storage"].data
            history_prices = history_data.get("prices", {}).get(currency, {})
            today = dt_util.utcnow().date()
            range_key = str(q("range") or "1y").lower()
            if range_key == "1d":
                start_day = today - timedelta(days=1)
            elif range_key == "7d":
                start_day = today - timedelta(days=7)
            elif range_key == "week_start":
                start_day = today - timedelta(days=today.weekday())
            elif range_key == "30d":
                start_day = today - timedelta(days=30)
            elif range_key == "month_start":
                start_day = today.replace(day=1)
            elif range_key == "90d":
                start_day = today - timedelta(days=90)
            elif range_key == "ytd":
                start_day = today.replace(month=1, day=1)
            elif range_key == "1y":
                start_day = today - timedelta(days=365)
            elif range_key == "3y":
                start_day = today - timedelta(days=365 * 3)
            elif range_key == "5y":
                start_day = today - timedelta(days=365 * 5)
            elif range_key == "10y":
                start_day = today - timedelta(days=365 * 10)
            else:
                start_day = None
                range_key = "max"
            signature = await self.hass.async_add_executor_job(partial(
                market_assessment_history_signature,
                history_prices,
                currency=currency,
                settings=market_settings,
            ))
            intraday_signature = await self.hass.async_add_executor_job(partial(
                market_assessment_intraday_signature,
                currency=currency,
                settings=market_settings,
            ))
            intraday_days = {
                "1d": 2,
                "7d": 8,
                "week_start": 8,
                "30d": 31,
                "month_start": 31,
                # The overview maps its visible 30-day range to the wider 90d
                # causal daily cache, so keep the recent intraday tail here too.
                "90d": 31,
            }.get(range_key, 0)

            async def _with_intraday(payload: dict[str, Any]) -> dict[str, Any]:
                if intraday_days <= 0:
                    return payload
                intraday_cache = runtime.get("market_assessment_intraday_cache")
                if intraday_cache is None:
                    return payload
                since = datetime.now(timezone.utc) - timedelta(days=intraday_days)
                points = await intraday_cache.async_points(intraday_signature, since=since)
                return {**payload, "intraday_points": points}

            cache: MarketAssessmentHistoryCache = runtime["market_assessment_history_cache"]
            cached = await cache.async_get(signature, range_key)
            if cached is not None:
                payload = {**cached, "range": range_key, "cache_status": "persistent_hit"}
                return respond(await _with_intraday(payload))

            await cache.async_prepare(signature)
            task_key = (signature, range_key)
            tasks = runtime.setdefault("_market_assessment_history_tasks", {})
            compute_lock = runtime.setdefault("_market_assessment_history_compute_lock", asyncio.Lock())
            running = tasks.get(task_key)
            if running is None or running.done():
                async def _calculate_history() -> dict[str, Any]:
                    async with compute_lock:
                        # A preceding queued request may already have produced
                        # this exact range while we were waiting for the CPU slot.
                        queued_hit = await cache.async_get(signature, range_key)
                        if queued_hit is not None:
                            return {**queued_hit, "range": range_key, "cache_status": "persistent_hit"}
                        # Calculate the expensive daily causal score series once
                        # per source/settings generation. Range changes then only
                        # filter/downsample and decorate marker points.
                        score_cache = await cache.async_get_scores(signature)
                        if score_cache is None:
                            score_cache = await self.hass.async_add_executor_job(partial(
                                calculate_buy_opportunity_history_scores,
                                history_prices,
                                None,
                                currency=currency,
                                settings=market_settings,
                                as_of_day=today,
                            ))
                            await cache.async_put_scores(signature, score_cache)
                        # Historical reconstruction uses only the durable daily cache.
                        # The frontend appends the already cached current-day score so
                        # every live quote does not force years of history to rebuild.
                        result = await self.hass.async_add_executor_job(partial(
                            calculate_buy_opportunity_history,
                            history_prices,
                            None,
                            currency=currency,
                            settings=market_settings,
                            as_of_day=today,
                            start_day=start_day,
                            max_points=420,
                            marker_interval_years=4 if range_key in {"10y", "max"} else 0,
                            precomputed_scores=score_cache.get("scores", {}),
                        ))
                        payload = {
                            **result,
                            "range": range_key,
                            "calculated_at": datetime.now(timezone.utc).isoformat(),
                            "cache_status": "rebuilt",
                        }
                        await cache.async_put(signature, range_key, payload)
                        return payload

                running = self.hass.async_create_task(
                    _calculate_history(),
                    f"Bitcoin Stack Tracker market history {range_key}",
                )
                tasks[task_key] = running
            try:
                result = await running
            finally:
                if tasks.get(task_key) is running and running.done():
                    tasks.pop(task_key, None)
            return respond(await _with_intraday(result))

        if route == "api/market-assessment" and method == "GET":
            entry_id = q("entry_id")
            runtime = _runtime(self.hass, entry_id)
            # Market assessment contains public market data only.  Keep the
            # normal portfolio access boundary, but it does not require the
            # password vault to be unlocked.
            try:
                runtime["security"].require_owner(requester)
            except VaultAccessDenied as err:
                raise web.HTTPForbidden(text="Owner access is required") from err
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry is None:
                raise web.HTTPBadRequest(text="Config entry was not found")
            live = runtime["coordinator"].data or {}
            snapshot = await async_market_assessment(
                self.hass, entry, runtime["coordinator"], runtime["history_storage"]
            )
            return respond({
                "buy_opportunity": snapshot["result"],
                "buy_opportunity_settings": snapshot["settings"],
                "live_price_updated_at": live.get("updated_at"),
                "history_last_sync": runtime["history_storage"].data.get("last_sync"),
                "calculated_at": snapshot["calculated_at"],
                "automatic": True,
                "cache_seconds": 300,
            })

        if route == "api/core-network" and method == "GET":
            entry_id = q("entry_id")
            runtime = _runtime(self.hass, entry_id)
            runtime["security"].require_owner(requester)
            if q("refresh_live") in {"1", "true", "yes"}:
                # An interactive connection refresh also performs one fresh live
                # ticker cycle. This makes the observed-provider timestamps
                # meaningful instead of merely re-rendering old telemetry.
                await runtime["coordinator"].async_refresh()
            entry = self.hass.config_entries.async_get_entry(entry_id)
            network_security = network_security_snapshot(self.hass)
            return respond({
                "network_security": network_security,
                "connection_inventory": _connection_inventory(
                    effective_settings(entry) if entry else {}, runtime["history_storage"].data, network_security,
                    (runtime["coordinator"].data or {}).get("price_details", {}),
                ),
                "integration_version": VERSION,
                "architecture": "native-core-panel",
                "refreshed_at": datetime.now(timezone.utc).isoformat(),
                "live_price_updated_at": (runtime["coordinator"].data or {}).get("updated_at"),
            })

        if route == "api/network-status" and method == "GET":
            entry_id = q("entry_id")
            runtime = _runtime(self.hass, entry_id)
            try:
                runtime["security"].require_owner(requester)
            except VaultAccessDenied as err:
                raise web.HTTPForbidden(text="Owner access is required") from err
            if entry_id and self.hass.config_entries.async_get_entry(entry_id) is not None:
                await _async_rotate_tor_if_due(
                    self.hass, entry_id=entry_id, trigger="network-poll"
                )
            return respond(await _panel_tor_status(self.hass, force=q("force") in {"1", "true", "yes"}))

        if route == "api/chart/halvings" and method == "GET":
            entry_id = q("entry_id")
            runtime = _runtime(self.hass, entry_id)
            runtime["security"].require_unlocked(requester)
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry is None:
                raise web.HTTPBadRequest(text="Config entry was not found")
            try:
                result = await _async_halving_markers(
                    self.hass, effective_settings(entry),
                    force=q("force") in {"1", "true", "yes"},
                )
            except ValueError as err:
                raise web.HTTPBadGateway(text=str(err)) from err
            return respond(result)

        if route == "api/history/reference-price" and method == "GET":
            entry_id = q("entry_id")
            runtime = _runtime(self.hass, entry_id)
            runtime["security"].require_unlocked(requester)
            currency = str(q("currency") or "").upper()
            timestamp = q("timestamp")
            live_prices = (runtime["coordinator"].data or {}).get("prices", {})
            return respond(_json_safe(historical_reference_price(
                runtime["history_storage"].data,
                currency,
                timestamp,
                live_price=live_prices.get(currency),
            )))

        if route == "api/history/intraday" and method == "POST":
            entry_id = str(_panel_json_body(body_text).get("entry_id") or "")
            runtime = _runtime(self.hass, entry_id)
            runtime["security"].require_unlocked(requester)
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry is None:
                raise web.HTTPBadRequest(text="Config entry was not found")
            payload = _panel_json_body(body_text)
            history_days = int(payload.get("history_days") or 366)
            interval_minutes = int(payload.get("interval_minutes") or market_ohlc_interval_for_days(history_days))
            return respond(await async_sync_intraday_history(
                self.hass, entry, runtime["history_storage"], history_days, interval_minutes
            ))

        if route == "api/tor/rotation-settings":
            entry_id = q("entry_id") if method == "GET" else str(_panel_json_body(body_text).get("entry_id") or "")
            runtime = _runtime(self.hass, entry_id)
            runtime["security"].require_owner(requester)
            state = await _panel_state(self.hass)
            settings = dict(state.setdefault("tor_rotation", {}).get(entry_id) or {})
            if method == "POST":
                incoming = _panel_json_body(body_text)
                interval = int(incoming.get("interval_minutes") or 30)
                if interval not in _TOR_ROTATION_INTERVALS:
                    raise web.HTTPBadRequest(text="Unsupported rotation interval")
                settings.update({"enabled": bool(incoming.get("enabled")), "interval_minutes": interval})
                state.setdefault("tor_rotation", {})[entry_id] = settings
                await _save_panel_state(self.hass, state)
                if settings["enabled"]:
                    await _async_rotate_tor_if_due(
                        self.hass, entry_id=entry_id, trigger="settings-save"
                    )
            else:
                # Self-healing watchdog: the owner panel polls this endpoint once
                # per minute.  If Home Assistant ever delayed the scheduled timer,
                # the persisted deadline is enforced here as well.
                await _async_rotate_tor_if_due(
                    self.hass, entry_id=entry_id, trigger="settings-poll"
                )
            state = await _panel_state(self.hass)
            settings = dict(state.setdefault("tor_rotation", {}).get(entry_id) or {})
            return respond(_tor_rotation_settings_view(settings))

        if route == "api/tor/new-identity" and method == "POST":
            entry_id = str(_panel_json_body(body_text).get("entry_id") or "")
            runtime = _runtime(self.hass, entry_id)
            runtime["security"].require_owner(requester)
            previous_network = await _panel_tor_status(self.hass)
            previous_exit_ip = previous_network.get("tor_exit_ip")
            result = rotate_tor_isolation(self.hass)
            state = await _panel_state(self.hass)
            settings = dict(state.setdefault("tor_rotation", {}).get(entry_id) or {})
            settings["last_rotated_at"] = result["last_rotated_at"]
            settings["last_trigger"] = "manual"
            if previous_exit_ip:
                settings["last_previous_ip"] = previous_exit_ip
            state["tor_rotation"][entry_id] = settings
            await _save_panel_state(self.hass, state)
            network = await _panel_tor_status(self.hass, force=True)
            current_exit_ip = network.get("tor_exit_ip")
            settings = _tor_rotation_settings_view(settings)
            return respond({
                **result,
                "rotation": settings,
                "network": network,
                "previous_exit_ip": previous_exit_ip,
                "tor_exit_ip": current_exit_ip,
                "ip_changed": bool(previous_exit_ip and current_exit_ip and previous_exit_ip != current_exit_ip),
            })

        if route == "api/backup-health" and method == "GET":
            entry_id = q("entry_id")
            _runtime(self.hass, entry_id)["security"].require_owner(requester)
            state = await _panel_state(self.hass)
            return respond(_panel_backup_health(entry_id, state.get("entries", {}).get(entry_id)))

        if route == "api/backup-health/settings" and method == "POST":
            incoming = _panel_json_body(body_text)
            entry_id = str(incoming.get("entry_id") or "")
            _runtime(self.hass, entry_id)["security"].require_owner(requester)
            backup_days = int(incoming.get("backup_warning_days") or 30)
            restore_days = int(incoming.get("restore_test_warning_days") or 180)
            if backup_days not in _PANEL_BACKUP_WARNING_DAYS or restore_days not in _PANEL_RESTORE_WARNING_DAYS:
                raise web.HTTPBadRequest(text="Unsupported backup reminder interval")
            return respond(await _panel_mark_health(self.hass, entry_id, backup_warning_days=backup_days, restore_test_warning_days=restore_days))

        if route == "api/backup-health/mark-restore-test" and method == "POST":
            incoming = _panel_json_body(body_text)
            entry_id = str(incoming.get("entry_id") or "")
            _runtime(self.hass, entry_id)["security"].require_owner(requester)
            return respond(await _panel_mark_health(self.hass, entry_id, last_restore_test_at=datetime.now(timezone.utc).isoformat()))

        if route == "api/logs" and method == "GET":
            entry_id = q("entry_id")
            _runtime(self.hass, entry_id)["security"].require_owner(requester)
            try:
                limit = max(1, min(_TECHNICAL_LOG_MAX_ENTRIES, int(q("limit", "500") or 500)))
            except ValueError:
                limit = _TECHNICAL_LOG_MAX_ENTRIES
            entries = list(_technical_log_buffer(self.hass))[-limit:]
            return respond({"entries": entries, "max_entries": _TECHNICAL_LOG_MAX_ENTRIES, "level": "Home Assistant Core", "note": "Technical metadata only; no passwords, request bodies, backups, CSV payloads or ledger contents."})

        if route == "api/logs/clear" and method == "POST":
            entry_id = str(_panel_json_body(body_text).get("entry_id") or "")
            _runtime(self.hass, entry_id)["security"].require_owner(requester)
            _technical_log_clear(self.hass)
            return respond({"cleared": True, "max_entries": _TECHNICAL_LOG_MAX_ENTRIES})

        if route == "api/logs/download" and method == "GET":
            entry_id = q("entry_id")
            _runtime(self.hass, entry_id)["security"].require_owner(requester)
            rows = list(_technical_log_buffer(self.hass))
            data = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows).encode("utf-8")
            return respond({"__file__": {"filename": "bitcoin-stack-tracker-app-log.jsonl", "mime": "application/x-ndjson", "data_base64": base64.b64encode(data).decode("ascii")}})

        raise web.HTTPNotFound(text=f"Unknown native panel route: {route}")


def _register_global_timers(hass: HomeAssistant) -> None:
    """(Re)register global timers with Home Assistant bound explicitly.

    Config-entry reloads can leave callbacks created by an older custom-component
    module alive in the running Core. Always cancel any previously stored timer
    before registering the current callback shape so a datetime argument can never
    be mistaken for ``hass`` after an update.
    """
    domain_data = hass.data.setdefault(DOMAIN, {})
    for key in ("_cancel_tor_rotation_timer", "_cancel_vault_expiry_timer"):
        cancel = domain_data.pop(key, None)
        if callable(cancel):
            try:
                cancel()
            except Exception:
                pass

    async def _tor_timer(now: Any) -> None:
        await _async_rotate_tor_if_due(hass, now, trigger="global-timer")

    async def _vault_timer(now: Any) -> None:
        await _async_expire_vault_sessions(hass)

    domain_data["_cancel_tor_rotation_timer"] = async_track_time_interval(
        hass, _tor_timer, timedelta(minutes=1)
    )
    domain_data["_cancel_vault_expiry_timer"] = async_track_time_interval(
        hass, _vault_timer, timedelta(seconds=30)
    )
    domain_data["_tor_rotation_timer_registered"] = True
    domain_data["_vault_expiry_timer_registered"] = True


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register integration service actions."""
    hass.data.setdefault(DOMAIN, {})
    if not hass.data[DOMAIN].get("_http_views_registered"):
        # Expose only the authenticated native-panel HTTP surface.
        # for the UI. Legacy Ingress/action/export/backup/restore views are gone;
        # all panel traffic is allowlisted inside this Core RPC endpoint.
        hass.http.register_view(BitcoinStackNativePanelRpcView(hass))
        hass.data[DOMAIN]["_http_views_registered"] = True

    from .panel import async_register_native_panel
    await async_register_native_panel(hass)

    domain_data = hass.data.setdefault(DOMAIN, {})
    _register_global_timers(hass)

    async def add_purchase(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])
        amount_btc = amount_to_btc(call.data[CONF_AMOUNT], call.data[CONF_AMOUNT_UNIT])
        _validate_positive_transaction(amount_btc, call.data[CONF_PRICE])
        item = await runtime["storage"].async_add_purchase(
            timestamp=parse_timestamp(call.data.get(CONF_TIMESTAMP)),
            amount_btc=amount_btc,
            currency=call.data[CONF_CURRENCY],
            price=call.data[CONF_PRICE],
            fee=call.data.get(CONF_FEE, 0),
            fee_btc=call.data.get(CONF_FEE_BTC, 0),
            fee_btc_affects_stack=call.data.get(CONF_FEE_BTC_AFFECTS_STACK, True),
            note=call.data.get(CONF_NOTE, ""),
            depot_id=call.data.get(CONF_DEPOT_ID, DEFAULT_DEPOT_ID),
        )
        _notify_entities(runtime)
        return _json_safe(item)

    async def add_income(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])
        amount_btc = amount_to_btc(call.data[CONF_AMOUNT], call.data[CONF_AMOUNT_UNIT])
        _validate_positive_transaction(amount_btc, call.data[CONF_PRICE])
        try:
            item = await runtime["storage"].async_add_income(
                timestamp=parse_timestamp(call.data.get(CONF_TIMESTAMP)),
                amount_btc=amount_btc,
                currency=call.data[CONF_CURRENCY],
                price=call.data[CONF_PRICE],
                fee=call.data.get(CONF_FEE, 0),
                fee_btc=call.data.get(CONF_FEE_BTC, 0),
                fee_btc_affects_stack=call.data.get(CONF_FEE_BTC_AFFECTS_STACK, True),
                note=call.data.get(CONF_NOTE, ""),
                depot_id=call.data.get(CONF_DEPOT_ID, DEFAULT_DEPOT_ID),
            )
        except ValueError as err:
            raise vol.Invalid(str(err)) from err
        _notify_entities(runtime)
        return _json_safe(item)

    async def add_sale(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])
        storage: BitcoinLedgerStore = runtime["storage"]
        amount_btc = amount_to_btc(call.data[CONF_AMOUNT], call.data[CONF_AMOUNT_UNIT])
        _validate_positive_transaction(amount_btc, call.data[CONF_PRICE])
        try:
            # Storage performs the atomic FIFO validation and reuses that exact
            # cache for persistence. Avoid an expensive duplicate pre-flight.
            item = await storage.async_add_sale(
                timestamp=parse_timestamp(call.data.get(CONF_TIMESTAMP)),
                amount_btc=amount_btc,
                currency=call.data[CONF_CURRENCY],
                price=call.data[CONF_PRICE],
                fee=call.data.get(CONF_FEE, 0),
                fee_btc=call.data.get(CONF_FEE_BTC, 0),
                fee_btc_affects_stack=call.data.get(CONF_FEE_BTC_AFFECTS_STACK, True),
                note=call.data.get(CONF_NOTE, ""),
                depot_id=call.data.get(CONF_DEPOT_ID, DEFAULT_DEPOT_ID),
            )
        except ValueError as err:
            raise vol.Invalid(str(err)) from err
        _notify_entities(runtime)
        return _json_safe(item)

    async def add_expense(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])
        amount_btc = amount_to_btc(call.data[CONF_AMOUNT], call.data[CONF_AMOUNT_UNIT])
        _validate_positive_transaction(amount_btc, call.data[CONF_PRICE])
        try:
            item = await runtime["storage"].async_add_expense(
                timestamp=parse_timestamp(call.data.get(CONF_TIMESTAMP)),
                amount_btc=amount_btc,
                currency=call.data[CONF_CURRENCY],
                price=call.data[CONF_PRICE],
                fee=call.data.get(CONF_FEE, 0),
                fee_btc=call.data.get(CONF_FEE_BTC, 0),
                fee_btc_affects_stack=call.data.get(CONF_FEE_BTC_AFFECTS_STACK, True),
                note=call.data.get(CONF_NOTE, ""),
                depot_id=call.data.get(CONF_DEPOT_ID, DEFAULT_DEPOT_ID),
            )
        except ValueError as err:
            raise vol.Invalid(str(err)) from err
        _notify_entities(runtime)
        return _json_safe(item)

    async def add_network_fee(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])
        amount_btc = amount_to_btc(call.data[CONF_AMOUNT], call.data[CONF_AMOUNT_UNIT])
        if amount_btc <= 0:
            raise vol.Invalid("Amount must be greater than zero")
        try:
            item = await runtime["storage"].async_add_network_fee(
                timestamp=parse_timestamp(call.data.get(CONF_TIMESTAMP)),
                amount_btc=amount_btc,
                currency=call.data[CONF_CURRENCY],
                price=call.data[CONF_PRICE],
                network=call.data.get(CONF_NETWORK, "onchain"),
                note=call.data.get(CONF_NOTE, ""),
                depot_id=call.data.get(CONF_DEPOT_ID, DEFAULT_DEPOT_ID),
            )
        except ValueError as err:
            raise vol.Invalid(str(err)) from err
        _notify_entities(runtime)
        return _json_safe(item)

    async def add_stack(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])
        amount_btc = amount_to_btc(call.data[CONF_AMOUNT], call.data[CONF_AMOUNT_UNIT])
        if amount_btc <= 0:
            raise vol.Invalid("Amount must be greater than zero")
        item = await runtime["storage"].async_add_stack(
            timestamp=parse_timestamp(call.data.get(CONF_TIMESTAMP)),
            amount_btc=amount_btc,
            note=call.data.get(CONF_NOTE, ""),
            depot_id=call.data.get(CONF_DEPOT_ID, DEFAULT_DEPOT_ID),
        )
        _notify_entities(runtime)
        return _json_safe(item)

    async def bulk_import(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])
        try:
            result = await runtime["storage"].async_bulk_import(
                list(call.data[CONF_TRANSACTIONS])
            )
        except ValueError as err:
            # Home Assistant otherwise reduces this to the unhelpful text
            # ``Bitcoin Stack Tracker action failed: ValueError``.
            raise vol.Invalid(str(err)) from err
        _notify_entities(runtime)
        if isinstance(result.get("entries"), list):
            result["entries"] = _dashboard_ledger_entries(result["entries"])
        return _json_safe(result)

    async def add_depot(call: ServiceCall) -> dict[str, Any]:
        depot = await _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])["storage"].async_add_depot(
            call.data[CONF_DEPOT_NAME]
        )
        await _refresh_structure_after_write(
            hass, call.data[CONF_CONFIG_ENTRY_ID], _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])
        )
        return depot

    async def delete_depot(call: ServiceCall) -> dict[str, Any]:
        deleted = await _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])["storage"].async_delete_depot(
            call.data[CONF_DEPOT_ID]
        )
        if not deleted:
            raise vol.Invalid("Depot cannot be deleted")
        await _refresh_structure_after_write(
            hass, call.data[CONF_CONFIG_ENTRY_ID], _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])
        )
        return {"deleted": True, "depot_id": call.data[CONF_DEPOT_ID]}

    async def add_goal(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])
        goal_btc = amount_to_btc(call.data[CONF_GOAL], call.data[CONF_GOAL_UNIT])
        goal = await runtime["storage"].async_add_goal(
            name=call.data[CONF_GOAL_NAME],
            amount_btc=goal_btc,
            depot_id=call.data.get(CONF_DEPOT_ID, ALL_DEPOTS),
            currency=call.data[CONF_CURRENCY],
        )
        await _refresh_structure_after_write(
            hass, call.data[CONF_CONFIG_ENTRY_ID], runtime
        )
        return goal

    async def update_goal(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])
        amount = None
        if CONF_GOAL in call.data:
            amount = amount_to_btc(call.data[CONF_GOAL], call.data[CONF_GOAL_UNIT])
        updated = await runtime["storage"].async_update_goal(
            call.data[CONF_GOAL_ID],
            amount_btc=amount,
            name=call.data.get(CONF_GOAL_NAME),
            depot_id=call.data.get(CONF_DEPOT_ID),
            currency=call.data.get(CONF_CURRENCY),
        )
        if not updated:
            raise vol.Invalid("Goal was not found")
        await _refresh_structure_after_write(
            hass, call.data[CONF_CONFIG_ENTRY_ID], runtime
        )
        return {"updated": True, "goal_id": call.data[CONF_GOAL_ID]}

    async def delete_goal(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])
        deleted = await runtime["storage"].async_delete_goal(call.data[CONF_GOAL_ID])
        if not deleted:
            raise vol.Invalid("Goal was not found")
        await _refresh_structure_after_write(
            hass, call.data[CONF_CONFIG_ENTRY_ID], runtime
        )
        return {"deleted": True, "goal_id": call.data[CONF_GOAL_ID]}

    async def delete_all_entries(call: ServiceCall) -> dict[str, Any]:
        entry_id = call.data[CONF_CONFIG_ENTRY_ID]
        await _authorize_call(hass, call, entry_id, owner_only=True)
        runtime = _runtime(hass, entry_id)
        deleted = await runtime["storage"].async_delete_all_entries()
        _notify_entities(runtime)
        return {"deleted": deleted}

    async def update_entry(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])
        storage: BitcoinLedgerStore = runtime["storage"]
        item_id = call.data[CONF_LEDGER_ENTRY_ID]
        entries = storage.entries
        existing = next((item for item in entries if item.get("id") == item_id), None)
        if existing is None:
            raise vol.Invalid("Ledger entry was not found")

        kind = str(call.data.get("type", existing.get("type")) or "").lower()
        if kind not in {"purchase", "income", "sale", "stack", "expense", "network_fee"}:
            raise vol.Invalid("Unsupported ledger entry type")
        amount_btc = amount_to_btc(call.data[CONF_AMOUNT], call.data[CONF_AMOUNT_UNIT])
        if amount_btc <= 0:
            raise vol.Invalid("Amount must be greater than zero")
        depot_id = call.data.get(CONF_DEPOT_ID, existing.get("depot_id", DEFAULT_DEPOT_ID))
        if not storage.has_depot(depot_id):
            raise vol.Invalid("Unknown depot")
        timestamp = parse_timestamp(call.data.get(CONF_TIMESTAMP) or existing.get("timestamp"))
        note = str(call.data.get(CONF_NOTE, existing.get("note", ""))).strip()
        replacement: dict[str, Any] = {
            "id": item_id,
            "type": kind,
            "timestamp": timestamp.isoformat(),
            "depot_id": depot_id,
            "amount_btc": btc_string(amount_btc),
            "note": note,
        }
        if kind == "network_fee":
            currency = str(call.data.get(CONF_CURRENCY, existing.get("currency", "")) or "").strip().upper()
            price = decimal_value(call.data.get(CONF_PRICE, existing.get("price", 0)))
            network = str(call.data.get(CONF_NETWORK, existing.get("network", "onchain")) or "onchain").lower()
            if not currency:
                raise vol.Invalid("Currency is required")
            if price <= 0:
                raise vol.Invalid("Reference price must be greater than zero")
            if network not in {"onchain", "lightning"}:
                raise vol.Invalid("Network must be onchain or lightning")
            replacement.update({
                "currency": currency,
                "price": money_string(price),
                "network": network,
                "fee_btc": "0",
                "fee_btc_affects_stack": False,
            })
        elif kind in {"purchase", "income", "sale", "expense"}:
            # When the booking type is changed, stale fields from the old kind
            # must never leak into the new transaction.  The form therefore
            # sends the complete priced transaction payload.
            currency = str(call.data.get(CONF_CURRENCY, existing.get("currency", "")) or "").strip().upper()
            price = decimal_value(call.data.get(CONF_PRICE, existing.get("price", 0)))
            fee = decimal_value(call.data.get(CONF_FEE, existing.get("fee", 0)))
            fee_btc = decimal_value(call.data.get(CONF_FEE_BTC, existing.get("fee_btc", 0)))
            fee_btc_affects_stack = bool(call.data.get(
                CONF_FEE_BTC_AFFECTS_STACK, existing.get("fee_btc_affects_stack", False)
            ))
            if not currency:
                raise vol.Invalid("Currency is required")
            if price <= 0:
                raise vol.Invalid("Price must be greater than zero")
            if fee < 0 or fee_btc < 0:
                raise vol.Invalid("Fees must not be negative")
            replacement.update({
                "currency": currency,
                "price": money_string(price),
                "fee": money_string(fee),
                "fee_btc": btc_string(fee_btc) if fee_btc > 0 else "0",
                "fee_btc_affects_stack": bool(fee_btc > 0 and fee_btc_affects_stack),
            })
        else:
            # Stack entries are unknown-basis BTC and cannot carry a transaction
            # price or a BTC network fee in the manual editor.
            replacement["fee_btc"] = "0"
            replacement["fee_btc_affects_stack"] = False

        try:
            # Storage validates the candidate atomically against the previous
            # oversold state. This also allows an old oversold ledger to be
            # repaired instead of rejecting every edit merely because it was
            # already inconsistent before the edit.
            await storage.async_update_entry(item_id, replacement)
        except ValueError as err:
            raise vol.Invalid(str(err)) from err
        _notify_entities(runtime)
        return {"updated": True, "ledger_entry_id": item_id, "entry": _json_safe(replacement)}

    async def delete_entry(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])
        storage: BitcoinLedgerStore = runtime["storage"]
        item_id = call.data[CONF_LEDGER_ENTRY_ID]
        entries = storage.entries
        if not any(item.get("id") == item_id for item in entries):
            raise vol.Invalid("Ledger entry was not found")
        try:
            await storage.async_delete(item_id)
        except ValueError as err:
            raise vol.Invalid(str(err)) from err
        _notify_entities(runtime)
        return {"deleted": True, "ledger_entry_id": item_id}

    async def set_goal(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])
        storage: BitcoinLedgerStore = runtime["storage"]
        goal_btc = amount_to_btc(call.data[CONF_GOAL], call.data[CONF_GOAL_UNIT])
        goals = storage.goals
        if goals:
            await storage.async_update_goal(goals[0]["id"], amount_btc=goal_btc)
            goal_id = goals[0]["id"]
        else:
            current_entry = hass.config_entries.async_get_entry(call.data[CONF_CONFIG_ENTRY_ID])
            currencies = configured_currencies(effective_settings(current_entry)) if current_entry else []
            goal = await storage.async_add_goal(
                name=f"{btc_string(goal_btc)} BTC",
                amount_btc=goal_btc,
                currency=currencies[0] if currencies else "EUR",
            )
            goal_id = goal["id"]
        await hass.config_entries.async_reload(call.data[CONF_CONFIG_ENTRY_ID])
        return {"updated": True, "goal_id": goal_id}

    async def set_tax_settings(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])
        result = await runtime["storage"].async_set_tax_settings(
            long_term_days=call.data[CONF_LONG_TERM_DAYS],
            note=call.data.get(CONF_TAX_NOTE, DEFAULT_TAX_NOTE),
        )
        _notify_entities(runtime)
        return result

    async def export_ledger(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])
        entry = hass.config_entries.async_get_entry(call.data[CONF_CONFIG_ENTRY_ID])
        storage: BitcoinLedgerStore = runtime["storage"]
        days = int(storage.tax_settings.get("long_term_days", 365))
        ledger_payload = await storage.async_export()
        fifo = await hass.async_add_executor_job(
            partial(fifo_result, ledger_payload.get("entries", []), long_term_days=days)
        )
        return _json_safe({
            "name": entry.title if entry else "Bitcoin Stack",
            "settings": effective_settings(entry) if entry else {},
            "ledger": ledger_payload,
            "fifo": fifo,
        })

    async def export_csv(call: ServiceCall) -> dict[str, Any]:
        """Reject durable plaintext exports; the panel download uses a temp directory."""
        del call
        raise vol.Invalid(
            "Persistent plaintext CSV export is disabled for privacy. "
            "Use the dashboard download, which creates the ZIP only temporarily."
        )

    async def sync_history(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime(hass, call.data[CONF_CONFIG_ENTRY_ID])
        entry = hass.config_entries.async_get_entry(call.data[CONF_CONFIG_ENTRY_ID])
        if entry is None:
            raise vol.Invalid("Config entry was not found")
        result = await async_sync_history(
            hass, entry, runtime["storage"], runtime["history_storage"]
        )
        try:
            result["market_assessment_history_cache"] = await _async_warm_market_assessment_history_scores(
                hass, entry, runtime
            )
        except Exception:
            result["market_assessment_history_cache"] = "warm-failed"
            _LOGGER.exception("Manual market-assessment history cache warm-up failed")
        _notify_entities(runtime)
        return result

    async def set_history_settings(call: ServiceCall) -> dict[str, Any]:
        """Enable or disable history without deleting the durable local cache."""
        entry_id = call.data[CONF_CONFIG_ENTRY_ID]
        await _authorize_call(
            hass, call, entry_id, owner_only=True, require_unlocked=False
        )
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            raise vol.Invalid("Config entry was not found")
        enabled = bool(call.data[CONF_ENABLED])
        auto_sync = bool(call.data[CONF_AUTO_SYNC]) if enabled else False
        proxy_url = DEFAULT_HISTORY_TOR_PROXY
        options = dict(entry.options)
        options[CONF_HISTORY_ENABLED] = enabled
        options[CONF_HISTORY_AUTO_SYNC] = auto_sync
        options[CONF_HISTORY_TOR_PROXY] = proxy_url
        # History is always retained in full. Range selection belongs to the UI.
        options[CONF_HISTORY_DAYS] = 0
        hass.config_entries.async_update_entry(entry, options=options)
        runtime = _runtime(hass, entry_id)
        timer_active = _configure_history_timer(
            hass,
            entry,
            runtime,
            enabled=enabled,
            auto_sync=auto_sync,
            sync_if_stale=auto_sync,
        )
        _notify_entities(runtime)
        return {
            "history_enabled": enabled,
            "history_auto_sync": auto_sync,
            "history_tor_proxy": proxy_url,
            "public_history_route": "Tor only",
            "cache_retained": True,
            "reload_scheduled": False,
            "vault_session_retained": True,
            "history_timer_active": timer_active,
        }

    async def set_buy_opportunity_settings(call: ServiceCall) -> dict[str, Any]:
        """Update the public, price-history-only market-assessment model."""
        entry_id = call.data[CONF_CONFIG_ENTRY_ID]
        await _authorize_call(
            hass, call, entry_id, owner_only=True, require_unlocked=False
        )
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            raise vol.Invalid("Config entry was not found")
        currencies = configured_currencies(effective_settings(entry))
        current = normalize_buy_opportunity_settings(
            effective_settings(entry).get(CONF_BUY_OPPORTUNITY_SETTINGS), currencies
        )
        if bool(call.data.get("reset_defaults")):
            normalized = normalize_buy_opportunity_settings(
                {"currency": str(call.data.get(CONF_CURRENCY, current["currency"])).upper()},
                currencies,
            )
        else:
            requested_profile = str(call.data.get("profile", current["profile"]))
            merged = {
                "profile": requested_profile,
                "currency": str(call.data.get(CONF_CURRENCY, current["currency"])).upper(),
                "weights": dict(
                    PROFILE_WEIGHTS.get(requested_profile, current["weights"])
                    if "profile" in call.data and "weights" not in call.data
                    else current["weights"]
                ),
                "signal_weights": {
                    component: dict(values)
                    for component, values in current["signal_weights"].items()
                },
                "turning_point_weights": {
                    model_name: dict(values)
                    for model_name, values in current["turning_point_weights"].items()
                },
                "thresholds": dict(current["thresholds"]),
                "model": dict(current["model"]),
            }
            if isinstance(call.data.get("weights"), dict):
                merged["weights"].update(call.data["weights"])
            if isinstance(call.data.get("thresholds"), dict):
                merged["thresholds"].update(call.data["thresholds"])
            if isinstance(call.data.get("model"), dict):
                merged["model"].update(call.data["model"])
            if isinstance(call.data.get("signal_weights"), dict):
                for component, values in call.data["signal_weights"].items():
                    if component in merged["signal_weights"] and isinstance(values, dict):
                        merged["signal_weights"][component].update(values)
            if isinstance(call.data.get("turning_point_weights"), dict):
                for model_name, values in call.data["turning_point_weights"].items():
                    if model_name in merged["turning_point_weights"] and isinstance(values, dict):
                        merged["turning_point_weights"][model_name].update(values)
            threshold_values = [
                float(merged["thresholds"][key])
                for key in ("very_expensive_max", "expensive_max", "interesting", "cheap", "very_cheap", "extreme")
            ]
            if not all(left < right for left, right in zip(threshold_values, threshold_values[1:])):
                raise vol.Invalid(
                    "Score thresholds must be strictly ascending: very_expensive_max < expensive_max < interesting < cheap < very_cheap < extreme"
                )
            if float(merged["model"]["volatility_regime_low_ratio"]) >= float(merged["model"]["volatility_regime_high_ratio"]):
                raise vol.Invalid("Volatility regime low ratio must be below high ratio")
            if int(merged["model"]["volatility_fast_window_days"]) >= int(merged["model"]["volatility_slow_window_days"]):
                raise vol.Invalid("Fast volatility window must be shorter than slow volatility window")
            if int(merged["model"]["turning_point_separation_days"]) >= int(merged["model"]["turning_point_lookback_days"]):
                raise vol.Invalid("Turning-point swing separation must be shorter than the turning-point lookback")
            if float(merged["model"]["turning_zone_threshold"]) >= float(merged["model"]["turning_extreme_threshold"]):
                raise vol.Invalid("Turning-point zone threshold must be below extreme threshold")
            normalized = normalize_buy_opportunity_settings(merged, currencies)

        options = dict(entry.options)
        options[CONF_BUY_OPPORTUNITY_SETTINGS] = normalized
        hass.config_entries.async_update_entry(entry, options=options)
        runtime = _runtime(hass, entry_id)
        invalidate_market_assessment_cache(hass, entry_id)
        for task in list(runtime.get("_market_assessment_history_tasks", {}).values()):
            if task is not None and not task.done():
                task.cancel()
        runtime["_market_assessment_history_tasks"] = {}
        await runtime["market_assessment_history_cache"].async_clear()
        await runtime["market_assessment_intraday_cache"].async_clear()
        _notify_entities(runtime)
        return {
            "settings": normalized,
            "reload_scheduled": False,
            "vault_session_retained": True,
            "notice": "Additional model-based market assessment only; not a buy signal or investment recommendation.",
        }

    async def list_portfolios(call: ServiceCall) -> dict[str, Any]:
        requester = await _authenticated_service_user_id(hass, call)
        portfolios = []
        for entry in hass.config_entries.async_entries(DOMAIN):
            runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if not isinstance(runtime, dict):
                continue
            security: BitcoinSecurityStore = runtime["security"]
            if not security.is_allowed(requester):
                continue
            portfolios.append({
                "config_entry_id": entry.entry_id,
                "title": entry.title,
                "state": str(entry.state),
                "owner": security.is_owner(requester),
                "password_protected": security.encryption_mode == ENCRYPTION_PASSWORD,
                "locked": not security.is_user_unlocked(requester),
            })
        return {
            "portfolios": portfolios,
            "version": VERSION,
            "asset": "BTC",
            "brand": BRAND_NAME,
        }

    async def dashboard_data(call: ServiceCall) -> dict[str, Any]:
        entry_id = call.data[CONF_CONFIG_ENTRY_ID]
        section = str(call.data.get(CONF_DASHBOARD_SECTION, "all") or "all")
        requester = await _authorize_call(
            hass, call, entry_id, require_unlocked=False
        )
        runtime = _runtime(hass, entry_id)
        entry = hass.config_entries.async_get_entry(entry_id)
        storage: BitcoinLedgerStore = runtime["storage"]
        security: BitcoinSecurityStore = runtime["security"]
        if not security.is_user_unlocked(requester) or storage.is_locked:
            status = security.public_status(requester)
            status["setup_required"] = storage.setup_required
            return {
                "locked": True,
                "section": section,
                "portfolio": {
                    "config_entry_id": entry_id,
                    "title": entry.title if entry else "Bitcoin Stack",
                    "version": VERSION,
                    "asset": "BTC",
                },
                "brand": {
                    "name": BRAND_NAME,
                    "watermark": BRAND_WATERMARK,
                    "lightning_address": V4V_LIGHTNING_ADDRESS,
                },
                "security": status,
                "vault_crypto": storage.password_crypto_status(),
            }

        history: BitcoinHistoryStore = runtime["history_storage"]
        prices = (runtime["coordinator"].data or {}).get("prices", {})
        price_details = (runtime["coordinator"].data or {}).get("price_details", {})
        price_errors = (runtime["coordinator"].data or {}).get("errors", [])
        history_days = int(call.data.get(CONF_HISTORY_DAYS, 365))
        history_interval = int(call.data.get(CONF_HISTORY_INTERVAL, 1440))
        history_data = history.data
        current_settings = effective_settings(entry) if entry else {}
        currencies = configured_currencies(current_settings) if entry else []

        # Heavy/sensitive data is deliberately separated. The native browser
        # requests only the section needed by the visible tab, keeping unlock
        # and tab switching fast while reducing how much private ledger data is
        # present in browser memory at any one time.
        if section == "ledger":
            entries = storage.entries
            fifo = storage.fifo_summary()
            return _json_safe({
                "locked": False,
                "section": "ledger",
                "entries": _dashboard_ledger_entries(entries),
                "fifo": _dashboard_ledger_fifo(fifo),
                "depot_entry_counts": _dashboard_depot_entry_counts(entries),
            })

        if section == "fifo":
            fifo = storage.fifo_summary()
            return _json_safe({
                "locked": False,
                "section": "fifo",
                # Resolve transaction links server-side. The tax view receives
                # only display fields: no notes, provider/import IDs or ledger
                # entry UUIDs, and it therefore does not require the full ledger.
                "fifo": {"matches": _dashboard_fifo_matches(fifo, storage.entries)},
            })

        cutoff = None
        if history_days > 0:
            cutoff = (
                dt_util.utcnow().date() - timedelta(days=history_days)
            ).isoformat()

        def _filter_days(values: dict[str, Any]) -> dict[str, Any]:
            if cutoff is None:
                return dict(values)
            return {day: value for day, value in values.items() if day >= cutoff}

        async def _chart_payload() -> dict[str, Any]:
            limited_prices = {
                currency: _filter_days(values)
                for currency, values in history_data.get("prices", {}).items()
            }
            limited_price_samples = history.price_samples_for_days(history_days)
            limited_market_candles = history.market_candles_for_days(
                history_days, history_interval
            )
            chart_cache = await async_ensure_chart_cache(hass, storage, history)
            limited_chart: dict[str, Any] = {}
            for metric, value in chart_cache.items():
                if not isinstance(value, dict):
                    continue
                if metric in {
                    "portfolio_value",
                    "open_cost_basis",
                    "unrealized_profit_loss",
                    "realized_profit_loss",
                    "total_profit_loss",
                }:
                    limited_chart[metric] = {
                        currency: _filter_days(series)
                        for currency, series in value.items()
                        if isinstance(series, dict)
                    }
                else:
                    limited_chart[metric] = _filter_days(value)
            entries = storage.entries
            return {
                "locked": False,
                "section": "chart",
                # Sanitized chart events intentionally omit notes, entry UUIDs,
                # provider order IDs and import fingerprints.
                "chart_ledger_events": _dashboard_chart_ledger_events(entries),
                "history": {
                    "prices": limited_prices,
                    "price_samples": limited_price_samples,
                    "market_candles": limited_market_candles,
                    "market_interval_minutes": history_interval,
                    "chart": limited_chart,
                    "days_requested": history_days,
                    "all_cached": history_days == 0,
                    "series_loaded": True,
                },
            }

        if section == "chart":
            return _json_safe(await _chart_payload())

        tax_settings = storage.tax_settings
        entries = storage.entries
        depots = storage.depots
        goals = storage.goals
        cached_fifo = storage.fifo_summary()
        cached_depot_fifo = {
            str(depot["id"]): storage.fifo_summary(str(depot["id"]))
            for depot in depots
        }
        calculations = await hass.async_add_executor_job(
            _build_dashboard_calculations,
            entries,
            depots,
            goals,
            prices,
            int(tax_settings.get("long_term_days", 365)),
            cached_fifo,
            cached_depot_fifo,
        )
        dashboard_settings = dict(current_settings)
        if not security.is_owner(requester):
            dashboard_settings.pop(CONF_HISTORY_TOR_PROXY, None)
        visible_tor_proxy = str(
            current_settings.get(CONF_HISTORY_TOR_PROXY, DEFAULT_HISTORY_TOR_PROXY)
        ) if security.is_owner(requester) else ""
        network_security = network_security_snapshot(hass)
        if not security.is_owner(requester):
            network_security["last_blocked_host"] = None
            network_security["last_tor_error"] = None
            network_security["connections"] = []
        connection_inventory = (
            _connection_inventory(
                current_settings, history_data, network_security, price_details,
            )
            if security.is_owner(requester)
            else {
                "policy": "local-direct-or-tor-only",
                "live_price_sources": [],
                "history_sources": [],
                "observed_connections": [],
            }
        )
        summary_fifo = _dashboard_fifo_summary(calculations["fifo"], currencies)
        history_summary = {
            "enabled": bool(current_settings.get(CONF_HISTORY_ENABLED, True)),
            "auto_sync": bool(current_settings.get(CONF_HISTORY_AUTO_SYNC, True)),
            "auto_sync_runtime_active": bool(runtime.get("history_auto_timer_active")),
            "auto_sync_check_interval_hours": runtime.get("history_auto_check_interval_hours", 6),
            "auto_sync_last_attempt": runtime.get("history_auto_last_attempt"),
            "auto_sync_last_success": runtime.get("history_auto_last_success"),
            "auto_sync_last_result": runtime.get("history_auto_last_result"),
            "tor_proxy": visible_tor_proxy,
            "public_route": "Bundled Tor only; own private local node direct",
            "last_sync": history_data.get("last_sync"),
            "errors": history_data.get("errors", []),
            "cached_daily_values": {
                currency: len(values)
                for currency, values in history_data.get("prices", {}).items()
            },
            "cached_price_samples": {
                currency: len(values)
                for currency, values in history_data.get("price_samples", {}).items()
                if isinstance(values, dict)
            },
            "cached_market_candles": {
                currency: {
                    str(interval): len(values)
                    for interval, values in tiers.items()
                    if isinstance(values, dict)
                }
                for currency, tiers in history_data.get("market_candles", {}).items()
                if isinstance(tiers, dict)
            },
            "bootstrap_complete": history_data.get("bootstrap_complete", {}),
            "source_metadata": history_data.get("source_metadata", {}),
            # Raw price/chart series are fetched only when the overview/chart is
            # visible. Empty containers keep settings rendering backwards-safe.
            "prices": {},
            "price_samples": {},
            "market_candles": {},
            "chart": {},
            "market_interval_minutes": history_interval,
            "days_requested": history_days,
            "all_cached": history_days == 0,
            "series_loaded": False,
        }
        market_snapshot = await async_market_assessment(
            hass, entry, runtime["coordinator"], runtime["history_storage"]
        )
        buy_opportunity_settings = market_snapshot["settings"]
        buy_opportunity = market_snapshot["result"]

        result: dict[str, Any] = {
            "locked": False,
            "section": "summary",
            "portfolio": {
                "config_entry_id": entry_id,
                "title": entry.title if entry else "Bitcoin Stack",
                "version": VERSION,
                "asset": "BTC",
            },
            "brand": {
                "name": BRAND_NAME,
                "watermark": BRAND_WATERMARK,
                "lightning_address": V4V_LIGHTNING_ADDRESS,
            },
            "settings": dashboard_settings,
            "buy_opportunity_settings": buy_opportunity_settings,
            "buy_opportunity_profiles": [*PROFILE_WEIGHTS.keys(), "custom"],
            "buy_opportunity": buy_opportunity,
            "buy_opportunity_calculated_at": market_snapshot.get("calculated_at"),
            "tax_settings": tax_settings,
            "depots": depots,
            "goals": calculations["goals"],
            "fifo": summary_fifo,
            "depot_summaries": calculations["depot_summaries"],
            "depot_entry_counts": _dashboard_depot_entry_counts(entries),
            "purchase_totals": _dashboard_purchase_totals(entries),
            "metrics": build_dashboard_metrics(entries, calculations["fifo"], prices, currencies),
            "prices": prices,
            "price_details": price_details,
            "price_errors": price_errors,
            "network_security": network_security,
            "connection_inventory": connection_inventory,
            "vault_crypto": storage.password_crypto_status(),
            "history": history_summary,
            "currencies": currencies,
            "security": {
                **runtime["security"].public_status(requester),
                "setup_required": storage.setup_required,
            },
            "disclaimer": "Holding-period and FIFO overview only; not tax advice and not a tax return.",
        }

        if section == "all":
            chart_payload = await _chart_payload()
            result["section"] = "all"
            result["entries"] = _dashboard_ledger_entries(entries)
            result["chart_ledger_events"] = chart_payload["chart_ledger_events"]
            result["history"].update(chart_payload["history"])
            result["fifo"] = calculations["fifo"]
            result["fifo"]["currency_summaries"] = summary_fifo["currency_summaries"]

        return _json_safe(result)

    async def list_users(call: ServiceCall) -> dict[str, Any]:
        entry_id = call.data[CONF_CONFIG_ENTRY_ID]
        requester = await _authorize_call(hass, call, entry_id, owner_only=True, require_unlocked=False)
        security: BitcoinSecurityStore = _runtime(hass, entry_id)["security"]
        return {
            "users": await security.async_user_directory(),
            "security": security.public_status(requester),
        }

    async def set_allowed_users(call: ServiceCall) -> dict[str, Any]:
        entry_id = call.data[CONF_CONFIG_ENTRY_ID]
        requester = await _authorize_call(hass, call, entry_id, owner_only=True, require_unlocked=False)
        security: BitcoinSecurityStore = _runtime(hass, entry_id)["security"]
        return await security.async_set_allowed_users(
            requester, list(call.data[CONF_ALLOWED_USER_IDS])
        )

    async def security_status(call: ServiceCall) -> dict[str, Any]:
        entry_id = call.data[CONF_CONFIG_ENTRY_ID]
        requester = await _authorize_call(
            hass, call, entry_id, require_unlocked=False
        )
        runtime = _runtime(hass, entry_id)
        result = runtime["security"].public_status(requester)
        result["setup_required"] = runtime["storage"].setup_required
        return result

    async def lock_vault(call: ServiceCall) -> dict[str, Any]:
        entry_id = call.data[CONF_CONFIG_ENTRY_ID]
        requester = await _authorize_call(
            hass, call, entry_id, require_unlocked=False
        )
        runtime = _runtime(hass, entry_id)
        security: BitcoinSecurityStore = runtime["security"]
        security.lock_user(requester)
        if security.unlocked_user_count == 0:
            await runtime["storage"].async_lock()
        result = security.public_status(requester)
        result["setup_required"] = runtime["storage"].setup_required
        return result

    async def set_sensitive_sensors(call: ServiceCall) -> dict[str, Any]:
        entry_id = call.data[CONF_CONFIG_ENTRY_ID]
        requester = await _authorize_call(hass, call, entry_id, owner_only=True, require_unlocked=False)
        security: BitcoinSecurityStore = _runtime(hass, entry_id)["security"]
        try:
            result = await security.async_set_sensitive_sensors(
                requester, bool(call.data[CONF_ENABLED])
            )
        except ValueError as err:
            raise vol.Invalid(str(err)) from err
        await hass.config_entries.async_reload(entry_id)
        return result

    async def purge_statistics(call: ServiceCall) -> dict[str, Any]:
        entry_id = call.data[CONF_CONFIG_ENTRY_ID]
        await _authorize_call(
            hass, call, entry_id, owner_only=True, require_unlocked=False
        )
        history_store: BitcoinHistoryStore = _runtime(hass, entry_id)["history_storage"]
        state = history_store.data
        statistic_ids = list(state.get("statistics_ids", []))
        removed = await async_clear_entry_statistics(hass, statistic_ids)
        await history_store.async_set_statistics_state({}, [])
        _LOGGER.warning(
            "User-requested cleanup queued for %d Bitcoin Stack Tracker statistic series on %s",
            removed,
            entry_id,
        )
        return {"removed_statistics": removed}

    registrations = [
        (SERVICE_ADD_PURCHASE, add_purchase, _with_requester(TRANSACTION_SCHEMA), SupportsResponse.OPTIONAL),
        (SERVICE_ADD_INCOME, add_income, _with_requester(TRANSACTION_SCHEMA), SupportsResponse.OPTIONAL),
        (SERVICE_ADD_SALE, add_sale, _with_requester(TRANSACTION_SCHEMA), SupportsResponse.OPTIONAL),
        (SERVICE_ADD_EXPENSE, add_expense, _with_requester(TRANSACTION_SCHEMA), SupportsResponse.OPTIONAL),
        (SERVICE_ADD_NETWORK_FEE, add_network_fee, _with_requester(NETWORK_FEE_SCHEMA), SupportsResponse.OPTIONAL),
        (SERVICE_ADD_STACK, add_stack, _with_requester(ADD_STACK_SCHEMA), SupportsResponse.OPTIONAL),
        (SERVICE_BULK_IMPORT, bulk_import, _with_requester(BULK_IMPORT_SCHEMA), SupportsResponse.ONLY),
        (SERVICE_ADD_DEPOT, add_depot, _with_requester(ADD_DEPOT_SCHEMA), SupportsResponse.OPTIONAL),
        (SERVICE_DELETE_DEPOT, delete_depot, _with_requester(DELETE_DEPOT_SCHEMA), SupportsResponse.OPTIONAL),
        (SERVICE_ADD_GOAL, add_goal, _with_requester(ADD_GOAL_SCHEMA), SupportsResponse.OPTIONAL),
        (SERVICE_UPDATE_GOAL, update_goal, _with_requester(UPDATE_GOAL_SCHEMA), SupportsResponse.OPTIONAL),
        (SERVICE_DELETE_GOAL, delete_goal, _with_requester(DELETE_GOAL_SCHEMA), SupportsResponse.OPTIONAL),
        (SERVICE_UPDATE_ENTRY, update_entry, _with_requester(UPDATE_ENTRY_SCHEMA), SupportsResponse.OPTIONAL),
        (SERVICE_DELETE_ENTRY, delete_entry, _with_requester(DELETE_SCHEMA), SupportsResponse.OPTIONAL),
        (SERVICE_DELETE_ALL_ENTRIES, delete_all_entries, _with_requester(ENTRY_SCHEMA), SupportsResponse.ONLY),
        (SERVICE_SET_GOAL, set_goal, _with_requester(SET_GOAL_SCHEMA), SupportsResponse.OPTIONAL),
        (SERVICE_SET_TAX_SETTINGS, set_tax_settings, _with_requester(SET_TAX_SCHEMA), SupportsResponse.OPTIONAL),
        (SERVICE_EXPORT_LEDGER, export_ledger, _with_requester(ENTRY_SCHEMA), SupportsResponse.ONLY),
        (SERVICE_EXPORT_CSV, export_csv, _with_requester(EXPORT_CSV_SCHEMA), SupportsResponse.ONLY),
        (SERVICE_SYNC_HISTORY, sync_history, _with_requester(ENTRY_SCHEMA), SupportsResponse.ONLY),
        (SERVICE_SET_HISTORY_SETTINGS, set_history_settings, SET_HISTORY_SETTINGS_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_SET_BUY_OPPORTUNITY_SETTINGS, set_buy_opportunity_settings, SET_BUY_OPPORTUNITY_SETTINGS_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_LIST_PORTFOLIOS, list_portfolios, vol.Schema(REQUESTER_SCHEMA), SupportsResponse.ONLY),
        (SERVICE_DASHBOARD_DATA, dashboard_data, _with_requester(DASHBOARD_DATA_SCHEMA), SupportsResponse.ONLY),
        (SERVICE_LIST_USERS, list_users, _with_requester(ENTRY_SCHEMA), SupportsResponse.ONLY),
        (SERVICE_SET_ALLOWED_USERS, set_allowed_users, SET_ALLOWED_USERS_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_SECURITY_STATUS, security_status, _with_requester(ENTRY_SCHEMA), SupportsResponse.ONLY),
        (SERVICE_LOCK_VAULT, lock_vault, LOCK_VAULT_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_SET_SENSITIVE_SENSORS, set_sensitive_sensors, SET_SENSITIVE_SENSORS_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_PURGE_STATISTICS, purge_statistics, PURGE_STATISTICS_SCHEMA, SupportsResponse.ONLY),
    ]
    if not hass.services.has_service(DOMAIN, SERVICE_ADD_PURCHASE):
        for service, handler, schema, response in registrations:
            async def protected_handler(
                call: ServiceCall,
                _handler=handler,
                _service=service,
            ):
                started = monotonic()
                entry_id = str(call.data.get(CONF_CONFIG_ENTRY_ID, ""))
                requester = str(call.context.user_id or "system")
                try:
                    if _service in RATE_LIMITS and entry_id:
                        requester = await _authenticated_service_user_id(hass, call)
                        _enforce_rate_limit(
                            hass,
                            entry_id=entry_id,
                            user_id=requester,
                            operation=_service,
                        )
                    if _service not in {
                        SERVICE_LIST_PORTFOLIOS, SERVICE_DASHBOARD_DATA,
                        SERVICE_LIST_USERS, SERVICE_SET_ALLOWED_USERS,
                        SERVICE_SECURITY_STATUS, SERVICE_LOCK_VAULT,
                        SERVICE_SET_SENSITIVE_SENSORS, SERVICE_PURGE_STATISTICS,
                        SERVICE_DELETE_ALL_ENTRIES,
                        SERVICE_SET_HISTORY_SETTINGS,
                        SERVICE_SET_BUY_OPPORTUNITY_SETTINGS,
                    }:
                        requester = await _authorize_call(hass, call, entry_id)
                    result = await _handler(call)
                except Exception:
                    duration_ms = int((monotonic() - started) * 1000)
                    _technical_log_append(hass, "ERROR", f"service={_service} status=failed duration_ms={duration_ms}")
                    _LOGGER.exception(
                        "Service failed service=%s entry=%s user=%s duration_ms=%d",
                        _service,
                        entry_id[-8:] if entry_id else "-",
                        requester[-8:] if requester else "-",
                        duration_ms,
                    )
                    raise
                duration_ms = int((monotonic() - started) * 1000)
                _technical_log_append(hass, "INFO", f"service={_service} status=completed duration_ms={duration_ms}")
                _LOGGER.debug(
                    "Service completed service=%s entry=%s user=%s duration_ms=%d",
                    _service,
                    entry_id[-8:] if entry_id else "-",
                    requester[-8:] if requester else "-",
                    duration_ms,
                )
                return result

            hass.services.async_register(
                DOMAIN,
                service,
                protected_handler,
                schema=schema,
                supports_response=response,
            )
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entries created by every published beta."""
    try:
        version, data = migrate_config_data(entry.version, dict(entry.data))
    except ValueError:
        _LOGGER.exception("Cannot migrate Bitcoin Stack Tracker entry %s", entry.entry_id)
        return False
    if version != entry.version or data != dict(entry.data):
        _LOGGER.info(
            "Migrating Bitcoin Stack Tracker entry %s from version %s to %s",
            entry.entry_id,
            entry.version,
            version,
        )
        hass.config_entries.async_update_entry(entry, version=version, data=data)
    return version == LATEST_CONFIG_VERSION


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one Bitcoin portfolio without persisting its master password."""
    # Register again at config-entry setup as a defensive fallback.  A full Core
    # restart after replacing custom_components is still recommended, but the
    # backend must not depend on the one global setup timing window for its UI.
    from .panel import async_register_native_panel
    await async_register_native_panel(hass)

    requested_mode = str(entry.data.get(CONF_ENCRYPTION_MODE, ENCRYPTION_NONE))
    security = BitcoinSecurityStore(hass, entry.entry_id)
    await security.async_load(default_encryption_mode=requested_mode)

    setup_token = str(entry.data.get(CONF_SETUP_TOKEN) or "")
    pending = hass.data.setdefault(DOMAIN, {}).setdefault("_pending_passwords", {})
    pending_setup = pending.pop(setup_token, None) if setup_token else None
    if isinstance(pending_setup, dict):
        initial_password = str(pending_setup.get("password") or "") or None
        initial_goal_btc = pending_setup.get("goal_btc", entry.data.get(CONF_GOAL_BTC, 0))
    else:
        # Compatibility with legacy one-time password handoff data.
        initial_password = pending_setup
        initial_goal_btc = entry.data.get(CONF_GOAL_BTC, 0)

    storage = BitcoinLedgerStore(hass, entry.entry_id, security)
    await storage.async_load(
        initial_mode=requested_mode,
        initial_password=initial_password,
    )
    if initial_password:
        security.mark_user_unlocked(security.owner_user_id)

    # Keep the config entry aligned with migrated legacy/password storage, but
    # never retain the one-time setup token or the master password.
    if (
        entry.data.get(CONF_ENCRYPTION_MODE) != security.encryption_mode
        or CONF_SETUP_TOKEN in entry.data
    ):
        data = dict(entry.data)
        data.pop(CONF_SETUP_TOKEN, None)
        data[CONF_ENCRYPTION_MODE] = security.encryption_mode
        hass.config_entries.async_update_entry(entry, data=data)

    currencies = configured_currencies(effective_settings(entry))
    if not storage.is_locked:
        await storage.async_ensure_legacy_goal(
            initial_goal_btc,
            currency=currencies[0] if currencies else "EUR",
        )
        if CONF_GOAL_BTC in entry.data:
            data = dict(entry.data)
            data.pop(CONF_GOAL_BTC, None)
            hass.config_entries.async_update_entry(entry, data=data)

    history_storage = BitcoinHistoryStore(hass, entry.entry_id)
    await history_storage.async_load()
    market_assessment_history_cache = MarketAssessmentHistoryCache(hass, entry.entry_id)
    await market_assessment_history_cache.async_load()
    market_assessment_intraday_cache = MarketAssessmentIntradayCache(hass, entry.entry_id)
    await market_assessment_intraday_cache.async_load()
    coordinator = BitcoinPriceCoordinator(hass, entry, history_storage)
    await coordinator.async_config_entry_first_refresh()
    # Keep one integration-owned listener registered permanently. Home Assistant's
    # DataUpdateCoordinator only schedules update_interval refreshes while it has
    # at least one listener. Price refreshes must therefore never depend on an
    # open dashboard or on a particular HA sensor entity being enabled.
    cancel_price_refresh_listener = coordinator.async_add_listener(lambda: None)

    wallet_watch = WalletWatchManager(hass, entry, storage)
    runtime: dict[str, Any] = {
        "storage": storage,
        "history_storage": history_storage,
        "market_assessment_history_cache": market_assessment_history_cache,
        "market_assessment_intraday_cache": market_assessment_intraday_cache,
        "coordinator": coordinator,
        "cancel_price_refresh_listener": cancel_price_refresh_listener,
        "security": security,
        "wallet_watch": wallet_watch,
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    _register_global_timers(hass)
    await wallet_watch.async_start()
    if not storage.is_locked:
        try:
            await wallet_watch.async_restore_full_config(normalize_watch_config(storage.wallet_watch_config), poll=False)
        except ValueError as err:
            _LOGGER.warning("Sats Sentinel configuration was not activated: %s", err)

    _configure_history_timer(
        hass, entry, runtime, sync_if_stale=True
    )
    # Entry-local watchdog in addition to the domain timer.  This survives the
    # exact setup path used by config-entry-only reloads and makes the persisted
    # Tor rotation deadline independent from an open browser.
    runtime["cancel_tor_rotation"] = async_track_time_interval(
        hass,
        partial(
            _async_rotate_tor_if_due,
            hass,
            entry_id=entry.entry_id,
            trigger="entry-timer",
        ),
        _TOR_ROTATION_ENTRY_CHECK,
    )
    await _async_rotate_tor_if_due(
        hass, entry_id=entry.entry_id, trigger="entry-setup"
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove private storage and all tracked external statistics."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    if isinstance(runtime, dict) and isinstance(runtime.get("wallet_watch"), WalletWatchManager):
        await runtime["wallet_watch"].async_stop()
        await runtime["wallet_watch"].runtime_store.async_remove()
    history_store = BitcoinHistoryStore(hass, entry.entry_id)
    await history_store.async_load()
    market_history_cache = MarketAssessmentHistoryCache(hass, entry.entry_id)
    await market_history_cache.async_load()
    statistic_ids = list(history_store.data.get("statistics_ids", []))
    removed = await async_clear_entry_statistics(hass, statistic_ids)
    security_store = BitcoinSecurityStore(hass, entry.entry_id)
    ledger_store = BitcoinLedgerStore(hass, entry.entry_id, security_store)
    await history_store.async_remove()
    await market_history_cache.async_remove()
    await ledger_store.async_remove()
    await security_store.async_remove()
    _LOGGER.info(
        "Removed Bitcoin Stack Tracker entry %s and queued cleanup of %d statistic series",
        entry.entry_id,
        removed,
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    if isinstance(runtime, dict) and isinstance(runtime.get("wallet_watch"), WalletWatchManager):
        await runtime["wallet_watch"].async_stop()
    if cancel := runtime.get("cancel_history_sync"):
        cancel()
    if cancel := runtime.get("cancel_tor_rotation"):
        cancel()
    if cancel := runtime.get("cancel_price_refresh_listener"):
        cancel()
    market_task = runtime.get("_market_assessment_task") if isinstance(runtime, dict) else None
    if market_task is not None and not market_task.done():
        market_task.cancel()
        try:
            await market_task
        except asyncio.CancelledError:
            pass
    history_tasks = list(runtime.get("_market_assessment_history_tasks", {}).values()) if isinstance(runtime, dict) else []
    for task in history_tasks:
        if task is not None and not task.done():
            task.cancel()
    for task in history_tasks:
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                _LOGGER.debug("Market-assessment history task ended during unload", exc_info=True)
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded

