from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORAGE = (ROOT / "custom_components/bitcoin_stack_tracker/storage.py").read_text(encoding="utf-8")
FIFO = (ROOT / "custom_components/bitcoin_stack_tracker/fifo.py").read_text(encoding="utf-8")
APP = (ROOT / "custom_components/bitcoin_stack_tracker/frontend/static/app-v021009-1ef3c90f.js").read_text(encoding="utf-8")


def test_bulk_import_reuses_precomputed_fifo_cache():
    block = STORAGE.split("async def async_bulk_import", 1)[1].split("async def async_add_depot", 1)[0]
    assert "self._fifo_cache = fifo_cache" in block
    assert "await self._async_save(refresh_fifo_cache=False)" in block
    assert "async def _async_save(self, *, refresh_fifo_cache: bool = True)" in STORAGE


def test_fifo_uses_per_depot_cursor_for_outgoing_transactions():
    assert "lot_cursor_by_depot: dict[str, int] = {}" in FIFO
    assert "while lot_cursor < len(lots) and remaining_sale > 0:" in FIFO
    assert "while lot_cursor < len(lots) and remaining_expense > 0:" in FIFO


def test_bulk_import_frontend_timeout_has_large_import_reserve():
    block = APP.split("async function confirmCsvImport()", 1)[1].split("function transactionLocalTimestamp", 1)[0]
    assert "timeoutMs:300000" in block
