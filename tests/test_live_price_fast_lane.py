from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LivePriceFastLaneTests(unittest.TestCase):
    def test_separate_default_cadences(self):
        text = (ROOT / "custom_components/bitcoin_stack_tracker/const.py").read_text()
        self.assertIn('DEFAULT_UPDATE_INTERVAL = 300', text)
        self.assertIn('DEFAULT_PUBLIC_UPDATE_INTERVAL = 60', text)
        self.assertIn('MIN_PUBLIC_UPDATE_INTERVAL = 30', text)

    def test_coordinator_has_public_fast_lane_and_local_anchor(self):
        text = (ROOT / "custom_components/bitcoin_stack_tracker/coordinator.py").read_text()
        self.assertIn('def _is_public_source', text)
        self.assertIn('self.public_interval_seconds if self._is_public_source(source) else self.local_interval_seconds', text)
        self.assertIn('if self._is_public_source(source)', text)
        self.assertIn('public_fast_lane', text)
        self.assertIn('ordered_indices = [', text)

    def test_dashboard_poll_is_local_cache_only(self):
        text = (ROOT / "custom_components/bitcoin_stack_tracker/frontend/static/app.js").read_text()
        self.assertIn('api/live-price?entry_id=', text)
        self.assertIn('},15000);', text)
        self.assertIn('This 15-second UI loop is local-only', text)

    def test_live_price_endpoint_does_not_force_external_refresh(self):
        text = (ROOT / "custom_components/bitcoin_stack_tracker/__init__.py").read_text()
        start = text.index('if route == "api/live-price"')
        end = text.index('if route == "api/market-assessment"', start)
        block = text[start:end]
        self.assertNotIn('async_refresh()', block)
        self.assertIn('runtime["coordinator"].data', block)


    def test_price_refresh_survives_restart_without_dashboard_or_sensor_listener(self):
        init = (ROOT / "custom_components/bitcoin_stack_tracker/__init__.py").read_text()
        coordinator = (ROOT / "custom_components/bitcoin_stack_tracker/coordinator.py").read_text()
        app = (ROOT / "custom_components/bitcoin_stack_tracker/frontend/static/app.js").read_text()
        self.assertIn('await coordinator.async_config_entry_first_refresh()', init)
        self.assertIn('cancel_price_refresh_listener = coordinator.async_add_listener(lambda: None)', init)
        self.assertIn('"cancel_price_refresh_listener": cancel_price_refresh_listener', init)
        self.assertIn('config_entry=entry', coordinator)
        live_start = app.index('async function refreshLivePrice')
        market_start = app.index('async function refreshMarketAssessment')
        self.assertNotIn('state.data.locked', app[live_start:market_start])
        market_end = app.index('function startMarketAssessmentPolling', market_start)
        self.assertNotIn('state.data.locked', app[market_start:market_end])

    def test_frontend_assets_are_cache_busted_for_sentinel_v5(self):
        index = (ROOT / "custom_components/bitcoin_stack_tracker/frontend/index.html").read_text()
        self.assertIn('style-v021009-', index)
        self.assertNotIn('style-v021006-', index)
        panel = (ROOT / "custom_components/bitcoin_stack_tracker/panel.py").read_text()
        self.assertIn('release021009-r2', panel)

    def test_sentinel_own_mempool_rule_remains_exclusive(self):
        text = (ROOT / "custom_components/bitcoin_stack_tracker/wallet_watch.py").read_text()
        self.assertIn('an explicitly configured own/custom mempool instance is exclusive', text)
        self.assertIn('own/custom ``.onion`` node is contacted through Tor and remains exclusive', text)
        self.assertIn('source[CONF_MEMPOOL_OWN_INSTANCE] = True', text)
        self.assertIn('automatic_mempool_route(', text)
        self.assertIn('return [source]', text)


if __name__ == '__main__':
    unittest.main()
