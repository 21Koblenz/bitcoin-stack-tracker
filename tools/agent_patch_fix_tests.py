from pathlib import Path

root = Path(__file__).resolve().parents[1]

# The generated regression should match the actual optional-chaining path used
# by app.js. The important property is that custom labels are read from the
# normalized market-assessment settings and are display-only.
reg = root / "tests" / "test_xpub_backfill_rating_regressions.py"
text = reg.read_text(encoding="utf-8")
text = text.replace(
    'and "buy_opportunity_settings?.labels" in A',
    'and "?.labels?.[value]" in A',
)
reg.write_text(text, encoding="utf-8")

# Seven new label inputs are intentionally display-only. They do not need the
# tuning-direction help required by numeric/model controls.
path = root / "tests" / "test_market_assessment_ui.py"
text = path.read_text(encoding="utf-8")
old = '''    assert len(field_names) == 94
    for name in field_names:
        assert f'"{name}":[' in block
'''
new = '''    assert len(field_names) == 101
    label_fields = [name for name in field_names if name.startswith("label_")]
    assert len(label_fields) == 7
    assert set(label_fields) == {
        "label_very_expensive", "label_expensive", "label_neutral",
        "label_interesting", "label_cheap", "label_very_cheap", "label_extreme",
    }
    for name in field_names:
        if name.startswith("label_"):
            continue
        assert f'"{name}":[' in block
'''
if old not in text:
    raise RuntimeError("market-assessment field-help test block not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
