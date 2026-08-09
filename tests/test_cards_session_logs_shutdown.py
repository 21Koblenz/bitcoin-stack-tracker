from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
APP = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")
INIT = (COMP / "__init__.py").read_text(encoding="utf-8")
HISTORY = (COMP / "history.py").read_text(encoding="utf-8")
RUN = (ROOT / "bitcoin_stack_tracker_dashboard" / "run.sh").read_text(encoding="utf-8")


def test_open_basis_and_fiat_secured_explain_fee_semantics():
    assert "result.totalOutlay = result.fiat + result.fees" in APP
    assert 'purchaseFees:"Kaufgebühren"' in APP
    assert 'openBasisHint:"Nur noch offene FIFO-Lots · Kaufgebühren anteilig enthalten"' in APP
    assert 'fmtFiat(secured.fees,currency)' in APP
    assert 'fmtFiat(secured.totalOutlay,currency)' in APP


def test_auto_lock_select_updates_before_global_activity_listener_can_reset_it():
    assert '$("#autoLockMinutes").oninput=event=>' in APP
    assert 'state.autoLockMinutes=value;' in APP
    assert 'void syncCoreAutoLock({touch:true,silent:false});' in APP
    schedule = APP.split("function scheduleAutoLock()", 1)[1].split("async function syncCoreAutoLock", 1)[0]
    assert "renderAutoLock();" not in schedule
    assert "const confirmed=Number(result?.auto_lock_minutes);" in APP


def test_native_panel_has_bounded_non_secret_technical_log_again():
    assert "_TECHNICAL_LOG_MAX_ENTRIES = 500" in INIT
    assert "def _technical_log_append" in INIT
    assert "route={route or '-'} method={method} status=200 duration_ms=" in INIT
    assert 'service={_service} status=completed duration_ms=' in INIT
    assert 'service={_service} status=failed duration_ms=' in INIT
    assert 'if route == "api/logs" and method == "GET"' in INIT
    assert 'rows = list(_technical_log_buffer(self.hass))' in INIT


def test_shutdown_uses_final_managed_process_cleanup_before_retaining_killswitch():
    cleanup = RUN.split("cleanup()", 1)[1].split("trap request_shutdown", 1)[0]
    assert "terminate_remaining_managed_processes" in cleanup
    assert 'if [[ -z "${remaining_managed}" ]]' in cleanup
    assert "nft delete table" in cleanup
    assert "Managed process still visible after fast final cleanup" in RUN


def test_history_strategy_forces_one_new_full_backfill_and_drops_stale_exclusive_labels():
    assert 'HISTORY_STRATEGY_VERSION = "ordered-source-cascade-v8-fx-fill"' in HISTORY
    assert 'metadata.pop(stale_key, None)' in HISTORY
    assert '"exclusive_source", "history_strategy"' in HISTORY
    assert "function historySourceSummary(item={})" in APP
    assert 'label.toLowerCase()==="own mempool instance only"' in APP
