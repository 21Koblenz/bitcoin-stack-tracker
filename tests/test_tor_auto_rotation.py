from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
INIT = (COMP / "__init__.py").read_text(encoding="utf-8")
APP = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")
INDEX = (COMP / "frontend/index.html").read_text(encoding="utf-8")


def test_rotation_intervals_match_frontend_options():
    assert "_TOR_ROTATION_INTERVALS = {10, 15, 30, 60, 120, 180, 360, 720, 1440}" in INIT
    for value in (10, 30, 60, 180, 360, 720, 1440):
        assert f'<option value="{value}">' in INDEX


def test_rotation_has_entry_local_watchdog_and_unload_cleanup():
    assert "_TOR_ROTATION_ENTRY_CHECK = timedelta(seconds=30)" in INIT
    setup = INIT.split("async def async_setup_entry", 1)[1].split("async def async_remove_entry", 1)[0]
    assert 'runtime["cancel_tor_rotation"] = async_track_time_interval' in setup
    assert 'trigger="entry-timer"' in setup
    assert 'trigger="entry-setup"' in setup
    unload = INIT.split("async def async_unload_entry", 1)[1]
    assert 'runtime.get("cancel_tor_rotation")' in unload


def test_panel_poll_is_a_self_healing_rotation_watchdog():
    network_route = INIT.split('if route == "api/network-status"', 1)[1].split('if route == "api/history/intraday"', 1)[0]
    assert 'trigger="network-poll"' in network_route
    settings_route = INIT.split('if route == "api/tor/rotation-settings"', 1)[1].split('if route == "api/tor/new-identity"', 1)[0]
    assert 'trigger="settings-poll"' in settings_route
    assert 'trigger="settings-save"' in settings_route
    assert "_tor_rotation_settings_view(settings)" in settings_route


def test_network_poll_sends_entry_id_and_refreshes_last_rotation_immediately():
    assert 'api/network-status?entry_id=${encodeURIComponent(state.entryId)}' in APP
    assert 'api/network-status?force=1&entry_id=${encodeURIComponent(state.entryId)}' in APP
    assert "state.network?.tor_last_rotated_at" in APP
    assert "last_rotated_at:state.network.tor_last_rotated_at" in APP


def test_rotation_is_locked_persisted_and_diagnostic():
    helper = INIT.split("async def _async_rotate_tor_if_due", 1)[1].split("async def _async_expire_vault_sessions", 1)[0]
    assert 'domain_data.get("_tor_rotation_lock")' in helper
    assert "async with lock:" in helper
    assert 'item["last_rotated_at"] = rotated_at' in helper
    assert 'item["next_rotation_at"]' in helper
    assert "await _save_panel_state(hass, state)" in helper
    assert "tor_auto_rotation status=rotated" in helper
