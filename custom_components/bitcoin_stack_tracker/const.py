"""Constants for Bitcoin Stack Tracker."""

from __future__ import annotations

import hashlib

DOMAIN = "bitcoin_stack_tracker"
PLATFORMS = ["sensor"]
VERSION = "0.21.0.13"
# Public frontend build stays aligned with the release. A separate cache revision
# can be bumped for final/repacked assets without inventing a new integration version.
FRONTEND_BUILD = "0.21.0.13"
FRONTEND_CACHE_REVISION = "7"

CONF_NAME = "name"
CONF_GOAL_BTC = "goal_btc"  # Legacy single-goal setting; migrated to local storage.
CONF_SOURCES = "sources"
CONF_SOURCE_TYPE = "source_type"
CONF_CURRENCIES = "currencies"
CONF_CURRENCY = "currency"
CONF_ENTITY_ID = "entity_id"
CONF_BASE_URL = "base_url"
CONF_VERIFY_SSL = "verify_ssl"
CONF_HISTORY_TOR_PROXY = "history_tor_proxy"
CONF_MEMPOOL_OWN_INSTANCE = "mempool_own_instance"
CONF_MEMPOOL_ROUTE = "mempool_route"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_PUBLIC_UPDATE_INTERVAL = "public_update_interval"
CONF_HISTORY_ENABLED = "history_enabled"
CONF_HISTORY_DAYS = "history_days"
CONF_HISTORY_AUTO_SYNC = "history_auto_sync"
CONF_BUY_OPPORTUNITY_SETTINGS = "buy_opportunity_settings"
CONF_LONG_TERM_DAYS = "long_term_days"
CONF_TAX_NOTE = "tax_note"
CONF_ENCRYPTION_ENABLED = "encryption_enabled"
CONF_ENCRYPTION_MODE = "encryption_mode"
CONF_SETUP_TOKEN = "setup_token"
CONF_VAULT_PASSWORD = "vault_password"
CONF_VAULT_PASSWORD_CONFIRM = "vault_password_confirm"

SOURCE_KRAKEN = "kraken"
SOURCE_MEMPOOL = "mempool"
SOURCE_ENTITY = "entity"

MEMPOOL_ROUTE_TOR = "tor"
MEMPOOL_ROUTE_DIRECT = "direct"

UNIT_BTC = "BTC"
UNIT_SATS = "sats"
DEFAULT_UPDATE_INTERVAL = 300
MIN_UPDATE_INTERVAL = 60
MAX_UPDATE_INTERVAL = 3600
DEFAULT_PUBLIC_UPDATE_INTERVAL = 60
MIN_PUBLIC_UPDATE_INTERVAL = 30
MAX_PUBLIC_UPDATE_INTERVAL = 300
DEFAULT_MEMPOOL_URL = "https://mempool.space"

TOR_GATEWAY_REPOSITORY_URL = "https://github.com/21Koblenz/bitcoin-stack-tracker"
TOR_GATEWAY_SLUG = "bitcoin_stack_tracker_dashboard"
TOR_GATEWAY_REPOSITORY_ID = hashlib.sha1(
    TOR_GATEWAY_REPOSITORY_URL.lower().encode()
).hexdigest()[:8]
TOR_GATEWAY_PUBLISHED_HOST = (
    f"{TOR_GATEWAY_REPOSITORY_ID}-{TOR_GATEWAY_SLUG.replace('_', '-')}"
)
TOR_GATEWAY_LOCAL_HOST = f"local-{TOR_GATEWAY_SLUG.replace('_', '-')}"
TOR_GATEWAY_HOST_CANDIDATES = (TOR_GATEWAY_PUBLISHED_HOST, TOR_GATEWAY_LOCAL_HOST)
DEFAULT_HISTORY_TOR_PROXY = f"socks5://{TOR_GATEWAY_PUBLISHED_HOST}:9050"
LOCAL_HISTORY_TOR_PROXY = f"socks5://{TOR_GATEWAY_LOCAL_HOST}:9050"
LEGACY_HISTORY_TOR_PROXY = "socks5://127.0.0.1:9050"
DEFAULT_KRAKEN_CURRENCIES = ["EUR"]
KRAKEN_CURRENCIES = ["EUR", "USD", "GBP", "CAD", "CHF", "AUD", "JPY"]

DEFAULT_HISTORY_DAYS = 0  # 0 means all locally available daily values.
MIN_HISTORY_DAYS = 0
MAX_HISTORY_DAYS = 36500
DEFAULT_LONG_TERM_DAYS = 365
MIN_LONG_TERM_DAYS = 1
MAX_LONG_TERM_DAYS = 36500
DEFAULT_TAX_NOTE = (
    "Configurable holding-period overview only. Depending on the applicable law, "
    "coins older than the selected period may be treated differently. Not tax advice "
    "and not a tax return."
)
DEFAULT_DEPOT_ID = "main"
ALL_DEPOTS = "all"

# Keep Store's external version stable and migrate the internal schema ourselves.
STORAGE_VERSION = 1
STORAGE_SCHEMA_VERSION = 5
SECURITY_SCHEMA_VERSION = 2
STORAGE_KEY_PREFIX = f"{DOMAIN}.ledger"
HISTORY_STORAGE_KEY_PREFIX = f"{DOMAIN}.history"
SECURITY_STORAGE_KEY_PREFIX = f"{DOMAIN}.security"
RUNTIME = "runtime"

BRAND_NAME = "Einundzwanzig Koblenz"
BRAND_WATERMARK = "created by Einundzwanzig Koblenz"
V4V_LIGHTNING_ADDRESS = "creamowl25@primal.net"
