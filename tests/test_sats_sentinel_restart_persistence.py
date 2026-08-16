from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"


def test_normal_unload_never_deletes_sentinel_runtime_store():
    init_py = (COMP / "__init__.py").read_text(encoding="utf-8")
    unload_start = init_py.index("async def async_unload_entry")
    unload = init_py[unload_start:]
    assert "runtime_store.async_remove()" not in unload
    remove_start = init_py.index("async def async_remove_entry")
    remove_end = init_py.index("async def async_unload_entry", remove_start)
    remove = init_py[remove_start:remove_end]
    assert "runtime_store.async_remove()" in remove


def test_successful_vault_unlock_rehydrates_sentinel_from_encrypted_config():
    init_py = (COMP / "__init__.py").read_text(encoding="utf-8")
    start = init_py.index("async def _async_unlock_for_requester")
    end = init_py.index("_HISTORY_AUTO_CHECK_INTERVAL", start)
    block = init_py[start:end]
    assert "watch_config = normalize_watch_config(storage.wallet_watch_config)" in block
    assert "watch_manager.async_apply_full_config(watch_config, poll=False)" in block
    assert "hass.async_create_task(" in block
    assert "recovery must never break vault unlock" in block


def test_frontend_reload_after_unlock_and_dirty_source_saved_before_monitor():
    app = (COMP / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    unlock = app[app.index('$("#unlockForm").onsubmit'):app.index('$("#lockButton")', app.index('$("#unlockForm").onsubmit'))]
    assert "await loadData()" in unlock
    assert "await loadWalletWatch()" in unlock

    start = app.index("async function addWalletWatchMonitor(event)")
    end = app.index("function addWalletWatchNotificationTarget", start)
    block = app[start:end]
    assert "if(state.walletWatchSettingsDirty)" in block
    assert "const settingsDraft=walletWatchDraftConfig()" in block
    global_save = block.index('api("api/wallet-watch"')
    monitor_save = block.index('api("api/wallet-watch/upsert-monitor"')
    assert global_save < monitor_save
    assert "state.walletWatchSettingsDirty=false" in block


def test_runtime_cache_contains_endpoint_and_addresses_but_not_raw_xpub():
    backend = (COMP / "wallet_watch.py").read_text(encoding="utf-8")
    start = backend.index("def runtime_cache_from_config")
    end = backend.index("class WalletWatchRuntimeStore", start)
    block = backend[start:end]
    assert '"electrum_host": str(config.get("electrum_host") or "")' in block
    assert '"electrum_port": int(config.get("electrum_port") or 50001)' in block
    assert '"addresses": addresses' in block
    assert '"monitors":' not in block
