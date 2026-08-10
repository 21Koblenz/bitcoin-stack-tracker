from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
APP = (COMP / "frontend/static/app-v021003-e7911ff7.js").read_text(encoding="utf-8")
CSS = (COMP / "frontend/static/style-v021003-e7911ff7.css").read_text(encoding="utf-8")
INDEX = (COMP / "frontend/index.html").read_text(encoding="utf-8")
INIT = (COMP / "__init__.py").read_text(encoding="utf-8")


def test_fifo_sales_shows_full_performance_columns_summary_and_pagination():
    for label in ("Kaufkurs damals", "FIFO-Einstand", "Verkaufskurs", "Verkaufserlös", "Gewinn/Verlust", "Rendite"):
        assert label in INDEX
    assert 'id="fifoSaleSummary"' in INDEX
    assert 'id="fifoPagination"' in INDEX
    assert 'function renderFifoSaleSummary(matches)' in APP
    assert 'const pageSize=Math.max(10,Number(state.ledgerPageSize)||25);' in APP
    assert 'function scrollFifoPageToStart()' in APP
    assert 'tableWrap.scrollTo({top:0,behavior:"smooth"})' in APP
    assert 'match.net_proceeds' in APP
    assert '(gain/basis)*100' in APP


def test_ledger_page_change_scrolls_inner_list_not_whole_tab_on_desktop():
    assert 'function scrollLedgerPageToStart()' in APP
    assert 'tableWrap.scrollTo({top:0,behavior:"smooth"})' in APP
    assert '$("#tab-ledger")?.scrollIntoView' not in APP


def test_bitcoin_hero_mark_is_not_fake_bold_or_rotated():
    assert '<span class="bitcoin-mark">₿</span>' in INDEX
    assert 'font-weight:400' in CSS
    assert 'font-synthesis:none' in CSS
    assert 'transform:rotate(8deg)' not in CSS


def test_gateway_drops_are_not_combined_with_core_policy_rejects():
    assert '"blocked_direct_packets": blocked_gateway' in INIT
    assert '"core_blocked_direct_requests": int(state.get("blocked_direct_requests", 0))' in INIT
    assert 'int(state.get("blocked_direct_requests", 0)) + blocked_gateway' not in INIT
    assert 'blockedConnections:"Vom Killswitch geblockte Pakete"' in APP
    assert 'coreBlocked:"Von der Integration vor Verbindung blockiert"' in APP


def test_app_log_scrolls_to_latest_entry_after_load():
    assert 'requestAnimationFrame(()=>{output.scrollTop=output.scrollHeight;});' in APP
