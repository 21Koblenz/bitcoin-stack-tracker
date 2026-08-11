from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
INIT = (COMP / "__init__.py").read_text(encoding="utf-8")
INDEX = (COMP / "frontend/index.html").read_text(encoding="utf-8")
APP = (COMP / "frontend/static/app-v021007-050b734c.js").read_text(encoding="utf-8")
CSS = (COMP / "frontend/static/style-v021006-733b783d.css").read_text(encoding="utf-8")


def test_chart_event_symbols_share_one_height_and_milestones_are_green():
    assert "const markerY = pad.t + 15;" in APP
    assert "const lane = index % 3" not in APP
    assert 'class="chart-event-badge"' in APP
    assert ".chart-event-milestone .chart-event-line,.chart .chart-event-milestone .chart-event-badge{stroke:var(--green)}" in CSS
    assert ".chart-event-milestone .chart-event-icon{fill:var(--green)}" in CSS
    assert ".chart-tooltip-event.milestone span{color:var(--green)}" in CSS


def test_discreet_mode_masks_stored_ledger_notes():
    assert 'const noteText = entry.note ? (state.discreet ? "***" : String(entry.note)) : "";' in APP
    assert 'ledger-note-block' in APP


def test_dca_has_anniversary_year_monthly_savings_rates():
    assert "function dcaPersonalYearCards(currency)" in APP
    assert "const start = new Date(purchases[0].time), now = new Date();" in APP
    assert "function addPersonalYears(date, years)" in APP
    assert "function personalMonthsStarted(start, end)" in APP
    assert "effectivePurchaseUnitCost" in APP
    assert 't("monthlySavingsOverall")' in APP
    assert 't("personalSavingsYear")' in APP
    assert "...dcaPersonalYearCards(currency)" in APP


def test_homepage_has_bitcoin_network_strip_and_derived_moscow_time():
    for element_id in (
        "bitcoinNetworkStrip",
        "heroBlockHeight",
        "heroMoscowTime",
        "heroHalvingCountdown",
        "heroHalvingEstimate",
    ):
        assert f'id="{element_id}"' in INDEX
    assert "function renderBitcoinNetworkStrip()" in APP
    assert "SATS_PER_BTC / fiatPrice" in APP
    assert "const currency = currentCurrency();" in APP
    assert "moscowUnit.textContent = `sats / ${currency}`" in APP
    assert "blocks * 10 * 60 * 1000" in APP
    assert "next_halving_height" in INIT
    assert "blocks_to_next_halving" in INIT
    assert "_HALVING_CACHE_TTL = timedelta(minutes=1)" in INIT


def test_halving_network_source_remains_local_first_then_tor():
    helper = INIT.split("def _halving_source_candidates", 1)[1].split("def _halving_source_label", 1)[0]
    assert "CONF_MEMPOOL_OWN_INSTANCE" in helper
    assert "DEFAULT_MEMPOOL_URL" in helper
    fetch = INIT.split("async def _halving_mempool_text", 1)[1].split("async def _halving_mempool_json", 1)[0]
    assert "proxy_url=tor_proxy_from_settings(settings) if uses_tor else None" in fetch
    assert "allow_local_direct=not uses_tor" in fetch
