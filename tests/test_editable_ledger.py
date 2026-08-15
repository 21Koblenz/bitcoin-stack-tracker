from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
INIT = (COMP / "__init__.py").read_text(encoding="utf-8")
STORAGE = (COMP / "storage.py").read_text(encoding="utf-8")
APP = (COMP / "frontend/static/app-v021009-bba91c83.js").read_text(encoding="utf-8")
HTML = (COMP / "frontend/index.html").read_text(encoding="utf-8")
SERVICES = (COMP / "services.yaml").read_text(encoding="utf-8")


def test_existing_ledger_entries_can_be_edited_in_place():
    assert 'SERVICE_UPDATE_ENTRY = "update_entry"' in INIT
    assert '(SERVICE_UPDATE_ENTRY, update_entry' in INIT
    assert 'await storage.async_update_entry(item_id, replacement)' in INIT
    assert 'async def async_update_entry' in STORAGE
    assert 'updated["id"] = item_id' in STORAGE
    assert '"chart_cache"' in STORAGE
    assert 'update_entry:' in SERVICES


def test_frontend_has_edit_button_and_reuses_transaction_controls():
    assert 'class="secondary compact edit-entry"' in APP
    assert 'function beginEditEntry(entryId)' in APP
    assert 'service("update_entry",payload)' in APP
    assert 'id="transactionCancelEdit"' in HTML
    assert 'id="transactionFormTitle"' in HTML
    assert 'name="fiat_total"' in HTML
    assert 't("saveChanges")' in APP


def test_consumed_purchase_is_not_falsely_shown_as_unknown():
    block = APP.split("function entryHoldingDetails(entry)", 1)[1].split("function applyStaticSelects", 1)[0]
    assert 'return {status:"consumed",reason:t("holdingReasonConsumed")};' in block
    assert 'status === "consumed" ? t("consumed")' in APP
    assert 'holdingReasonCurrency' in APP
    assert 'holdingReasonUnknownCost' in APP
    assert 'holdingReasonInsufficient' in APP


def test_edit_revalidates_fifo_and_allows_entry_type_correction():
    block = INIT.split("async def update_entry(call", 1)[1].split("async def delete_entry(call", 1)[0]
    assert 'kind = str(call.data.get("type", existing.get("type"))' in block
    assert 'await storage.async_update_entry(item_id, replacement)' in block
    # FIFO validation is centralized in storage so the exact validated cache is
    # reused for persistence instead of performing the expensive calculation twice.
    storage_block = STORAGE.split("async def async_update_entry", 1)[1].split("async def async_delete", 1)[0]
    assert 'fifo_cache = await self._async_validate_fifo_change(before, entries)' in storage_block
    assert 'await self._async_save(refresh_fifo_cache=False)' in storage_block
    frontend = APP.split("function beginEditEntry(entryId)", 1)[1].split("function openDeleteEntryDialog", 1)[0]
    assert 'type.disabled=false' in frontend
