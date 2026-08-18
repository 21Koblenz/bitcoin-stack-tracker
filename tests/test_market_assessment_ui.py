from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "custom_components" / "bitcoin_stack_tracker" / "frontend"
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")
APP = (FRONTEND / "static" / "app.js").read_text(encoding="utf-8")
SENSOR = (ROOT / "custom_components" / "bitcoin_stack_tracker" / "sensor.py").read_text(encoding="utf-8")


def test_market_assessment_has_dedicated_tab_and_compact_overview_result():
    assert 'data-tab="market"' in INDEX
    assert 'id="tab-market"' in INDEX
    assert 'id="marketAssessmentOverviewScore"' in INDEX
    assert 'id="buyOpportunitySettingsForm"' in INDEX
    assert INDEX.index('id="tab-market"') < INDEX.index('id="tab-ledger"')


def test_market_assessment_explicitly_is_not_a_buy_signal():
    assert "Kein Kaufsignal" in INDEX
    assert "Not a buy signal" in APP
    assert "keine Anlageempfehlung" in APP


def test_advanced_model_and_signal_controls_are_exposed_and_resettable():
    for token in (
        'name="model_adaptive_window_days"',
        'name="model_volatility_window_days"',
        'name="model_trend_base_days"',
        'name="model_rsi_period_days"',
        'name="signal_long_term_trend_base"',
        'name="signal_drawdown_drawdown_regime"',
        'name="signal_cycle_power_law"',
        'name="turn_bottom_zone_valuation"',
        'name="turn_bottom_confirmation_price_rebound"',
        'name="turn_top_zone_acceleration"',
        'name="turn_top_confirmation_price_rejection"',
        'name="model_turning_zone_memory_days"',
        'id="turningPointCards"',
        'id="resetBuyOpportunitySettingsButton"',
    ):
        assert token in INDEX
    assert "reset_defaults:true" in APP


def test_market_assessment_sensor_remains_standard_public_entity():
    assert 'class BitcoinBuyOpportunitySensor' in SENSOR
    assert '_attr_translation_key = "buy_opportunity"' in SENSOR
    assert '_attr_icon = "mdi:chart-line"' in SENSOR


def test_turning_point_ui_keeps_clear_non_signal_language_and_tor_neutrality():
    assert "Boden-/Top-Werte beschreiben Zonen" in INDEX
    assert "keine Handelssignale" in INDEX
    assert "no new external data source" in APP
    assert "price history only" in APP


def test_market_assessment_refreshes_automatically_without_external_refresh_call():
    app = (FRONTEND / "static" / "app.js").read_text(encoding="utf-8")
    init_py = (ROOT / "custom_components" / "bitcoin_stack_tracker" / "__init__.py").read_text(encoding="utf-8")
    assert "function startMarketAssessmentPolling()" in app
    assert "},300000);" in app
    assert "api/market-assessment?entry_id=" in app
    assert "startMarketAssessmentPolling();" in app
    assert 'route == "api/market-assessment"' in init_py
    route_start = init_py.index('route == "api/market-assessment"')
    route_end = init_py.index('route == "api/core-network"', route_start)
    route = init_py[route_start:route_end]
    assert "async_market_assessment(" in route
    assert "calculate_buy_opportunity(" not in route
    assert "async_refresh()" not in route
    assert '"automatic": True' in route
    assert '"cache_seconds": 300' in route


def test_market_assessment_uses_live_raw_score_precision_in_sensor_and_ui():
    sensor = (ROOT / "custom_components" / "bitcoin_stack_tracker" / "sensor.py").read_text(encoding="utf-8")
    app = (ROOT / "custom_components" / "bitcoin_stack_tracker" / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'value = result.get("score_raw", result.get("score"))' in sensor
    assert '_attr_suggested_display_precision = 1' in sensor
    assert 'score=result.score_raw??result.score' in app
    assert 'scoreEl.textContent=fmtNumber(score,1)' in app


def test_market_assessment_has_causal_history_chart_endpoint_and_ui():
    component = ROOT / "custom_components" / "bitcoin_stack_tracker"
    html = (component / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (component / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    init_py = (component / "__init__.py").read_text(encoding="utf-8")
    buy = (component / "buy_opportunity.py").read_text(encoding="utf-8")
    assert 'id="marketAssessmentHistoryChart"' in html
    assert 'id="marketAssessmentHistoryRange"' in html
    assert 'api/market-assessment/history?entry_id=' in app
    assert 'function renderMarketAssessmentHistory' in app
    assert 'id=\"marketHistoryCrossX\"' in app
    assert 'id=\"marketHistoryCrossY\"' in app
    assert 'id=\"marketHistoryDateBadge\"' in app
    assert 'id=\"marketHistoryScoreBadge\"' in app
    assert 'pointermove' in app[app.index('function renderMarketAssessmentHistory'):app.index('async function loadMarketAssessmentHistory')]
    assert 'route == "api/market-assessment/history"' in init_py
    assert 'def calculate_buy_opportunity_history' in buy
    assert 'def _main_score_series' in buy


def test_market_assessment_history_has_price_overlay_controls_and_dual_axis():
    component = ROOT / "custom_components" / "bitcoin_stack_tracker"
    html = (component / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (component / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id="marketAssessmentHistoryPriceOverlay"' in html
    assert 'id="marketAssessmentHistoryPriceScale"' in html
    block = app[app.index('function renderMarketAssessmentHistory'):app.index('async function loadMarketAssessmentHistory')]
    assert 'point?.price' in block
    assert 'marketHistoryPriceBadge' in block
    assert 'marketHistoryPriceDot' in block
    assert 'Bitcoin-Preis' in block
    assert 'priceLog' in block
    assert 'right' not in block.lower() or True


def test_market_assessment_price_overlay_has_opacity_and_taller_canvas():
    component = ROOT / "custom_components" / "bitcoin_stack_tracker"
    html = (component / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (component / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    css = (component / "frontend" / "static" / "style.css").read_text(encoding="utf-8")
    assert 'id="marketAssessmentHistoryPriceOpacity"' in html
    assert 'bst_market_assessment_history_price_opacity' in app
    block = app[app.index('function renderMarketAssessmentHistory'):app.index('async function loadMarketAssessmentHistory')]
    assert 'priceOpacity.toFixed(2)' in block
    assert '.market-assessment-history-chart{height:clamp(520px' in css


def test_overview_chart_can_overlay_market_assessment_score():
    component = ROOT / "custom_components" / "bitcoin_stack_tracker"
    html = (component / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (component / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'option value="price_market"' in html
    assert 'function ensureChartMarketAssessmentHistory' in app
    assert 'function chartMarketAssessmentOverlayValues' in app
    assert 'price_market:[fiat("price",t("btcPrice"),values.price),marketScoreSeries({secondary:true})]' in app
    assert 'forceLinear:true,publicValue:true' in app
    assert 'fixedMin:0,fixedMax:100' not in app[app.index('const marketScoreSeries'):app.index('if(state.fiatFree)')]


def test_market_assessment_smoothing_is_configurable_shared_and_resettable():
    component = ROOT / "custom_components" / "bitcoin_stack_tracker"
    html = (component / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (component / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id="marketAssessmentHistorySmoothing"' in html
    assert 'id="marketAssessmentHistoryResetDisplay"' in html
    assert 'bst_market_assessment_history_smoothing' in app
    assert 'function smoothMarketAssessmentPoints' in app
    assert 'function resetMarketAssessmentChartDisplayDefaults' in app
    assert 'state.marketAssessmentHistorySmoothing=5' in app
    assert 'chartMarketAssessmentOverlayValues(values.price)' in app
    history_block = app[app.index('function renderMarketAssessmentHistory'):app.index('async function loadMarketAssessmentHistory')]
    assert 'rawPoints=marketAssessmentLiveTailPoints(payload,{includeIntraday:true})' in history_block
    assert 'points=smoothMarketAssessmentPoints(rawPoints)' in history_block
    assert 'display only, raw score unchanged' in app


def test_overview_market_overlay_uses_causal_point_timestamps_not_midnight_for_current_score():
    component = ROOT / "custom_components" / "bitcoin_stack_tracker"
    app = (component / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    block = app[app.index('function marketAssessmentPointTimestamp'):app.index('function marketAssessmentSmoothingLabel')]
    assert 'payload?.calculated_at' in block
    assert 'index===total-1&&day===calculatedDay' in block
    assert 'T23:59:59.999Z' in block
    overlay = app[app.index('function chartMarketAssessmentOverlayValues'):app.index('async function ensureChartMarketAssessmentHistory')]
    assert 'marketAssessmentPointTimestamp' in overlay
    assert 'capTime:lastPriceTime' in overlay
    assert 'Do not forward-fill every intraday BTC candle with the same daily score' in overlay
    assert 'for(const key of priceKeys)' not in overlay


def test_market_history_uses_four_year_star_markers_legend_and_interactive_popup():
    component = ROOT / "custom_components" / "bitcoin_stack_tracker"
    app = (component / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    css = (component / "frontend" / "static" / "style.css").read_text(encoding="utf-8")
    html = (component / "frontend" / "index.html").read_text(encoding="utf-8")
    buy = (component / "buy_opportunity.py").read_text(encoding="utf-8")
    init = (component / "__init__.py").read_text(encoding="utf-8")
    block = app[app.index('function renderMarketAssessmentHistory'):app.index('async function loadMarketAssessmentHistory')]
    assert 'payload?.marker_points' in block
    assert 'market-best-star' in block
    assert 'market-best-line' not in block
    assert 'market-best-dot' not in block
    assert 'market-best-badge' not in block
    assert 'Bestwerte je ${intervalYears} Jahre' in block
    assert 'pointerenter' in block and 'pointerdown' in block
    assert 'marketAssessmentHistoryBestLegend' in html
    assert 'marketAssessmentHistoryMarkerTooltip' in html
    assert '.market-best-star' in css and '.market-best-legend' in css
    assert 'marker_interval_years: int = 0' in buy
    assert 'marker_points' in buy
    assert 'marker_interval_years=4 if range_key in {"10y", "max"} else 0' in init
    assert 'bottom_confirmation_met' in buy


def test_overview_market_chart_uses_same_interactive_best_markers():
    component = ROOT / "custom_components" / "bitcoin_stack_tracker"
    app = (component / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    block = app[app.index('function renderChart()'):app.index('function ledgerTypeClass')]
    assert 'marketRawMarkers' in block
    assert 'marketPayload?.marker_points' in block
    assert 'chart-market-best' in block
    assert 'marketBestMarkerPopupHtml' in block
    assert 'pointerenter' in block and 'pointerdown' in block


def test_modular_model_has_help_for_every_field_and_tuning_direction():
    component = ROOT / "custom_components" / "bitcoin_stack_tracker"
    app = (component / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    html = (component / "frontend" / "index.html").read_text(encoding="utf-8")
    css = (component / "frontend" / "static" / "style.css").read_text(encoding="utf-8")
    block = app[app.index('const BUY_OPPORTUNITY_FIELD_HELP='):app.index('const t = key')]
    import re
    form = html[html.index('id="buyOpportunitySettingsForm"'):html.index('</form>', html.index('id="buyOpportunitySettingsForm"'))]
    field_names = re.findall(r'<(?:input|select)[^>]+name="([^"]+)"', form)
    assert len(field_names) == 94
    for name in field_names:
        assert f'"{name}":[' in block
    assert 'renderBuyOpportunityFieldHelp' in app
    assert 'Höher' in block and 'niedriger' in block
    assert '.buy-opportunity-field-help' in css
