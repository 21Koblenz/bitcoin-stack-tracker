from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "custom_components/bitcoin_stack_tracker/frontend"
APP = (FRONTEND / "static/app.js").read_text(encoding="utf-8")
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")


def test_chart_has_independent_left_and_right_scale_controls():
    assert 'id="chartScaleLeftButton"' in INDEX
    assert 'id="chartScaleRightButton"' in INDEX
    assert 'bst_chart_scale_left' in APP
    assert 'bst_chart_scale_right' in APP
    assert 'function chartAxisScale(index)' in APP
    assert 'const logarithmic = index =>' in APP
    assert 'const symlogarithmic = index =>' in APP
    assert 'chartScaleLabel(0)' in APP
    assert 'chartScaleLabel(1)' in APP


def test_signed_series_uses_symlog_on_its_own_axis():
    assert 'const logBlocked = Boolean(item?.forceLinear);' in APP
    assert 'const signedLog = Boolean(item?.allowNegative && chartAxisScale(index) === "log");' in APP
    assert 't(signedLog?"symlogarithmic":"logarithmic")' in APP
    assert 'Math.sign(numeric)*Math.log10(1+Math.abs(numeric)/threshold)' in APP
    assert 'Math.sign(numeric)*threshold*((10 ** Math.abs(numeric))-1)' in APP
    assert 'const signedSeries = series.some' not in APP


def test_large_chart_and_ledger_ui_use_revision_caches():
    assert 'const chartTimestampCache = new Map();' in APP
    assert 'derivedCacheKey("chartTimeline"' in APP
    assert 'derivedCacheKey("chartSeries"' in APP
    assert 'function uiIndexes()' in APP
    assert 'matchesBySale=new Map()' in APP
    assert 'openLotByEntry=new Map(' in APP
    assert 'const points = sortedNumericPoints(values);' in APP


def test_market_score_overlay_keeps_linear_but_auto_scaled_right_axis():
    start = APP.index('const marketScoreSeries')
    block = APP[start:APP.index('if(state.fiatFree)', start)]
    assert 'forceLinear:true,publicValue:true' in block
    assert 'fixedMin:0,fixedMax:100' not in block
    assert 'marketScoreLinearOnly' in APP
