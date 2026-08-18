from pathlib import Path
R=Path(__file__).resolve().parents[1];C=R/"custom_components"/"bitcoin_stack_tracker"
W=(C/"wallet_watch.py").read_text();A=(C/"frontend"/"static"/"app.js").read_text();H=(C/"frontend"/"index.html").read_text();I=(C/"__init__.py").read_text();B=(C/"buy_opportunity.py").read_text();M=(C/"market_assessment_backfill.py").read_text()
def test_xpub():
 assert "blockchain.scripthash.subscribe" in W and 'return "p2wpkh", False' in W and "resolved_address_type_verified" in W and "Wird ermittelt …" in A
def test_backfill():
 assert "async_market_assessment_backfill_loop" in I and "intraday_backfill" in I and "BACKFILL_SCORE_BATCH_POINTS = 2" in M and "marketAssessmentBackfillStatus" in A
def test_labels():
 assert "score_affecting_settings" in B
 assert "label_extreme" in H
 assert "labels" in B
 assert "BUY_OPPORTUNITY_LABELS_SCHEMA" in I
