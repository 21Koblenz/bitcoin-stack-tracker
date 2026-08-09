from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

MODELS_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "bitcoin_stack_tracker" / "models.py"
spec = spec_from_file_location("bst_models_test", MODELS_PATH)
models = module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(models)


class GoalReachedTests(unittest.TestCase):
    def test_first_crossing_is_returned_and_sales_reduce_balance(self):
        entries = [
            {"id":"1","type":"purchase","timestamp":"2026-01-01T10:00:00+00:00","depot_id":"main","amount_btc":"0.4"},
            {"id":"2","type":"purchase","timestamp":"2026-02-01T10:00:00+00:00","depot_id":"main","amount_btc":"0.7"},
            {"id":"3","type":"sale","timestamp":"2026-03-01T10:00:00+00:00","depot_id":"main","amount_btc":"0.3"},
            {"id":"4","type":"purchase","timestamp":"2026-04-01T10:00:00+00:00","depot_id":"main","amount_btc":"0.5"},
        ]
        self.assertEqual(models.goal_reached_at(entries, "1.0", "main"), "2026-02-01T10:00:00+00:00")
        self.assertIsNone(models.goal_reached_at(entries, "2.0", "main"))

    def test_offsets_are_sorted_as_actual_instants_and_historical_crossing_remains(self):
        entries = [
            {"id":"later","type":"sale","timestamp":"2026-01-01T10:30:00+01:00","depot_id":"main","amount_btc":"0.2"},
            {"id":"first","type":"purchase","timestamp":"2026-01-01T09:00:00+00:00","depot_id":"main","amount_btc":"1.0"},
        ]
        self.assertEqual(models.goal_reached_at(entries, "1.0", "main"), "2026-01-01T09:00:00+00:00")

    def test_depot_scope_is_respected(self):
        entries = [
            {"id":"1","type":"purchase","timestamp":"2026-01-01T10:00:00+00:00","depot_id":"a","amount_btc":"0.6"},
            {"id":"2","type":"stack","timestamp":"2026-01-02T10:00:00+00:00","depot_id":"b","amount_btc":"0.6"},
        ]
        self.assertIsNone(models.goal_reached_at(entries, "1.0", "a"))
        self.assertEqual(models.goal_reached_at(entries, "1.0", "all"), "2026-01-02T10:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
