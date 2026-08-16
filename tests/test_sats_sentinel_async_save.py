from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"


def test_monitor_save_persists_before_background_gap_discovery():
    backend = (COMP / "wallet_watch.py").read_text(encoding="utf-8")
    start = backend.index("async def async_upsert_monitor")
    end = backend.index("async def async_remove_monitor", start)
    block = backend[start:end]
    assert "self.cancel_background_refresh()" in block
    assert "await self.ledger_store.async_set_wallet_watch_config(new_config)" in block
    assert "await self.runtime_store.async_replace_from_full_config(new_config)" in block
    assert "self.schedule_background_refresh(" in block
    assert "await self._discover_gap_addresses" not in block
    assert "await self.async_poll(force=True)" not in block


def test_full_settings_post_does_not_wait_for_fulcrum_gap_scan():
    init_py = (COMP / "__init__.py").read_text(encoding="utf-8")
    marker = 'if route == "api/wallet-watch" and method == "POST":'
    start = init_py.index(marker)
    end = init_py.index('if route == "api/wallet-watch/source-test"', start)
    block = init_py[start:end]
    assert 'runtime["wallet_watch"].cancel_background_refresh()' in block
    assert 'await runtime["storage"].async_set_wallet_watch_config(config)' in block
    assert 'await runtime["wallet_watch"].runtime_store.async_replace_from_full_config(config)' in block
    assert 'runtime["wallet_watch"].schedule_background_refresh(config, poll=True)' in block
    assert 'await runtime["wallet_watch"].async_apply_full_config' not in block


def test_background_scan_state_is_exposed_without_addresses():
    backend = (COMP / "wallet_watch.py").read_text(encoding="utf-8")
    start = backend.index("def public_status")
    end = backend.index("async def _request_text", start)
    block = backend[start:end]
    assert '"scan_in_progress": bool(' in block
    assert 'self._refresh_task is not None and not self._refresh_task.done()' in block


def test_frontend_monitor_save_uses_short_persistence_timeout_and_background_message():
    app = (COMP / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    start = app.index("async function addWalletWatchMonitor(event)")
    end = app.index("function addWalletWatchNotificationTarget", start)
    block = app[start:end]
    assert 'api("api/wallet-watch/upsert-monitor"' in block
    assert 'timeoutMs:30000' in block
    assert 'Adressscan läuft im Hintergrund' in block
    assert 'Address scan is running in the background' in block


def test_newer_save_cancels_stale_background_discovery():
    backend = (COMP / "wallet_watch.py").read_text(encoding="utf-8")
    assert "def cancel_background_refresh" in backend
    schedule_start = backend.index("def schedule_background_refresh")
    schedule_end = backend.index("async def _timer", schedule_start)
    schedule = backend[schedule_start:schedule_end]
    assert "self.cancel_background_refresh()" in schedule
    assert "async with self._lock:" in schedule
    assert "await self._discover_gap_addresses" in schedule
    assert "await self.async_poll(force=True)" in schedule
