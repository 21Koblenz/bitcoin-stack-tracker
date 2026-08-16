from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_sats_sentinel_runtime_selftest():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "sentinel_e2e_selftest.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    for marker in (
        "PASS: ZPUB save/derive",
        "PASS: restart cache persists Fulcrum + derived addresses",
        "PASS: Receive/Change gap-limit discovery through full config activation",
        "PASS: Fulcrum server.version before delete",
        "PASS: Fulcrum self-signed TLS certificate pin",
        "PASS: saved-monitor TX overview",
        "PASS: monitor delete + journal purge",
        "PASS: Fulcrum source unchanged/reachable after delete",
        "PASS: unlimited history uses page mode",
        "PASS: watch target upsert is immediately backend-visible",
        "PASS: unchanged Fulcrum poll uses subscribe-only fast path",
        "PASS: stale balance reconciliation avoids history reload",
        "PASS: lightweight status keeps per-monitor balance/count aggregates without addresses",
    ):
        assert marker in result.stdout
