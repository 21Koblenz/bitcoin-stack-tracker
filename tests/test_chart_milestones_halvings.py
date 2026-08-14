from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
INIT = (COMP / "__init__.py").read_text(encoding="utf-8")
INDEX = (COMP / "frontend/index.html").read_text(encoding="utf-8")
APP = (COMP / "frontend/static/app-v021009-1ef3c90f.js").read_text(encoding="utf-8")
CSS = (COMP / "frontend/static/style-v021006-733b783d.css").read_text(encoding="utf-8")


def test_chart_has_independent_milestone_and_halving_toggles():
    assert 'id="chartMilestonesButton"' in INDEX
    assert 'id="chartHalvingsButton"' in INDEX
    assert 'bst_chart_milestones' in APP
    assert 'bst_chart_halvings' in APP
    assert 'function updateChartMarkerButtons()' in APP
    assert 'if (!state.showMilestones || state.discreet) return [];' in APP


def test_milestones_are_rendered_at_the_transaction_that_crossed_the_goal():
    assert 'function chartMilestoneEvents()' in APP
    assert 'goalMilestonesByEntryId()' in APP
    assert 'kind: "milestone"' in APP
    assert 'icon: "★"' in APP
    assert 'chart-event-milestone' in CSS


def test_halvings_use_210k_block_boundaries_and_mempool_api():
    assert '_HALVING_INTERVAL = 210_000' in INIT
    assert '"/api/blocks/tip/height"' in INIT
    assert 'f"/api/block-height/{height}"' in INIT
    assert 'f"/api/block/{block_hash}"' in INIT
    assert 'route == "api/chart/halvings"' in INIT
    assert 'function chartHalvingEvents()' in APP
    assert 'chart-event-halving' in CSS


def test_own_mempool_is_preferred_and_public_fallback_is_tor_routed():
    helper = INIT.split('def _halving_source_candidates', 1)[1].split('def _halving_source_label', 1)[0]
    assert 'CONF_MEMPOOL_OWN_INSTANCE' in helper
    assert 'DEFAULT_MEMPOOL_URL' in helper
    fetch = INIT.split('async def _halving_mempool_text', 1)[1].split('async def _halving_mempool_json', 1)[0]
    assert 'uses_tor = mempool_source_uses_tor(source)' in fetch
    assert 'proxy_url=tor_proxy_from_settings(settings) if uses_tor else None' in fetch
    assert 'allow_local_direct=not uses_tor' in fetch


def test_future_halvings_are_discovered_without_hardcoded_dates():
    helper = INIT.split('async def _async_halving_markers', 1)[1].split('_PANEL_STATE_VERSION', 1)[0]
    assert 'tip_height // _HALVING_INTERVAL' in helper
    assert 'range(_HALVING_INTERVAL, latest_halving + 1, _HALVING_INTERVAL)' in helper
    assert '_HALVING_CACHE_TTL' in helper
    assert 'next_halving_height' in helper
