from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
FIFO = (COMP / "fifo.py").read_text(encoding="utf-8")
STORAGE = (COMP / "storage.py").read_text(encoding="utf-8")
HISTORY = (COMP / "history.py").read_text(encoding="utf-8")
INIT = (COMP / "__init__.py").read_text(encoding="utf-8")


def test_fifo_cursor_is_calculation_local_and_ledger_is_resorted_each_run():
    assert "lot_cursor_by_depot: dict[str, int] = {}" in FIFO
    assert "filtered = [" in FIFO and "_sorted_entries(entries)" in FIFO
    assert "while lot_cursor < len(lots) and remaining_sale > 0:" in FIFO
    assert "while lot_cursor < len(lots) and remaining_expense > 0:" in FIFO


def test_daily_history_uses_single_pass_compact_snapshots_not_fifo_per_day():
    block = HISTORY.split("def _daily_fifo_snapshots", 1)[1].split("def _chart_revision", 1)[0]
    assert "lot_cursor_by_depot" in block
    assert "mature_until" in block
    assert '"currencies": currency_summaries' in block
    assert '"depots": {' in block
    assert "fifo_result(active" not in block
    assert "snapshots[day] = fifo_result" not in block
    assert '"chart_schema": 5' in HISTORY


def test_dashboard_reuses_storage_fifo_cache():
    handler = INIT.split("async def dashboard_data(call", 1)[1].split("async def list_users", 1)[0]
    assert "cached_fifo = storage.fifo_summary()" in handler
    assert "cached_depot_fifo" in handler
    assert "cached_fifo," in handler
    assert "cached_depot_fifo," in handler


def test_derived_chart_cache_save_does_not_rebuild_fifo():
    block = STORAGE.split("async def async_set_chart_cache", 1)[1].split("def has_depot", 1)[0]
    assert "await self._async_save(refresh_fifo_cache=False)" in block
