from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "bitcoin_stack_tracker"
RUNTIME = (COMPONENT / "market_assessment_runtime.py").read_text(encoding="utf-8")
BACKFILL = (COMPONENT / "market_assessment_backfill.py").read_text(encoding="utf-8")


def test_market_reads_do_not_spawn_backfill():
    assert "async_market_assessment_backfill_loop" not in RUNTIME
    assert "throttled market assessment backfill" not in RUNTIME
    assert "_ensure_backfill" not in RUNTIME


def test_backfill_worker_is_background_only():
    assert "async_create_background_task" in BACKFILL
    assert "waiting_for_home_assistant" in BACKFILL
    assert "waiting_for_tor_gateway" in BACKFILL
