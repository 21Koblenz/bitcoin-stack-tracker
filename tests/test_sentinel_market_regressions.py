from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "bitcoin_stack_tracker"
APP = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
CSS = (COMPONENT / "frontend" / "static" / "style.css").read_text(encoding="utf-8")
INIT = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
CACHE = (COMPONENT / "market_assessment_intraday_cache.py").read_text(encoding="utf-8")


def test_market_assessment_persists_real_five_minute_points_for_90_days():
    assert "_STORAGE_VERSION = 1" in CACHE
    assert "_RETENTION_DAYS = 90" in CACHE
    assert "_BUCKET_MINUTES = 5" in CACHE
    assert "_SAVE_DELAY_SECONDS = 60 * 60" in CACHE
    assert '"90d": 91' in INIT


def test_market_history_consumes_intraday_points_and_refreshes_on_new_score():
    assert 'marketAssessmentLiveTailPoints(payload,{includeIntraday:true})' in APP
    assert 'if(state.historyRange==="1")return 5;' in APP
    assert 'Math.floor(Date.now()/300000)' in APP
    assert 'const assessmentAdvanced=' in APP
    assert 'loadMarketAssessmentHistory({force:true})' in APP
    assert 'ensureChartMarketAssessmentHistory({force:true})' in APP


def test_locked_sentinel_uses_local_opt_in_but_server_remains_authoritative():
    assert 'const showLockedSentinel=walletWatchShowWhenLocked();' in APP
    assert 'if(!state.entryId||!state.data?.locked)return false;' in APP
    assert 'state.data.security={...(state.data.security||{}),owner:true}' in APP
    assert 'Boolean(state.data.security?.owner)&&walletWatchShowWhenLocked()' not in APP
    assert '!state.data?.security?.owner||!walletWatchShowWhenLocked()' not in APP


def test_sentinel_addresses_are_collapsible_on_desktop_and_mobile():
    assert '.sats-sentinel-monitored-addresses>summary{cursor:pointer;user-select:none}' in CSS
    assert '.sats-sentinel-monitored-addresses:not([open])>.sats-sentinel-address-list{display:none!important}' in CSS


def test_no_temporary_runtime_patch_ships():
    assert not (COMPONENT / "frontend" / "static" / "runtime-fixes.js").exists()


def test_version_specific_root_notes_are_archived():
    for pattern in ("GITHUB-RELEASE-v*.md", "RELEASE-QC-v*.md", "AUDIT-v*.md", "GIT-CLEANUP-v*.md"):
        assert not list(ROOT.glob(pattern)), pattern
