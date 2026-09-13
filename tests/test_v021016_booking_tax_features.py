from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"

PANEL = (COMP / "panel.py").read_text(encoding="utf-8")
CUTOFF = (COMP / "holding_cutoff.py").read_text(encoding="utf-8")
FEATURE = (COMP / "frontend/static/booking_tax_features.js").read_text(encoding="utf-8")
MATH = (COMP / "frontend/static/booking_value_math.js").read_text(encoding="utf-8")
LOADER = (COMP / "frontend/static/feature_loader.js").read_text(encoding="utf-8")


def test_release_loader_is_fail_safe_and_uses_original_panel_module():
    assert 'module_url=f"{STATIC_URL}/panel.js?v={FRONTEND_BUILD}&r={FRONTEND_CACHE_REVISION}"' in PANEL
    assert "index_features.html" in PANEL
    assert "window.location.replace(fallback)" in LOADER


def test_booking_table_keeps_original_column_count():
    assert "bst-current-head" not in FEATURE
    assert "bst-current-cell" not in FEATURE
    assert 'cell.dataset?.i18n === "fiatTotal"' in FEATURE
    assert "columnCount - 1" not in FEATURE


def test_cutoff_table_sorting_and_date_format():
    assert "cutoffDateDisplay" in FEATURE
    assert "`${year} ${month} ${day}`" in FEATURE
    assert "bst-sort-acquired" in FEATURE
    assert 'cutoffSortDirection === "asc" ? "desc" : "asc"' in FEATURE


def test_unlock_regression_has_no_mutation_observer():
    assert "new MutationObserver" not in FEATURE
    assert "observer.observe" not in FEATURE


def test_backend_cutoff_keeps_blocked_lots_short_term():
    assert 'result["holding_status"] = "short_term"' in CUTOFF
    assert 'result["long_term_date"] = None' in CUTOFF
    assert 'result["days_until_long_term"] = None' in CUTOFF
    assert "tax_cutoff_blocked_btc" in CUTOFF


def test_current_value_math_is_fee_aware():
    assert 'type === "purchase" || type === "income"' in MATH
    assert 'type === "sale" || type === "expense"' in MATH
    assert "currentValue / historical - 1" in MATH
