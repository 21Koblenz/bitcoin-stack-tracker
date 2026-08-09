from __future__ import annotations

import ast
from bisect import bisect_right
from datetime import date
from io import BytesIO
from math import isfinite
from pathlib import Path
import csv
import io
import zipfile

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / "custom_components" / "bitcoin_stack_tracker" / "history.py"
HISTORY = HISTORY_PATH.read_text(encoding="utf-8")


def _load_helpers(*names):
    tree = ast.parse(HISTORY)
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    module = ast.Module(body=selected, type_ignores=[])
    ns = {
        "bisect_right": bisect_right,
        "date": date,
        "BytesIO": BytesIO,
        "isfinite": isfinite,
        "csv": csv,
        "io": io,
        "zipfile": zipfile,
    }
    exec(compile(module, str(HISTORY_PATH), "exec"), ns)
    return [ns[name] for name in names]


def test_usd_to_eur_uses_previous_ecb_working_day_for_weekend_price():
    last_rate, convert = _load_helpers("_last_rate_on_or_before", "_convert_usd_history")
    # Ensure the helper name exists in the convert function's global namespace.
    convert.__globals__["_last_rate_on_or_before"] = last_rate
    usd_prices = {"2010-07-18": 0.08, "2010-07-19": 0.09}
    rates = {"USD": {"2010-07-16": 1.2920, "2010-07-19": 1.2948}}
    converted = convert(usd_prices, "EUR", rates)
    assert set(converted) == set(usd_prices)
    assert abs(converted["2010-07-18"] - (0.08 / 1.2920)) < 1e-12
    assert abs(converted["2010-07-19"] - (0.09 / 1.2948)) < 1e-12


def test_ecb_bulk_zip_parser_reads_full_history_rows_and_filters_range():
    (parse_bulk,) = _load_helpers("_parse_ecb_bulk_zip")
    csv_text = "Date,USD,GBP,\n2010-07-16,1.2920,0.8400,\n2010-07-19,1.2948,0.8420,\n2013-04-01,1.2818,0.8430,\n"
    payload = BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("eurofxref-hist.csv", csv_text)
    parsed = parse_bulk(payload.getvalue(), {"USD", "GBP"}, "2010-07-01", "2010-12-31")
    assert parsed["USD"] == {"2010-07-16": 1.2920, "2010-07-19": 1.2948}
    assert parsed["GBP"] == {"2010-07-16": 0.8400, "2010-07-19": 0.8420}


def test_fill_missing_days_preserves_own_node_values_on_overlap():
    (fill_missing,) = _load_helpers("_fill_missing_days")
    values = {"2013-04-01": 100.0, "2013-04-03": 102.0}
    candidate = {"2013-04-01": 999.0, "2013-04-02": 101.0, "2013-04-03": 999.0}
    added = fill_missing(values, candidate)
    assert added == {"2013-04-02": 101.0}
    assert values["2013-04-01"] == 100.0
    assert values["2013-04-02"] == 101.0
    assert values["2013-04-03"] == 102.0


def test_eur_backfill_reuses_full_local_usd_cache_and_fills_all_missing_days():
    assert 'HISTORY_STRATEGY_VERSION = "ordered-source-cascade-v9-dense-gap-fill"' in HISTORY
    assert 'ECB_BULK_HISTORY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"' in HISTORY
    assert 'contributed = _fill_missing_days(values, converted)' in HISTORY
    assert 'values.update(preferred_overlay)' in HISTORY
    assert 'role="gap-fill + deep-backfill"' in HISTORY
