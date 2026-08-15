from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_service_identity_cannot_be_forwarded():
    text=(ROOT/"custom_components/bitcoin_stack_tracker/__init__.py").read_text()
    assert 'CONF_REQUESTER_USER_ID = "actor_user_id"' not in text
    block=text[text.index("async def _authenticated_service_user_id"):text.index("async def _authorize_call")]
    assert "call.context.user_id" in block
    assert "call.data" not in block


def test_native_iframe_uses_authenticated_same_origin_postmessage_bridge():
    panel=(ROOT/"custom_components/bitcoin_stack_tracker/frontend/panel-v021009-ae7b9cb3.js").read_text()
    app=(ROOT/"custom_components/bitcoin_stack_tracker/frontend/static/app-v021009-bba91c83.js").read_text()
    assert "new MessageChannel()" not in panel
    assert "nativeBridgeReady" not in app
    assert "event.source !== this._frame.contentWindow" in panel
    assert "event.origin !== window.location.origin" in panel
    assert "event.source !== window.parent" in app
    assert "event.origin !== window.location.origin" in app
    assert "window.parent.postMessage(request,window.location.origin)" in app


def test_backup_is_data_only():
    text=(ROOT/"custom_components/bitcoin_stack_tracker/__init__.py").read_text()
    block=text[text.index("async def _async_backup_payload"):text.index("def _validate_backup_payload")]
    assert '"backup_schema": 2' in block
    assert '"ledger"' in block and '"history"' in block
    assert '"settings"' not in block and '"access"' not in block
    assert '"tax_settings"' not in block and '"chart_cache"' not in block
    assert '"source_metadata"' not in block and '"last_sync"' not in block
    restore=text[text.index("async def _panel_restore_payload"):text.index("async def _panel_tor_exit_ip")]
    assert "async_update_entry" not in restore
    assert "async_restore_allowed_users" not in restore


def test_tor_ports_and_input_killswitch():
    run=(ROOT/"bitcoin_stack_tracker_dashboard/run.sh").read_text()
    tor=(ROOT/"bitcoin_stack_tracker_dashboard/torrc").read_text()
    assert 'export TOR_SHARED_PORT="9051"' in run
    assert 'hook input priority filter; policy drop' in run
    assert 'BST_SOCKS_CORE_ONLY' in run
    assert 'BST_SOCKS_SHARED_INTERNAL' in run
    assert ':9051 IsolateSOCKSAuth' in tor


def test_provider_payloads_use_bounded_helpers():
    for rel in ["coordinator.py","history.py","config_flow.py"]:
        text=(ROOT/"custom_components/bitcoin_stack_tracker"/rel).read_text()
        assert "await response.json(" not in text
    init=(ROOT/"custom_components/bitcoin_stack_tracker/__init__.py").read_text()
    assert "await response.json(" not in init
    assert (ROOT/"custom_components/bitcoin_stack_tracker/http_limits.py").exists()


def test_transitive_security_dependencies_are_pinned():
    import json
    manifest=json.loads((ROOT/"custom_components/bitcoin_stack_tracker/manifest.json").read_text())
    assert "python-socks==2.8.2" in manifest["requirements"]
    assert "argon2-cffi-bindings==25.1.0" in manifest["requirements"]
    lock=(ROOT/"DEPENDENCIES.lock").read_text()
    assert "aiohttp-socks==0.11.0" in lock
    assert "python-socks==2.8.2" in lock


def test_bridge_does_not_accept_cross_window_or_cross_origin_messages():
    panel=(ROOT/"custom_components/bitcoin_stack_tracker/frontend/panel-v021009-ae7b9cb3.js").read_text()
    assert "event.source !== this._frame.contentWindow" in panel
    assert "event.origin !== window.location.origin" in panel
    assert 'message.source !== RPC_SOURCE' in panel


def test_native_panel_chunked_body_is_bounded():
    init=(ROOT/"custom_components/bitcoin_stack_tracker/__init__.py").read_text()
    block=init[init.index("class BitcoinStackNativePanelRpcView"):init.index("if route == \"api/whoami\"")]
    assert "request.content.readexactly(_PANEL_RPC_MAX_BYTES + 1)" in block
    assert "await request.json()" not in block


def test_base_images_are_immutable_per_architecture():
    docker=(ROOT/"bitcoin_stack_tracker_dashboard/Dockerfile").read_text()
    assert "amd64-base:3.22-2026.06.1@sha256:368b5fcd266d1e5a643bad9bc9e84760760032e911ecfdef2a7fc148d76035d1" in docker
    assert "aarch64-base:3.22-2026.06.1@sha256:03185a346a3e505e0aa102cb1e976a2e7be7421cf4a405abd2cd83e0a6bd0a58" in docker
    assert "FROM base-${BUILD_ARCH}" in docker


def test_outer_apparmor_blocks_ha_and_process_memory():
    profile=(ROOT/"bitcoin_stack_tracker_dashboard/apparmor.txt").read_text()
    assert "deny /config/** rwklx" in profile
    assert "deny /homeassistant/** rwklx" in profile
    assert "deny /var/run/docker.sock rwklx" in profile
    assert "deny /proc/*/mem rwklx" in profile


def test_tor_gateway_blocks_private_egress_even_for_tor_uid():
    run = (ROOT / "bitcoin_stack_tracker_dashboard/run.sh").read_text(encoding="utf-8")
    local_block = run.index('comment "BST_BLOCK_LOCAL_IPV4"')
    tor_allow = run.index('comment "BST_TOR_PUBLIC"')
    assert local_block < tor_allow
    assert 'comment "BST_BLOCK_LOCAL_IPV6"' in run
    assert 'comment "BST_LOCAL_IPV4"' not in run
    assert 'comment "BST_LOCAL_IPV6"' not in run


def test_release_integrity_helper_never_embeds_a_private_key():
    helper = (ROOT / "tools/release-integrity.sh").read_text(encoding="utf-8")
    assert "sha256sum" in helper
    assert "minisign -Sm" in helper
    assert "MINISIGN_SECRET_KEY" in helper
    assert "BEGIN PRIVATE KEY" not in helper
