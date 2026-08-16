from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"


def test_receive_and_change_counts_are_gap_limits_not_total_counts():
    backend = (COMP / "wallet_watch.py").read_text(encoding="utf-8")
    assert "counts.  Discovery is independent for receive (/0) and change (/1)." in backend
    assert "consecutive_unused = 0 if used else consecutive_unused + 1" in backend
    assert "if consecutive_unused >= gap_limit:" in backend
    assert '(0, "receive", int(monitor.get("receive_count") or 0))' in backend
    assert '(1, "change", int(monitor.get("change_count") or 0))' in backend


def test_gap_discovery_keeps_all_used_addresses_and_standby_without_runtime_xpub():
    backend = (COMP / "wallet_watch.py").read_text(encoding="utf-8")
    assert "GAP_STANDBY_ADDRESSES_PER_BRANCH = 20" in backend
    assert "active=False, used=None" in backend
    assert '"xpub_in_runtime": False' in backend
    assert '"descriptor_in_runtime": False' in backend
    assert "Unlock the vault once to replenish pre-derived addresses." in backend


def test_gap_limit_ui_names_receive_and_change_explicitly():
    html = (COMP / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (COMP / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    assert "Receive Gap-Limit" in html
    assert "Change Gap-Limit" in html
    assert "Alle benutzten Receive-Adressen bleiben überwacht" in html
    assert "Alle benutzten Change-Adressen bleiben überwacht" in html
    assert "Receive Gap ${mon.receive_count||0} · Change Gap ${mon.change_count||0}" in app
    assert "receive_addresses:receive.length" in app
    assert "change_addresses:change.length" in app


def test_public_address_count_excludes_inactive_standby_pool():
    backend = (COMP / "wallet_watch.py").read_text(encoding="utf-8")
    start = backend.index("def public_status")
    end = backend.index("async def _request_text", start)
    block = backend[start:end]
    assert 'bool(row.get("active", True))' in block
    assert '"address_count": len(addresses)' in block


def test_lightweight_status_keeps_privacy_safe_per_monitor_balance_and_counts():
    backend = (COMP / "wallet_watch.py").read_text(encoding="utf-8")
    app = (COMP / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    start = backend.index("def public_status")
    end = backend.index("async def _request_text", start)
    block = backend[start:end]
    assert '"monitor_summaries": monitor_summaries' in block
    assert '"balance_sats": 0' in block
    assert 'summary["balance_sats"] += int(row.get("balance_sats") or 0)' in block
    assert 'summary["utxo_count"] += int(row.get("utxo_count") or 0)' in block
    assert 'summary["receive_address_count"] += 1' in block
    assert 'summary["change_address_count"] += 1' in block
    assert 'aggregate=st.monitor_summaries?.[id]' in app
    assert 'overviewBalance===null?Number(aggregate.balance_sats||0):overviewBalance' in app
    assert 'receive_addresses:Number(aggregate.receive_address_count||0)' in app
    assert 'change_addresses:Number(aggregate.change_address_count||0)' in app


def test_full_config_activation_rebuilds_gap_coverage_before_status():
    backend = (COMP / "wallet_watch.py").read_text(encoding="utf-8")
    start = backend.index("async def async_apply_full_config")
    end = backend.index("async def async_upsert_monitor", start)
    block = backend[start:end]
    assert "await self._discover_gap_addresses(normalized, source)" in block
    assert "if poll:" in block
    assert "await self.async_poll(force=True)" in block


def test_transaction_overview_uses_only_active_gap_discovered_addresses():
    backend = (COMP / "wallet_watch.py").read_text(encoding="utf-8")
    start = backend.index("async def async_monitor_transactions")
    end = backend.index("async def", start + len("async def async_monitor_transactions"))
    block = backend[start:end]
    assert 'and bool(row.get("active", True))' in block


def test_watch_card_balance_reuses_current_wallet_balance_from_tx_overview():
    app = (COMP / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'overview=walletWatchTxOverviewState(id)?.data||null' in app
    assert 'overviewBalance=overview&&Number.isFinite(Number(overview.balance_sats))?Number(overview.balance_sats):null' in app
    assert 'balance_sats:overviewBalance===null?Number(aggregate.balance_sats||0):overviewBalance' in app
    assert 'state.walletWatch.status.monitor_summaries[id].balance_sats=Number(result.balance_sats||0)' in app
    assert 'renderWalletWatch();}catch(error)' in app
