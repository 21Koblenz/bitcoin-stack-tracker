# Release QC — v0.21.0.10

## Result

- Target release: **v0.21.0.10**
- Baseline on GitHub: **v0.21.0.9**
- Tor Gateway: **v0.21.0.3** unchanged
- Version consistency: `VERSION.txt`, `const.py`, `manifest.json`, frontend build, SBOM and Sentinel User-Agent report **0.21.0.10**
- Frontend cache namespace: **v021010** with new hashed index/panel/app/style assets and `release021010-r1` query bust
- Final test suite: **457 tests + 8 subtests passed**
- Python compile: passed
- JavaScript syntax: passed
- JSON/YAML parsing: passed
- Frontend asset integrity/version references: passed

## Release-critical coverage

- Sats Sentinel source selection and explicit fail-closed behavior
- Fulcrum/electrs Electrum query path and TLS certificate pinning
- no hidden public provider fallback from an explicitly selected own source
- movement journal persistence and purge on watch-entry deletion
- UI status refresh does not overwrite unsaved Sentinel configuration
- causal market-history reconstruction without look-ahead
- EMA display smoothing remains causal and display-only
- market-history BTC-price overlay/crosshair/opacity controls
- overview Bitcoin-price + market-assessment overlay and flat-line regression
- live-price fast lane/range-refresh behavior and Tor routing boundaries

## Release note

This is a normal version increment from **v0.21.0.9** to **v0.21.0.10**. Existing HACS installations should therefore see a regular update after the new tag/release is published and HACS metadata refreshes.
