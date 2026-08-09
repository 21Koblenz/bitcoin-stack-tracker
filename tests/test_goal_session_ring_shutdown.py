from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
INIT = (COMP / "__init__.py").read_text(encoding="utf-8")
APP = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")
APPARMOR = (ROOT / "bitcoin_stack_tracker_dashboard" / "apparmor.txt").read_text(encoding="utf-8")
RUN = (ROOT / "bitcoin_stack_tracker_dashboard" / "run.sh").read_text(encoding="utf-8")


def test_goal_writes_do_not_reload_password_protected_vault():
    helper = INIT.split("async def _refresh_structure_after_write", 1)[1].split("def _host_label", 1)[0]
    assert "security.encryption_mode == ENCRYPTION_PASSWORD" in helper
    assert "_notify_entities(runtime)" in helper
    assert "await hass.config_entries.async_reload(entry_id)" in helper
    for name, next_name in [("add_goal", "update_goal"), ("update_goal", "delete_goal")]:
        block = INIT.split(f"async def {name}(call", 1)[1].split(f"async def {next_name}(call", 1)[0]
        assert "_refresh_structure_after_write" in block
        assert "async_reload" not in block


def test_partial_goal_ring_uses_direct_dash_length_not_offset_math():
    block = APP.split("function renderGoalCards()", 1)[1].split("function firstPortfolioActivityDay()", 1)[0]
    assert 'stroke-dasharray="${ringDash} ${ringGap}"' in block
    assert 'stroke-dashoffset="${Math.max(0,100-ringProgress)}"' not in block
    assert '${ringProgress > 0 ? `<circle class="goal-ring-progress"' in block
    assert "const ringCircumference = 2 * Math.PI * 50;" in block
    assert "const ringDash = ringCircumference * ringProgress / 100;" in block


def test_gateway_can_signal_cross_uid_tor_and_reports_signal_failure():
    assert "capability kill," in APPARMOR
    helper = RUN.split("signal_pid_checked() {", 1)[1].split("child_pids() {", 1)[0]
    assert 'kill "-${signal_name}" "${pid}"' in helper
    assert "Could not send ${signal_name}" in helper
    tor = RUN.split("stop_tor() {", 1)[1].split("request_shutdown() {", 1)[0]
    assert 'signal_pid_checked "${tor_pid}" TERM "Tor"' in tor
    assert 'signal_pid_checked "${tor_pid}" KILL "Tor"' in tor
