from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "bitcoin_stack_tracker"


def test_sats_sentinel_branding_and_internal_compatibility():
    html = (COMPONENT / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    init_py = (COMPONENT / "__init__.py").read_text(encoding="utf-8")

    assert "Sats Sentinel" in html
    assert "Wallet Watch" not in html
    assert "Sats Sentinel" in app
    assert "Wallet Watch" not in app
    assert "Sats Sentinel" in backend
    assert '"User-Agent": "Bitcoin-Stack-Tracker/0.21.0.10"' in backend

    # Internal route/event/storage names intentionally stay stable.
    assert 'route == "api/wallet-watch"' in init_py
    assert 'WATCH_EVENT = "bitcoin_stack_tracker_wallet_activity"' in backend
    assert 'WATCH_STORAGE_KEY = "bitcoin_stack_tracker.wallet_watch_runtime"' in backend


def test_sats_sentinel_multi_channel_surface_is_present():
    html = (COMPONENT / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")

    assert "Mehrere Ziele können parallel verwendet werden" in html
    assert '<option value="ntfy">ntfy</option>' in html
    assert '<option value="webhook">Webhook</option>' in html
    assert "Diskret · keine Walletdaten" in html
    assert "walletWatchNotifyServices" in html
    assert "walletWatchNotificationTargets" in html
    assert "notification_targets" in app
    assert "asyncio.gather" in backend
    assert "one target cannot block the others" in backend
    assert 'kind == "ntfy"' in backend
    assert 'kind == "webhook"' in backend


def test_discreet_external_payload_does_not_include_wallet_fields():
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    start = backend.index('if mode == "discreet":')
    end = backend.index("amount = (", start)
    discreet = backend[start:end]

    assert '"🛡️ Sats Sentinel"' in discreet
    assert '"Bitcoin-Bewegung erkannt. Öffne Bitcoin Stack Tracker für Details."' in discreet
    assert '{"event": "wallet_activity"}' in discreet
    return_block = discreet[discreet.index("return ("):]
    for forbidden in ("amount_sats", "txid", "monitor_id", "direction\":", "confirmed\":", "address"):
        assert forbidden not in return_block


def test_runtime_cache_is_based_on_concrete_addresses_not_watch_keys():
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    start = backend.index("def runtime_cache_from_config")
    end = backend.index("class WalletWatchRuntimeStore", start)
    cache_code = backend[start:end]

    assert '"address": row["address"]' in cache_code
    assert '"notification_targets": deepcopy' in cache_code
    # xpub/descriptor may appear in derivation branches, but not in the returned cache schema.
    returned = cache_code[cache_code.rindex("return {"):]
    assert '"xpub":' not in returned
    assert '"descriptor":' not in returned
    assert '"value":' not in returned


def test_sats_sentinel_simulation_uses_real_alert_path_without_state_mutation_surface():
    html = (COMPONENT / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    init_py = (COMPONENT / "__init__.py").read_text(encoding="utf-8")

    assert "TESTLABOR · KEINE BLOCKCHAIN-ÄNDERUNG" in html
    assert "walletWatchSimulateForm" in html
    assert 'api/wallet-watch/simulate' in app
    assert 'route == "api/wallet-watch/simulate"' in init_py
    assert "async def async_simulate_activity" in backend
    start = backend.index("async def async_simulate_activity")
    end = backend.index("async def async_test_notifications", start)
    block = backend[start:end]
    assert "await self._notify_activity(row, event)" in block
    assert '"simulated": True' in block
    assert "async_save" not in block


def test_market_assessment_public_indicators_ignore_discreet_mode():
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    start = app.index("function renderBuyOpportunity()")
    end = app.index("function buyOpportunitySettingsDefaults", start)
    block = app[start:end]
    assert 'indicatorsEl.innerHTML=indicatorRows.map(([label,value])=>`<div><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`' in block
    assert 'indicatorsEl.innerHTML=indicatorRows.map(([label,value])=>`<div><span>${esc(label)}</span><strong>${privateHtml(value)}</strong></div>`' not in block


def test_sats_sentinel_status_cards_have_spacious_card_layout():
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    css = (COMPONENT / "frontend" / "static" / "style.css").read_text(encoding="utf-8")
    html = (COMPONENT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'class="sats-sentinel-card"' in app
    assert ".sats-sentinel-card-grid" in css
    assert ".sats-sentinel-card-hint" in css
    assert 'id="walletWatchError"' in html
    assert ".sats-sentinel-alert" in css


def test_sats_sentinel_live_mempool_test_is_tor_policy_bound_and_non_persistent():
    html = (COMPONENT / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    init_py = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
    assert "LIVE MEMPOOL TEST · TOR-REGELN GELTEN" in html
    assert 'api/wallet-watch/live-test' in app
    assert 'route == "api/wallet-watch/live-test"' in init_py
    start = backend.index("async def async_live_test_transaction")
    end = backend.index("async def async_test_notifications", start)
    block = backend[start:end]
    assert "_mempool_sources(self.entry" in block
    assert 'self._request_json(source, f"/api/tx/{txid}")' in block
    assert "await self._notify_activity(row, event)" in block
    assert "async_save" not in block


def test_sats_sentinel_sensitive_runtime_values_still_mask_in_discreet_mode():
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'walletWatchCard("UTXOs",state.discreet?"••••"' in app
    assert 'state.discreet?"••••":(mon.label||mon.id)' in app
    assert 'else if (state.activeTab === "walletwatch") renderWalletWatch();' in app


def test_sats_sentinel_own_mempool_is_strictly_exclusive():
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    start = backend.index("def _mempool_sources")
    end = backend.index("def _summary_signature", start)
    block = backend[start:end]
    assert "source[CONF_MEMPOOL_OWN_INSTANCE] = True" in block
    assert "automatic_mempool_route(" in block
    assert "return [source]" in block
    assert "if allow_public_tor:" in block
    assert block.index("return [source]") < block.index("if allow_public_tor:")
    assert "own/custom ``.onion`` node is contacted through Tor" in block
    assert "no implicit mempool.space/provider fallback" in block


def test_sats_sentinel_status_documents_explicit_source_fail_closed():
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    assert "explicit source is fail-closed" in backend
    assert "never by runtime health" in backend
    assert "no runtime provider fallback" in backend


def test_sats_sentinel_normalizes_local_mempool_api_suffixes_without_fallback():
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    assert "def _canonical_mempool_base_url" in backend
    assert '"/api/v1/prices", "/api/v1", "/api"' in backend
    assert "source[CONF_BASE_URL] = base" in backend
    assert "automatic_mempool_route(" in backend


def test_selected_chart_range_forces_recent_tail_reload():
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    assert "async function reloadSelectedChartRange()" in app
    block = app[app.index("async function reloadSelectedChartRange()"):app.index('if($("#refreshChartPrices"))')]
    assert 'await ensureDashboardSection("chart")' in block
    assert 'await refreshLivePrice({silent:true})' in block
    assert 'await ensureIntradayHistory({force:true,interactive:false})' in block
    assert 'await reloadSelectedChartRange();' in app


def test_sats_sentinel_failed_address_probe_stays_on_same_node_and_exposes_diagnostic():
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'await self._request_json(source_used, "/api/v1/prices")' in backend
    assert 'mempool is reachable, but its address API failed' in backend
    assert 'const isOffline=Boolean(st.last_error)' in app
    assert 'Teilprüfung · Node online' in app


def test_sats_sentinel_same_node_address_api_path_compatibility_has_no_provider_fallback():
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    assert '"/api/address", "/api/v1/address"' in backend
    assert 'getattr(err, "status", None) == 404' in backend
    assert 'self._address_api_prefix_by_base[base] = prefix' in backend
    start = backend.index("async def _address_api_json")
    end = backend.index("async def _address_snapshot", start)
    block = backend[start:end]
    assert "_request_json(source" in block
    assert "DEFAULT_MEMPOOL_URL" not in block
    assert "_mempool_sources" not in block


def test_every_chart_range_selection_refreshes_its_source_tail():
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    start = app.index("async function reloadSelectedChartRange()")
    end = app.index('if($("#refreshChartPrices"))', start)
    block = app[start:end]
    assert 'await ensureIntradayHistory({force:true,interactive:false})' in block
    assert 'service("sync_history",{config_entry_id:state.entryId}' in block
    assert 'await refreshLivePrice({silent:true})' in block
    assert 'await reloadSelectedChartRange();' in app


def test_sats_sentinel_does_not_require_address_utxo_endpoint():
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    start = backend.index("async def _address_snapshot")
    end = backend.index("def _notification_text", start)
    block = backend[start:end]
    assert '"/txs"' in block
    assert '"/utxo"' not in block
    assert "_utxo_count_from_summary(summary)" in block
    assert 'funded_txo_count' in backend
    assert 'spent_txo_count' in backend


def test_sats_sentinel_runtime_cache_does_not_store_full_utxo_set():
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    start = backend.index("def runtime_cache_from_config")
    end = backend.index("class WalletWatchRuntimeStore", start)
    block = backend[start:end]
    assert '"utxo_count": 0' in block
    returned = block[block.rindex("return {"):]
    assert '"utxos":' not in returned


def test_sats_sentinel_uses_only_configured_public_mempool_when_no_own_node():
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    start = backend.index("def _configured_public_mempool_sources")
    end = backend.index("def _summary_signature", start)
    block = backend[start:end]
    assert "DEFAULT_MEMPOOL_URL" not in block
    assert "public_sources = _configured_public_mempool_sources(entry)" in block
    assert "return [public_sources[0]]" in block
    assert "Do not leak watched addresses to a cascade of providers" in block
    assert "source[CONF_MEMPOOL_ROUTE] = MEMPOOL_ROUTE_TOR" in block


def test_sats_sentinel_own_onion_node_is_exclusive_and_tor_routed():
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    network = (COMPONENT / "network.py").read_text(encoding="utf-8")
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    assert "own/custom ``.onion`` node is contacted through Tor and remains exclusive" in backend
    assert "automatic_mempool_route(" in backend
    assert 'host.endswith(".onion")' in network
    assert "ProxyConnector.from_url(isolated_proxy, rdns=True)" in network
    assert 'selected_source_route==="tor"' in app
    assert "hidden provider switch" in app


def test_sats_sentinel_public_tor_requires_explicit_configured_source():
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    html = (COMPONENT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'value="mempool_public"' in html
    assert "Konfigurierte öffentliche Mempool-Quelle über Tor nutzen" in html
    assert "Explizite Auswahl = Fail Closed" in html
    assert 'cfg.allow_public_tor' in app


def test_sats_sentinel_ui_status_refreshes_without_extra_blockchain_poll():
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    init_py = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
    assert 'api/wallet-watch/status?entry_id=' in app
    assert '},15000);' in app
    assert 'state.activeTab!=="walletwatch"' in app
    assert 'route == "api/wallet-watch/status"' in init_py
    assert 'public_status(include_addresses=False)' in init_py


def test_sats_sentinel_activity_journal_is_logged_before_alert_filtering():
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    assert '"activity_log": []' in backend
    assert 'async def _append_activity_log' in backend
    poll = backend[backend.index('async def async_poll'):]
    assert poll.index('await self._append_activity_log(row, event)') < poll.index('await self._notify_activity(row, event)')
    notify = backend[backend.index('async def _notify_activity'):backend.index('async def _notify_outage')]
    assert 'min_notify_sats' in notify
    assert 'return' in notify


def test_sats_sentinel_journal_display_filter_does_not_delete_history():
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    block = backend[backend.index('def public_activity_log'):backend.index('def _notification_text')]
    assert 'LOG_PAGE_SIZE = 25' in backend
    assert '"stored_total": len(self.runtime_store.data.get("activity_log", []) or [])' in block
    assert 'self.runtime_store.data["activity_log"] =' not in block
    assert 'mode == "count"' in block
    assert 'mode == "days"' in block


def test_sats_sentinel_watch_entries_are_editable_categorized_and_channel_specific():
    html = (COMPONENT / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    for token in ('Eigene Adresse / Wallet', 'Exchange', 'Hacker / Incident', 'Mindestbetrag für Alarm', 'HA-Event auslösen', 'Ausgewählte Handy-Pushs'):
        assert token in html
    assert 'function editWalletWatchMonitor' in app
    assert 'wallet-watch-edit' in app
    for key in ('"category": category', '"min_notify_sats": min_notify_sats', '"notify_ha_event"', '"notify_persistent"', '"notify_services"', '"notify_external"'):
        assert key in backend


def test_sats_sentinel_activity_journal_has_category_filter_and_25_item_paging():
    html = (COMPONENT / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    init_py = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
    assert 'id="walletWatchActivityCategory"' in html
    assert 'id="walletWatchActivityPagination"' in html
    assert 'api/wallet-watch/log?entry_id=' in app
    assert 'route == "api/wallet-watch/log"' in init_py


def test_sats_sentinel_partial_tx_timeout_does_not_mark_node_offline():
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'TX_REQUEST_TIMEOUT_SECONDS = 45' in backend
    assert 'partial_errors: list[str] = []' in backend
    assert 'partial_errors.append(f"Wallet {monitor_slot}: txs' in backend
    assert 'data["last_warning"]' in backend
    assert 'data["last_error"] = None' in backend
    assert '⚠ TEILWEISE' in app


def test_sats_sentinel_journal_has_direct_page_picker_and_counterparty_limit():
    html = (COMPONENT / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id="walletWatchActivityCounterparties"' in html
    assert 'Bis zu 12' in html
    assert 'id="walletWatchActivityPageSelect"' in app
    assert 'data-ww-page="1"' in app
    assert 'walletWatchCounterpartyLimit' in app


def test_sats_sentinel_monitor_rules_are_rendered_as_named_fields():
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    for token in ('Eingangs-Alarm', 'Ausgangs-Alarm', 'Alarmgrenze', 'Alarmkanäle'):
        assert token in app
    assert 'wallet-watch-monitor-meta' in app


def test_sats_sentinel_journal_page_size_is_selectable_and_capped_at_25():
    html = (COMPONENT / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    init_py = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
    assert 'id="walletWatchActivityPageSize"' in html
    for value in ('value="10"', 'value="15"', 'value="20"', 'value="25"'):
        assert value in html
    assert 'bst_wallet_watch_page_size' in app
    assert 'page_size=${encodeURIComponent(state.walletWatchActivityPageSize||10)}' in app
    assert 'safe_page_size = min(LOG_PAGE_SIZE, max(1, requested_page_size))' in backend
    assert 'page_size = min(25, max(1, int(q("page_size") or 10)))' in init_py


def test_sats_sentinel_txid_links_use_selected_mempool_explorer_base():
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    assert 'explorer_base_url' in backend
    assert '_explorer_mempool_source(self.entry, bool(config.get("allow_public_tor")))' in backend
    assert 'function walletWatchTxLink' in app
    assert '${base}/tx/${encodeURIComponent(txid)}' in app
    assert 'target="_blank" rel="noopener noreferrer"' in app


def test_sats_sentinel_journal_renders_sender_direction_recipient_with_explorer_links():
    html = (COMPONENT / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    assert '<th>Sender</th><th>Richtung</th><th>Empfänger</th>' in html
    assert 'function walletWatchWatchedPartyHtml' in app
    assert 'function walletWatchAddressLink' in app
    assert '${base}/address/${encodeURIComponent(raw)}' in app
    assert 'sender=outgoing?watched:other' in app
    assert 'recipient=outgoing?other:watched' in app
    assert '"watched_addresses"' in backend
    assert 'cp["monitor_label"]' in backend
    assert 'cp["category"]' in backend


def test_sats_sentinel_query_source_is_explicitly_selectable():
    html = (COMPONENT / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    for value in ("auto", "fulcrum", "electrs", "mempool_own", "mempool_public"):
        assert f'value="{value}"' in html
    assert 'id="walletWatchElectrumHost"' in html
    assert 'id="walletWatchElectrumPort"' in html
    assert 'cfg.query_source=' in app
    assert 'def _select_watch_source' in backend
    assert 'if mode in _ALLOWED_ELECTRUM_KINDS' in backend
    assert 'if mode == "mempool_own"' in backend
    assert 'if mode == "mempool_public"' in backend


def test_sats_sentinel_electrum_support_is_batched_and_tor_capable():
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    network = (COMPONENT / "network.py").read_text(encoding="utf-8")
    assert 'class _ElectrumRPCClient' in backend
    assert 'blockchain.scripthash.subscribe' in backend
    assert 'blockchain.scripthash.get_balance' in backend
    assert 'blockchain.scripthash.listunspent' in backend
    assert 'blockchain.scripthash.get_history' in backend
    assert 'blockchain.transaction.get' in backend
    assert 'async_tor_socks_connection_info' in network
    assert 'target hostname is' in network


def test_sats_sentinel_auto_selection_is_configuration_based_not_health_fallback():
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    block = backend[backend.index('def _select_watch_source'):backend.index('def _explorer_mempool_source')]
    assert 'never by runtime health' in block
    assert 'electrum = _electrum_source_from_config(config)' in block
    assert block.index('if electrum:') < block.index('if own:')
    assert block.index('if own:') < block.index('if bool(config.get("allow_public_tor")) and public:')


def test_sats_sentinel_status_refresh_does_not_rerender_settings_form():
    app = (ROOT / "custom_components/bitcoin_stack_tracker/frontend/static/app.js").read_text()
    marker = "async function refreshWalletWatchStatus"
    block = app[app.index(marker):app.index("function startWalletWatchStatusPolling", app.index(marker))]
    assert "renderWalletWatchStatusOnly()" in block
    assert "renderWalletWatch();" not in block


def test_sats_sentinel_save_has_immediate_feedback_and_source_probe():
    app = (ROOT / "custom_components/bitcoin_stack_tracker/frontend/static/app.js").read_text()
    html = (ROOT / "custom_components/bitcoin_stack_tracker/frontend/index.html").read_text()
    assert 'id="walletWatchSaveButton"' in html
    assert 'id="walletWatchSourceTest"' in html
    assert 'id="walletWatchSourceTestResult"' in html
    assert 'Speichere Sats Sentinel' in app
    assert 'api/wallet-watch/source-test' in app
    assert 'button.disabled=true' in app


def test_sats_sentinel_save_api_does_not_wait_for_full_wallet_poll():
    init_py = (ROOT / "custom_components/bitcoin_stack_tracker/__init__.py").read_text()
    assert 'async_apply_full_config(config, poll=False)' in init_py
    assert 'route == "api/wallet-watch/source-test"' in init_py


def test_sats_sentinel_source_change_clears_stale_offline_state():
    backend = (ROOT / "custom_components/bitcoin_stack_tracker/wallet_watch.py").read_text()
    assert 'old_source_fingerprint' in backend
    assert 'new_source_fingerprint != old_source_fingerprint' in backend
    assert 'fresh["last_error"] = None' in backend


def test_sats_sentinel_pinned_self_signed_electrum_certificate_surface_and_runtime():
    html = (COMPONENT / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")

    assert 'id="walletWatchElectrumPinnedCertPem"' in html
    assert "Zertifikat anheften" in html
    assert "niemals einen Private Key" in html
    assert "electrum_pinned_cert_pem" in app
    assert "def _normalize_electrum_pinned_certificate" in backend
    assert 'if "PRIVATE KEY" in upper:' in backend
    assert 'cert.fingerprint(hashes.SHA256()).hex()' in backend
    assert '"electrum_pinned_cert_sha256"' in backend
    assert '"electrum_pinned_cert_pem"' not in backend[backend.index("def runtime_cache_from_config"):backend.index("class WalletWatchRuntimeStore")]
    assert 'peer_der = ssl_object.getpeercert(binary_form=True)' in backend
    assert "hmac.compare_digest(actual, pinned)" in backend
    assert "certificate pin mismatch" in backend


def test_sats_sentinel_removed_monitor_purges_encrypted_journal_and_ui_saves_immediately():
    backend = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
    app = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")

    replace_start = backend.index("async def async_replace_from_full_config")
    replace_end = backend.index("def _canonical_mempool_base_url", replace_start)
    replace = backend[replace_start:replace_end]
    assert "removed_monitor_ids = old_monitor_ids - new_monitor_ids" in replace
    assert 'if str(item.get("monitor_id") or "") not in removed_monitor_ids' in replace
    assert "purged_activity_count" in replace
    assert "await self.async_save()" in replace

    assert "async function removeWalletWatchMonitor(id)" in app
    assert "Journal-Historie wird dauerhaft" in app
    delete_block = app[app.index("async function removeWalletWatchMonitor(id)"):app.index("function addWalletWatchMonitor", app.index("async function removeWalletWatchMonitor(id)"))]
    assert 'api("api/wallet-watch"' in delete_block
    assert "loadWalletWatchActivity(1)" in delete_block
    assert "purged_activity_count" in delete_block
