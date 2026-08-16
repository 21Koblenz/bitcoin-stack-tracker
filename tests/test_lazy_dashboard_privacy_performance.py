from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
INIT = (COMP / "__init__.py").read_text(encoding="utf-8")
APP = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")


def _block(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_native_panel_loads_summary_first_and_heavy_sections_on_demand():
    load = _block(APP, "async function loadData()", "async function ensureIntradayHistory")
    assert "&section=summary" in load
    assert "ensureActiveTabData(state.activeTab)" in load
    lazy = _block(APP, "async function ensureDashboardSection(section)", "function ensureActiveTabData")
    assert 'section === "chart"' in lazy
    assert 'ensureDashboardSection("ledger")' in APP
    assert 'ensureDashboardSection("fifo")' in APP
    assert 'dashboardLoadRevision' in APP


def test_chart_analytics_use_sanitized_chart_events_not_full_ledger():
    helper = _block(APP, "function chartLedgerEntries()", "function dashboardSectionLoaded")
    assert "chart_ledger_events" in helper
    perf = _block(APP, "function performanceLedgerEvents", "function performancePricePoints")
    assert "chartLedgerEntries()" in perf
    chart = _block(APP, "function ledgerStackAndPortfolio", "function fifoMetricEvents")
    assert "chartLedgerEntries()" in chart


def test_backend_chart_events_omit_notes_ids_and_import_fingerprints():
    helper = _block(INIT, "def _dashboard_chart_ledger_events", "def _with_requester")
    assert '"timestamp"' in helper and '"amount_btc"' in helper
    assert '"depot_id"' in helper
    assert '"note"' not in helper
    assert '"import_ref_hash"' not in helper
    assert '"id"' not in helper


def test_summary_payload_is_aggregate_only_and_has_currency_fifo_summaries():
    handler = _block(INIT, "async def dashboard_data(call", "async def list_users")
    assert 'if section == "ledger"' in handler
    assert 'if section == "fifo"' in handler
    assert 'if section == "chart"' in handler
    assert '"purchase_totals": _dashboard_purchase_totals(entries)' in handler
    assert '"depot_entry_counts": _dashboard_depot_entry_counts(entries)' in handler
    helper = _block(INIT, "def _dashboard_fifo_summary", "def _dashboard_purchase_totals")
    assert '"currency_summaries"' in helper
    assert '"open_lots"' not in helper
    assert '"matches"' not in helper


def test_sensitive_panel_responses_are_no_store_and_same_origin():
    block = _block(INIT, "def respond(payload", 'if route == "api/whoami"')
    assert 'Cache-Control"] = "no-store, private, max-age=0"' in block
    assert 'Cross-Origin-Resource-Policy"] = "same-origin"' in block
    assert 'Referrer-Policy"] = "no-referrer"' in block


def test_non_owner_connection_inventory_is_not_reintroduced_by_rpc_layer():
    route = _block(INIT, 'if route == "api/dashboard"', 'if route == "api/security/users"')
    assert "security.is_owner(requester)" in route
    assert 'section in {"summary", "all"}' in route


def test_csv_duplicate_review_stays_core_side_without_loading_full_ledger():
    block = _block(APP, "async function previewCsvImport", "async function confirmCsvImport")
    assert 'ensureDashboardSection("ledger")' not in block
    assert 'dashboardSectionLoaded("ledger")' not in block
    assert 'api/import/duplicates' in APP


def test_tax_fifo_section_does_not_require_full_ledger_or_expose_entry_ids():
    helper = _block(INIT, "def _dashboard_fifo_matches", "def _dashboard_chart_ledger_events")
    assert '"purchase_id", "sale_id"' in helper
    assert '"purchase_price"' in helper and '"sale_price"' in helper
    assert '"note"' not in helper
    handler = _block(INIT, 'if section == "fifo"', 'cutoff = None')
    assert '_dashboard_fifo_matches(fifo, storage.entries)' in handler
    tax_loader = _block(APP, "function ensureActiveTabData", "function schedulePerformanceSummary")
    tax_part = tax_loader.split('tabName === "tax"', 1)[1]
    assert 'ensureDashboardSection("fifo")' in tax_part
    assert 'ensureDashboardSection("ledger")' not in tax_part


def test_lazy_section_responses_are_revision_guarded_against_stale_same_portfolio_data():
    lazy = _block(APP, "async function ensureDashboardSection(section)", "function ensureActiveTabData")
    assert "requestedRevision = dashboardLoadRevision" in lazy
    assert "requestedRevision !== dashboardLoadRevision" in lazy
    load = _block(APP, "async function loadData()", "async function ensureIntradayHistory")
    assert "requestedRevision = dashboardLoadRevision" in load
    assert "requestedRevision !== dashboardLoadRevision" in load
