from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "custom_components/bitcoin_stack_tracker/frontend"
APP = (FRONTEND / "static/app-v021006-733b783d.js").read_text(encoding="utf-8")
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")


def test_chart_has_independent_left_and_right_scale_controls():
    assert 'id="chartScaleLeftButton"' in INDEX
    assert 'id="chartScaleRightButton"' in INDEX
    assert 'bst_chart_scale_left' in APP
    assert 'bst_chart_scale_right' in APP
    assert 'function chartAxisScale(index)' in APP
    assert 'const logarithmic = index =>' in APP
    assert 'logarithmic(0)?t("logarithmic")' in APP
    assert 'logarithmic(1)?t("logarithmic")' in APP


def test_signed_series_only_blocks_its_own_log_axis():
    assert 'const logBlocked = Boolean(item?.allowNegative);' in APP
    assert 'if (logBlocked && chartAxisScale(index) === "log") setChartAxisScale(index,"linear")' in APP
    assert 'const signedSeries = series.some' not in APP


def test_large_chart_and_ledger_ui_use_revision_caches():
    assert 'const chartTimestampCache = new Map();' in APP
    assert 'derivedCacheKey("chartTimeline"' in APP
    assert 'derivedCacheKey("chartSeries"' in APP
    assert 'function uiIndexes()' in APP
    assert 'matchesBySale=new Map()' in APP
    assert 'openLotByEntry=new Map(' in APP
    assert 'const points = sortedNumericPoints(values);' in APP
