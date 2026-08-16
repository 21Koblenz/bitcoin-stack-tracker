from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components/bitcoin_stack_tracker"
CRYPTO_PATH = COMP / "crypto.py"
STORAGE_PATH = COMP / "storage.py"
INIT_PATH = COMP / "__init__.py"
PANEL_PATH = COMP / "panel.py"
APP_PATH = COMP / "frontend/static/app.js"
INDEX_PATH = COMP / "frontend/index.html"
PANEL_JS_PATH = COMP / "frontend/panel.js"
ADDON = ROOT / "bitcoin_stack_tracker_dashboard"
RUN_PATH = ADDON / "run.sh"


def load_crypto(name: str):
    spec = spec_from_file_location(name, CRYPTO_PATH)
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_v3_local_vault_uses_envelope_encryption_and_device_binding():
    crypto = load_crypto("bst_crypto_v030_local")
    payload = {"entries": [{"id": "one", "amount_btc": "0.001"}]}
    device_secret = crypto.new_device_secret()
    envelope, dek = crypto.create_password_envelope(
        payload,
        password="correct horse battery staple 2026",
        entry_id="entry-test",
        device_secret=device_secret,
    )
    assert len(device_secret) == 32
    assert len(dek) == 32
    assert envelope["version"] == 3
    assert envelope["encryption_mode"] == "password-argon2id-envelope-v3"
    assert envelope["key_wrap"]["algorithm"] == "AES-256-GCM"
    assert envelope["key_wrap"]["device_bound"] is True
    assert envelope["key_wrap"]["kek_bits"] == 256
    assert envelope["key_wrap"]["wrapped_key_bits"] == 256
    assert envelope["key_wrap"]["hkdf"] == "HKDF-SHA-512"
    assert envelope["data"]["key_bits"] == 256
    assert envelope["data"]["nonce_bits"] == 96
    assert envelope["data"]["tag_bits"] == 128
    assert envelope["data"]["aad"] is True

    restored, restored_dek = crypto.decrypt_password_envelope(
        envelope,
        password="correct horse battery staple 2026",
        entry_id="entry-test",
        device_secret=device_secret,
    )
    assert restored == payload
    assert restored_dek == dek


def test_wrong_password_wrong_device_key_and_missing_device_key_all_fail():
    crypto = load_crypto("bst_crypto_v030_wrong_keys")
    device_secret = crypto.new_device_secret()
    envelope, _ = crypto.create_password_envelope(
        {"entries": []},
        password="very long unique master password 123",
        entry_id="entry-test",
        device_secret=device_secret,
    )
    with pytest.raises(crypto.PasswordDecryptionError):
        crypto.decrypt_password_envelope(
            envelope,
            password="wrong but sufficiently long password",
            entry_id="entry-test",
            device_secret=device_secret,
        )
    with pytest.raises(crypto.PasswordDecryptionError):
        crypto.decrypt_password_envelope(
            envelope,
            password="very long unique master password 123",
            entry_id="entry-test",
            device_secret=crypto.new_device_secret(),
        )
    with pytest.raises(crypto.PasswordDecryptionError):
        crypto.decrypt_password_envelope(
            envelope,
            password="very long unique master password 123",
            entry_id="entry-test",
            device_secret=None,
        )


def test_each_data_reencryption_uses_a_fresh_96_bit_nonce():
    crypto = load_crypto("bst_crypto_v030_nonce")
    device_secret = crypto.new_device_secret()
    envelope, dek = crypto.create_password_envelope(
        {"entries": []},
        password="a long unique password for nonce test",
        entry_id="entry-test",
        device_secret=device_secret,
    )
    second = crypto.encrypt_v3_payload_with_dek(
        {"entries": [{"id": "two"}]}, envelope=envelope, dek=dek, context="ledger:entry-test"
    )
    third = crypto.encrypt_v3_payload_with_dek(
        {"entries": [{"id": "three"}]}, envelope=second, dek=dek, context="ledger:entry-test"
    )
    assert second["data"]["nonce"] != envelope["data"]["nonce"]
    assert third["data"]["nonce"] != second["data"]["nonce"]
    assert second["key_wrap"]["nonce"] == envelope["key_wrap"]["nonce"]


def test_password_change_rewraps_the_same_random_dek():
    crypto = load_crypto("bst_crypto_v030_rewrap")
    device_secret = crypto.new_device_secret()
    payload = {"entries": [{"id": "one"}]}
    old, dek = crypto.create_password_envelope(
        payload,
        password="first long master password 2026",
        entry_id="entry-test",
        device_secret=device_secret,
    )
    new = crypto.rewrap_password_envelope(
        payload,
        dek=dek,
        new_password="second long master password 2026",
        entry_id="entry-test",
        device_secret=device_secret,
    )
    assert new["key_wrap"]["ciphertext"] != old["key_wrap"]["ciphertext"]
    assert new["kdf"]["salt"] != old["kdf"]["salt"]
    restored, restored_dek = crypto.decrypt_password_envelope(
        new,
        password="second long master password 2026",
        entry_id="entry-test",
        device_secret=device_secret,
    )
    assert restored == payload
    assert restored_dek == dek


def test_argon2id_profile_is_128_mib_t3_p1_with_256_bit_salt():
    crypto = load_crypto("bst_crypto_v030_argon")
    kdf = crypto.new_kdf_metadata()
    assert kdf["name"] == "argon2id"
    assert kdf["memory_kib"] == 128 * 1024
    assert kdf["time_cost"] == 3
    assert kdf["parallelism"] == 1
    assert kdf["version"] == 19
    profile = crypto.kdf_security_profile(kdf)
    assert profile["estimated_memory_mib"] == 128.0
    assert profile["salt_bits"] == 256
    assert profile["current_profile"] is True


def test_portable_backup_v3_is_envelope_encrypted_but_not_device_bound():
    crypto = load_crypto("bst_crypto_v030_backup")
    payload = {"ledger": {"entries": []}, "history": {}}
    envelope = crypto.create_backup_envelope(
        payload, password="separate high entropy backup password"
    )
    assert envelope["backup_version"] == 3
    assert envelope["encryption_mode"] == "portable-backup-argon2id-envelope-v3"
    assert envelope["key_wrap"]["device_bound"] is False
    assert envelope["portable_binding"]
    assert crypto.decrypt_backup_envelope(
        envelope, password="separate high entropy backup password"
    ) == payload


def test_legacy_scrypt_v1_remains_readable_for_migration():
    crypto = load_crypto("bst_crypto_v030_legacy")
    password = "legacy password 123"
    kdf = {
        "name": "scrypt",
        "salt": crypto._b64(b"0123456789abcdef"),
        "n": 2**15,
        "r": 8,
        "p": 1,
        "length": 32,
    }
    key = crypto._derive_key(password, kdf)
    payload = {"entries": [{"id": "legacy"}]}
    envelope = crypto.encrypt_with_key(
        payload,
        key=key,
        kdf=kdf,
        mode=crypto.PASSWORD_ENVELOPE_MODE_V1,
        context="ledger:legacy-entry",
    )
    restored, _ = crypto.decrypt_password_envelope(
        envelope, password=password, entry_id="legacy-entry"
    )
    assert restored == payload
    assert crypto.password_envelope_needs_upgrade(envelope) is True


def test_new_passwords_require_16_characters():
    crypto = load_crypto("bst_crypto_v030_password_length")
    with pytest.raises(crypto.PasswordValidationError):
        crypto.validate_new_password("x" * 15)
    crypto.validate_new_password("x" * 16)
    index = INDEX_PATH.read_text(encoding="utf-8")
    assert 'name="new_password" type="password" minlength="16"' in index


def test_device_binding_key_is_separate_from_ledger_and_mode_0600():
    storage = STORAGE_PATH.read_text(encoding="utf-8")
    assert '"bitcoin_stack_tracker_device_keys", f"{entry_id}.key"' in storage
    assert "os.O_WRONLY | os.O_CREAT | os.O_EXCL" in storage
    assert "os.chmod(self._device_key_path, 0o600)" in storage
    assert "new_device_secret" in storage
    assert "device_secret=device_secret" in storage


def test_native_panel_is_served_by_home_assistant_core():
    panel = PANEL_PATH.read_text(encoding="utf-8")
    bridge = PANEL_JS_PATH.read_text(encoding="utf-8")
    assert "panel_custom.async_register_panel" in panel
    assert "StaticPathConfig" in panel
    assert 'STATIC_URL = "/api/bitcoin_stack_tracker/frontend"' in panel
    assert 'this._hass.callApi("POST", "bitcoin_stack_tracker/panel/rpc"' in bridge
    assert "native-core-panel" in panel


def test_native_secret_path_bypasses_service_bus_and_addon():
    init = INIT_PATH.read_text(encoding="utf-8")
    start = init.index('if route.startswith("api/vault/")')
    end = init.index('if route == "api/import/preview"', start)
    block = init[start:end]
    assert "_async_unlock_for_requester(" in block
    assert "storage.async_initialize_password" in block
    assert "storage.async_enable_password" in block
    assert "storage.async_change_password" in block
    assert "_panel_call_service" not in block
    assert "service bus" in block
    # Secret-specific legacy HTTP views are no longer registered as a second surface.
    setup_start = init.index("async def async_setup(")
    setup_slice = init[setup_start:setup_start + 1800]
    assert "BitcoinStackNativePanelRpcView(hass)" in setup_slice
    assert "BitcoinStackVaultUnlockView(hass)" not in setup_slice
    assert "BitcoinStackVaultEnableView(hass)" not in setup_slice
    assert "BitcoinStackVaultChangePasswordView(hass)" not in setup_slice


def test_secret_bearing_home_assistant_services_are_not_registered():
    init = INIT_PATH.read_text(encoding="utf-8")
    reg_start = init.index("registrations = [")
    reg_end = init.index("if not hass.services.has_service", reg_start)
    registered = init[reg_start:reg_end]
    assert "SERVICE_UNLOCK_VAULT" not in registered
    assert "SERVICE_SET_ENCRYPTION" not in registered
    assert "SERVICE_CHANGE_VAULT_PASSWORD" not in registered
    services = (COMP / "services.yaml").read_text(encoding="utf-8")
    assert "unlock_vault:" not in services
    assert "set_encryption:" not in services
    assert "change_vault_password:" not in services


def test_csv_and_backup_processing_live_in_core_not_network_addon():
    assert (COMP / "csv_import.py").is_file()
    init = INIT_PATH.read_text(encoding="utf-8")
    assert 'route == "api/import/preview"' in init
    assert 'route == "api/backup"' in init
    assert 'route == "api/restore"' in init
    addon_files = {p.relative_to(ADDON).as_posix() for p in ADDON.rglob("*") if p.is_file()}
    assert "app/server.py" not in addon_files
    assert not any(path.startswith("app/static/") for path in addon_files)


def test_tor_addon_has_no_ingress_and_no_home_assistant_api_token():
    import yaml
    config = yaml.safe_load((ADDON / "config.yaml").read_text(encoding="utf-8"))
    assert "ingress" not in config
    assert "ingress_port" not in config
    assert "homeassistant_api" not in config
    agent = (ADDON / "app/network_agent.py").read_text(encoding="utf-8")
    assert "SUPERVISOR_TOKEN" not in agent
    assert "HA_TOKEN" not in agent
    assert "parse_transaction_upload" not in agent
    assert "portfolio_access\": False" in agent
    assert "homeassistant_api_token\": False" in agent


def test_network_agent_is_kernel_blocked_from_initiating_egress():
    run = RUN_PATH.read_text(encoding="utf-8")
    assert 'meta skuid ${APP_UID} counter reject comment "BST_AGENT_NO_EGRESS"' in run
    assert 'ct state established,related counter accept comment "BST_ESTABLISHED_REPLY"' in run
    assert 'meta skuid ${TOR_UID}' in run
    assert 'comment "BST_AGENT_NO_EGRESS"' in run


def test_tor_uses_socks_auth_isolation_without_control_socket():
    torrc = (ADDON / "torrc").read_text(encoding="utf-8")
    run = RUN_PATH.read_text(encoding="utf-8")
    network = (COMP / "network.py").read_text(encoding="utf-8")
    assert torrc.count("IsolateSOCKSAuth") == 4
    assert "ControlSocket /" not in torrc
    assert "ControlPort" not in torrc
    assert "CookieAuth" not in torrc
    assert "tor_control_halt" not in run
    assert "IsolateSOCKSAuth" in network
    assert "tor_isolation_token" in network


def test_tor_auto_rotation_has_real_core_timer():
    init = INIT_PATH.read_text(encoding="utf-8")
    assert "async def _async_rotate_tor_if_due" in init
    assert 'timedelta(minutes=1)' in init
    assert 'rotate_tor_isolation(hass)' in init
    assert '"last_rotated_at"' in init


def test_frontend_security_ui_explains_96_bit_value_is_nonce_not_key():
    app = APP_PATH.read_text(encoding="utf-8")
    assert 'cryptoNonceNote:"GCM-IV/Nonce (kein Schlüssel)"' in app
    assert 'Envelope v3 · DEK ${crypto.data_key_bits||256} bit' in app
    assert 'cryptoDeviceBound:"256-Bit separater Core-Geräteschlüssel"' in app
    assert "AES-256-GCM · ARGON2ID · ENVELOPE V3" in INDEX_PATH.read_text(encoding="utf-8")


def test_auto_lock_can_be_disabled_and_single_delete_has_custom_modal():
    app = APP_PATH.read_text(encoding="utf-8")
    index = INDEX_PATH.read_text(encoding="utf-8")
    assert '[0,5,15,30,60,120]' in app
    assert '<option value="0" data-i18n="disabled">' in index
    assert 'id="deleteEntryModal"' in index
    assert "openDeleteEntryDialog(button.dataset.id)" in app


def test_addon_base_and_python_dependencies_are_pinned():
    manifest = json.loads((COMP / "manifest.json").read_text(encoding="utf-8"))
    assert "argon2-cffi==25.1.0" in manifest["requirements"]
    assert "aiohttp-socks==0.11.0" in manifest["requirements"]
    docker = (ADDON / "Dockerfile").read_text(encoding="utf-8")
    assert "3.22-2026.06.1@sha256:368b5fcd266d1e5a643bad9bc9e84760760032e911ecfdef2a7fc148d76035d1" in docker
    assert "3.22-2026.06.1@sha256:03185a346a3e505e0aa102cb1e976a2e7be7421cf4a405abd2cd83e0a6bd0a58" in docker
    assert "FROM base-${BUILD_ARCH}" in docker
    assert "base:latest" not in docker


def test_cyclonedx_sboms_are_v17_and_current_release():
    release = json.loads((ROOT / "SBOM.cdx.json").read_text(encoding="utf-8"))
    source = json.loads((ADDON / "SBOM.source.cdx.json").read_text(encoding="utf-8"))
    for bom in (release, source):
        assert bom["bomFormat"] == "CycloneDX"
        assert bom["specVersion"] == "1.7"
    assert release["metadata"]["component"]["version"] == "0.21.0.11"
    assert source["metadata"]["component"]["version"] == "0.21.0.3"
    gateway = next(component for component in release["components"] if component["name"] == "bitcoin-stack-tracker-tor-gateway")
    assert gateway["version"] == "0.21.0.3"
    release_names = {component["name"] for component in release["components"]}
    assert {"argon2-cffi", "aiohttp-socks", "bitcoin-stack-tracker-tor-gateway"} <= release_names
    source_names = {component["name"] for component in source["components"]}
    assert "bitcoin-stack-tracker-tor-gateway" in source_names
    assert "argon2-cffi" not in source_names
    generator = (ADDON / "generate_runtime_sbom.py").read_text(encoding="utf-8")
    assert '"apk", "info", "-v"' in generator
    assert "pip\", \"list" not in generator


def test_core_side_auto_lock_survives_browser_close_and_can_be_disabled():
    init = INIT_PATH.read_text(encoding="utf-8")
    security = (COMP / "security.py").read_text(encoding="utf-8")
    app = APP_PATH.read_text(encoding="utf-8")
    assert "async def _async_expire_vault_sessions" in init
    assert 'timedelta(seconds=30)' in init
    assert 'route == "api/security/session"' in init
    assert "configure_user_auto_lock" in security
    assert "expire_unlock_sessions" in security
    assert "{0, 5, 15, 30, 60, 120}" in security
    assert "await storage.async_lock()" in init
    assert 'api("api/security/session"' in app


def test_legacy_http_ui_surfaces_are_removed_not_just_unregistered():
    init = INIT_PATH.read_text(encoding="utf-8")
    for class_name in (
        "BitcoinStackActionView",
        "BitcoinStackVaultUnlockView",
        "BitcoinStackVaultEnableView",
        "BitcoinStackVaultDisableView",
        "BitcoinStackVaultChangePasswordView",
        "BitcoinStackNetworkInventoryView",
        "BitcoinStackExportView",
        "BitcoinStackBackupView",
        "BitcoinStackRestoreView",
    ):
        assert f"class {class_name}" not in init
    assert init.count("class BitcoinStackNativePanelRpcView") == 1
    assert init.count("hass.http.register_view(") == 1


def test_native_frontend_has_strict_csp_and_no_direct_dashboard_fetch_fallback():
    index = INDEX_PATH.read_text(encoding="utf-8")
    app = APP_PATH.read_text(encoding="utf-8")
    assert 'Content-Security-Policy' in index
    assert "connect-src 'none'" in index
    assert "object-src 'none'" in index
    assert "base-uri 'none'" in index
    assert "frame-ancestors 'self'" in index
    assert "fetch(dashboardUrl" not in app
    assert "Bitcoin Stack Tracker muss über das native Home-Assistant-Seitenleistenpanel geöffnet werden" in app
    # Legacy passwords stay migratable; only new secrets are forced to 16+ chars.
    assert 'id="unlockForm"' in index and 'name="password" type="password" minlength="1"' in index
    assert 'name="new_password" type="password" minlength="16"' in index


def test_v031_native_panel_registration_is_idempotent_and_retried_from_entry_setup():
    panel = PANEL_PATH.read_text(encoding="utf-8")
    init = INIT_PATH.read_text(encoding="utf-8")
    assert "frontend.async_panel_exists" in panel
    assert "frontend.async_remove_panel" in panel
    assert "_native_static_registered" in panel
    assert "except RuntimeError" in panel
    assert "return False" in panel
    setup_entry = init[init.index("async def async_setup_entry"):]
    assert "await async_register_native_panel(hass)" in setup_entry[:1200]


def test_v031_gateway_health_agent_is_stdlib_only_and_direct_python_script():
    agent = (ADDON / "app/network_agent.py").read_text(encoding="utf-8")
    docker = (ADDON / "Dockerfile").read_text(encoding="utf-8")
    assert agent.startswith("#!/usr/bin/python3")
    assert "from http.server import BaseHTTPRequestHandler, HTTPServer" in agent
    assert "from aiohttp" not in agent
    assert "py3-aiohttp" not in docker
    assert 'APP_VERSION = "0.21.0.3"' in agent
