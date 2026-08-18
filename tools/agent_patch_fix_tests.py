from pathlib import Path

root = Path(__file__).resolve().parents[1]

# Keep the focused rating regression structural instead of depending on one
# exact optional-chaining spelling in minified-ish frontend code.
reg = root / "tests" / "test_xpub_backfill_rating_regressions.py"
text = reg.read_text(encoding="utf-8")
text = text.replace(
    'W=(C/"wallet_watch.py").read_text();A=(C/"frontend"/"static"/"app.js").read_text();I=(C/"__init__.py").read_text();B=(C/"buy_opportunity.py").read_text();M=(C/"market_assessment_backfill.py").read_text()',
    'W=(C/"wallet_watch.py").read_text();A=(C/"frontend"/"static"/"app.js").read_text();H=(C/"frontend"/"index.html").read_text();I=(C/"__init__.py").read_text();B=(C/"buy_opportunity.py").read_text();M=(C/"market_assessment_backfill.py").read_text()',
)
start = text.find("def test_labels():")
if start < 0:
    raise RuntimeError("generated rating regression missing")
new = '''def test_labels():
 assert "score_affecting_settings" in B
 assert "label_extreme" in H
 assert "labels" in B
 assert "BUY_OPPORTUNITY_LABELS_SCHEMA" in I
'''
text = text[:start] + new
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
