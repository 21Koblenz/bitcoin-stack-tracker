from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "custom_components" / "bitcoin_stack_tracker" / "frontend" / "static" / "app.js").read_text(encoding="utf-8")


def test_locked_sentinel_privacy_is_reapplied_on_all_auto_lock_paths():
    assert "function hideLockedWalletWatch(){" in APP
    assert "if(!enabled){hideLockedWalletWatch();return;}" in APP
    assert "if(!walletWatchShowWhenLocked())hideLockedWalletWatch();" in APP
    assert 'document.addEventListener("visibilitychange"' in APP
    assert "void loadData().then" in APP
    assert "state.data?.locked&&!walletWatchShowWhenLocked()" in APP


def test_reconstruction_status_uses_backend_source_interval_and_route():
    assert "Bitstamp 5m · Tor only" not in APP
    assert "s.interval_minutes||15" in APP
    assert "s.source||walletWatchLang" in APP
    assert 's.network_route||"Tor only"' in APP
