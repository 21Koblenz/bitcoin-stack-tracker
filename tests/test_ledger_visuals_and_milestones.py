from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "custom_components" / "bitcoin_stack_tracker" / "frontend"
APP = (FRONTEND / "static" / "app-v021005-28d54128.js").read_text(encoding="utf-8")
CSS = (FRONTEND / "static" / "style-v021005-28d54128.css").read_text(encoding="utf-8")


def test_ledger_notes_start_after_date_column_and_date_stays_separate():
    assert 'class="ledger-date-cell"' in APP
    assert 'class="ledger-note-date-spacer"' in APP
    assert 'colspan="8"' in APP
    assert '.ledger-date-cell{' in CSS
    assert '.ledger-note-row td[colspan]' in CSS


def test_purchase_and_sale_have_distinct_transaction_colours():
    assert 'function ledgerTypeClass(type)' in APP
    assert '`ledger-type-${value}`' in APP
    assert '.ledger-entry-row.ledger-type-purchase td' in CSS
    assert '.ledger-entry-row.ledger-type-sale td' in CSS
    assert '.ledger-type-purchase .ledger-type-badge' in CSS
    assert '.ledger-type-sale .ledger-type-badge' in CSS
    assert 'var(--green)' in CSS
    assert 'var(--red)' in CSS


def test_goal_milestone_is_attached_to_entry_that_first_crossed_target():
    assert 'function goalMilestonesByEntryId()' in APP
    helper = APP.split('function goalMilestonesByEntryId()', 1)[1].split('function ledgerDetailHtml', 1)[0]
    assert 'if (state.discreet) return result;' in helper
    assert 'balance + 1e-12 >= target' in helper
    assert 'result.get(entryId).push(goal)' in helper
    assert 'ledger-milestone-block' in APP
    assert 'milestoneReached:"Meilenstein erreicht"' in APP


def test_ledger_search_can_find_goal_name_for_milestone_entry():
    block = APP.split('function renderLedger()', 1)[1].split('function renderAggregateDepot()', 1)[0]
    assert 'milestoneMap.get(String(item.id))' in block
    assert 'goal?.name' in block
