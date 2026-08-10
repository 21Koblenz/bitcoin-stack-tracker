from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
INIT = (COMP / "__init__.py").read_text(encoding="utf-8")
STORAGE = (COMP / "storage.py").read_text(encoding="utf-8")
APP = (COMP / "frontend/static/app-v021002-81aa3197.js").read_text(encoding="utf-8")
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


def test_edit_revalidates_fifo_and_preserves_entry_type():
    block = INIT.split("async def update_entry(call", 1)[1].split("async def delete_entry(call", 1)[0]
    assert 'kind = str(existing.get("type")' in block
    assert 'candidate_entries = [replacement if item.get("id") == item_id else item for item in entries]' in block
    assert 'fifo_result' in block
    assert 'if check["oversold_btc"] > 0:' in block
    frontend = APP.split("function beginEditEntry(entryId)", 1)[1].split("function openDeleteEntryDialog", 1)[0]
    assert 'type.disabled=true' in frontend
