from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
CONST = (COMP / "const.py").read_text(encoding="utf-8")
INDEX = (COMP / "frontend/index.html").read_text(encoding="utf-8")
APP = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")
INIT = (COMP / "__init__.py").read_text(encoding="utf-8")


def test_frontend_assets_share_release_and_cache_revision():
    version = re.search(r'FRONTEND_BUILD = "([^"]+)"', CONST).group(1)
    revision = re.search(r'FRONTEND_CACHE_REVISION = "([^"]+)"', CONST).group(1)
    assert f'static/style.css?v={version}&r={revision}' in INDEX
    assert f'static/app.js?v={version}&r={revision}' in INDEX
    assert f'static/performance-math.js?v={version}&r={revision}' in INDEX
    assert '&r=6' not in INDEX


def test_reconstruction_progress_has_lightweight_live_endpoint():
    assert 'api/market-assessment/backfill-status' in INIT
    block = INIT.split('if route == "api/market-assessment/backfill-status"', 1)[1].split('if route == "api/market-assessment/history"', 1)[0]
    assert 'async_market_assessment(' not in block
    assert 'async_stats(intraday_signature)' in block
    assert 'intraday_backfill' in block


def test_market_tab_polls_only_lightweight_progress_every_30_seconds():
    assert 'marketAssessmentBackfillPollTimer=setInterval' in APP
    assert 'state.activeTab!=="market"' in APP
    assert 'refreshMarketAssessmentBackfillStatus({silent:true})' in APP
    poll = APP.split('marketAssessmentBackfillPollTimer=setInterval', 1)[1].split('function startNetworkPolling', 1)[0]
    assert '},30000);' in poll
    assert 'api/market-assessment/backfill-status?' in APP
