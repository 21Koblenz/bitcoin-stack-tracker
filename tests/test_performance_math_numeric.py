from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_frontend_performance_math_against_numeric_golden_cases() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed in this test environment")
    subprocess.run(
        [node, str(ROOT / "tests" / "performance_math_test.js")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
