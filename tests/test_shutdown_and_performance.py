from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
APP = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")
RUN = (ROOT / "bitcoin_stack_tracker_dashboard" / "run.sh").read_text(encoding="utf-8")


def test_shutdown_budget_is_well_below_s6_svwait_timeout():
    health = RUN.split("stop_health_agent() {", 1)[1].split("nft_counter() {", 1)[0]
    tor = RUN.split("stop_tor() {", 1)[1].split("request_shutdown() {", 1)[0]
    final = RUN.split("terminate_remaining_managed_processes() {", 1)[1].split("stop_health_agent() {", 1)[0]
    assert "attempts < 8" in health
    assert "attempts < 4" in health
    assert "attempts < 16" in tor
    assert "attempts < 5" in tor
    assert "attempts < 5" in final
    assert 'signal_pid_checked "${tor_pid}" TERM "Tor"' in tor
    assert 'signal_pid_checked "${tor_pid}" KILL "Tor"' in tor
    assert "s6-svwait" in RUN  # documented reason for the bounded budget


def test_overview_book_profit_includes_matching_percentage():
    assert "const unrealizedPercent=unrealized!=null&&invested>0?unrealized/invested*100:null;" in APP
    assert '`${t("onOpenCostBasis")}: ${unrealizedPercent==null?"–":signedPercent(unrealizedPercent)}' in APP


def test_depot_range_performance_uses_roi_matching_the_absolute_profit():
    assert "const positiveFlows=events.reduce((sum,item)=>sum+(item.flow>0?item.flow:0),0);" in APP
    assert "const capitalBase=Math.max(0,start.value)+positiveFlows;" in APP
    assert "const roiPercent=capitalBase>0?absolute/capitalBase*100:null;" in APP
    assert "roiPercent,capitalBase" in APP
    assert 'portfolioChange.roiPercent==null?"–":signedPercent(portfolioChange.roiPercent)' in APP
    # Dedicated return analytics must still use TWR rather than the simple ROI.
    assert 't("twr")' in APP
    assert "portfolioChange.percent==null?\"–\":signedPercent(portfolioChange.percent)" in APP
