from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CC = ROOT / "custom_components" / "bitcoin_stack_tracker"
INIT = (CC / "__init__.py").read_text(encoding="utf-8")
FLOW = (CC / "config_flow.py").read_text(encoding="utf-8")
HISTORY = (CC / "history.py").read_text(encoding="utf-8")
STORAGE = (CC / "storage.py").read_text(encoding="utf-8")
NETWORK = (CC / "network.py").read_text(encoding="utf-8")
CSV_IMPORT = (CC / "csv_import.py").read_text(encoding="utf-8")
EXPORT = (CC / "export.py").read_text(encoding="utf-8")
TORRC = (ROOT / "bitcoin_stack_tracker_dashboard" / "torrc").read_text(encoding="utf-8")
RUN = (ROOT / "bitcoin_stack_tracker_dashboard" / "run.sh").read_text(encoding="utf-8")
AGENT = (ROOT / "bitcoin_stack_tracker_dashboard" / "app" / "network_agent.py").read_text(encoding="utf-8")
APP = (CC / "frontend" / "static" / "app.js").read_text(encoding="utf-8")


def _route(name: str, next_name: str) -> str:
    return INIT.split(f'if route == "{name}"', 1)[1].split(f'if route == "{next_name}"', 1)[0]


def test_http_identity_cannot_be_overridden_by_header_or_query():
    block = INIT.split("async def _request_user_from_http", 1)[1].split("async def _async_backup_payload", 1)[0]
    assert 'request["hass_user"]' in block
    assert "X-Bitcoin-Stack-Requester" not in block
    assert 'request.query.get("actor_user_id"' not in block


def test_import_preview_authorizes_before_parser():
    block = _route("api/import/preview", "api/download")
    assert 'require_unlocked(requester)' in block
    assert 'operation="import_preview"' in block
    assert block.index('require_unlocked(requester)') < block.index('parse_transaction_upload')


def test_restore_authorizes_and_rate_limits_before_argon2_backup_decryption():
    block = _route("api/restore", "api/core-network")
    assert 'require_owner(requester)' in block
    assert 'require_unlocked(requester)' in block
    assert 'operation="restore"' in block
    assert block.index('require_owner(requester)') < block.index('_validate_and_decrypt_backup_bytes')
    assert block.index('operation="restore"') < block.index('_validate_and_decrypt_backup_bytes')


def test_network_telemetry_is_owner_only():
    block = _route("api/network-status", "api/chart/halvings")
    assert 'require_owner(requester)' in block


def test_encrypted_initial_goal_uses_ram_handoff_and_legacy_goal_is_scrubbed():
    create = FLOW.split("def _create_entry", 1)[1].split("async_get_options_flow", 1)[0]
    assert '"goal_btc": self._base[CONF_GOAL_BTC]' in create
    assert '[token] = {' in create
    assert 'data[CONF_GOAL_BTC] = self._base[CONF_GOAL_BTC]' in create  # only non-encrypted branch
    setup = INIT.split("async def async_setup_entry", 1)[1]
    assert 'initial_goal_btc = pending_setup.get("goal_btc"' in setup
    assert 'data.pop(CONF_GOAL_BTC, None)' in setup


def test_history_does_not_persist_own_node_url():
    assert '"configured_base_url": str(own_sources[0].get(CONF_BASE_URL' not in HISTORY
    assert 'def _scrub_source_metadata' in STORAGE
    assert 'if str(key) != "configured_base_url"' in STORAGE
    assert 'scrubbed_legacy_metadata' in STORAGE
    assert 'own mempool instance unavailable ({type(err).__name__})' in HISTORY


def test_public_non_onion_targets_require_https_and_tls_verification_over_tor():
    assert 'requires HTTPS over Tor' in NETWORK
    assert 'TLS verification may not be disabled for public target' in NETWORK
    assert 'if not is_onion_url(target):' in NETWORK


def test_shared_tor_socks_proxy_remains_available_to_addon_network():
    assert 'SocksPolicy accept 172.30.32.0/23' in TORRC
    assert '172.30.32.0/23' in RUN
    assert 'tcp dport ${TOR_PORT}' in RUN and 'BST_SOCKS_CORE_ONLY' in RUN
    assert 'tcp dport ${TOR_SHARED_PORT}' in RUN and 'BST_SOCKS_SHARED_INTERNAL' in RUN


def test_csv_parser_and_export_have_resource_and_formula_guards():
    assert 'MAX_IMPORT_COLUMNS = 128' in CSV_IMPORT
    assert 'MAX_IMPORT_CELL_CHARS = 16_384' in CSV_IMPORT
    assert 'if len(records) > max_records:' in CSV_IMPORT
    assert 'def _safe_csv_text' in EXPORT
    assert 'startswith(("=", "+", "-", "@"))' in EXPORT
    assert 'Persistent plaintext CSV export is disabled for privacy' in INIT


def test_shared_gateway_status_does_not_expose_socket_ip_lists_to_peer_addons():
    block = AGENT.split('if path == "/network-status":', 1)[1].split('if path == "/":', 1)[0]
    assert '"tor_public_socket_targets"' not in block
    assert '"app_local_socket_targets"' not in block
    assert '"non_tor_public_socket_targets"' not in block
    assert '"clearnet_leak_detected"' in block


def test_non_owner_dashboard_does_not_poll_owner_only_network_telemetry():
    block = APP.split('async function refreshNetworkStatus', 1)[1].split('function startNetworkPolling', 1)[0]
    assert '!state.data?.security?.owner' in block
