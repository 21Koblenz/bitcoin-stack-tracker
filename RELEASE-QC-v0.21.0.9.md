# Release QC — v0.21.0.9

## Result

**PASS**

- Full local pytest suite: **373 passed + 8 subtests passed**
- Targeted Revolut X / reference-price / ledger-math / Peach regression set: **19 passed**
- Python compile: PASS
- JavaScript syntax: PASS
- JSON/YAML parse: PASS
- Version consistency: `VERSION.txt`, `const.py`, `manifest.json` and frontend build all report **0.21.0.9**
- Frontend cache assets: v0.21.0.9 panel/index/app paths active; obsolete v0.21.0.7 app and v0.21.0.6 panel copies removed
- Generated `__pycache__` / `.pyc` files removed from release

## Scope

QC covers the v0.21.0.9 changes: Revolut X CSV import, manual income/expense/network-fee bookings, editable booking type with FIFO revalidation, historical plausibility warning, overview labels/summaries and new chart ranges.

The Tor Gateway remains **v0.21.0.3** and is not changed by this release.
