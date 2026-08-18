from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "bitcoin_stack_tracker"
WALLET = (COMPONENT / "wallet_watch.py").read_text(encoding="utf-8")
APP = (COMPONENT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
HTML = (COMPONENT / "frontend" / "index.html").read_text(encoding="utf-8")
INIT = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
BUY = (COMPONENT / "buy_opportunity.py").read_text(encoding="utf-8")
BACKFILL = (COMPONENT / "market_assessment_backfill.py").read_text(encoding="utf-8")


def test_raw_xpub_auto_detection_does_not_publish_unverified_zero_balance():
    assert "blockchain.scripthash.subscribe" in WALLET
    assert 'return "p2wpkh", False' in WALLET
    assert "resolved_address_type_verified" in WALLET
    assert "Wird ermittelt …" in APP


def test_90_day_backfill_is_wired_throttled_and_visible():
    assert "async_market_assessment_backfill_loop" in INIT
    assert "intraday_backfill" in INIT
    assert "BACKFILL_SCORE_BATCH_POINTS = 2" in BACKFILL
    assert "BACKFILL_SCORE_PAUSE_SECONDS = 20" in BACKFILL
    assert "marketAssessmentBackfillStatus" in APP
    assert "Bitstamp 5m" in APP


def test_rating_names_are_editable_but_display_only():
    assert "score_affecting_settings" in BUY
    assert 'payload.pop("labels", None)' in BUY
    assert "BUY_OPPORTUNITY_LABELS_SCHEMA" in INIT
    assert "label_very_expensive" in HTML
    assert "label_extreme" in HTML
    assert "buy_opportunity_settings?.labels" in APP
