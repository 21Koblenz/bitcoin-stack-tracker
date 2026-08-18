# Release QC — v0.21.0.11

## Result

- Target release: **v0.21.0.11**
- Public baseline before this release: **v0.21.0.10**
- Tor Gateway: **v0.21.0.3** unchanged
- Version consistency: `VERSION.txt`, `const.py`, `manifest.json`, frontend build/query cache bust, SBOM and Sentinel User-Agent report **0.21.0.11**
- Frontend entrypoints: stable canonical filenames only; no `index-v*`, `panel-v*`, `app-v*`, `style-v*` or `performance-math-v*` files in the release tree
- Final Python suite: **485 tests + 8 subtests passed**
- Python compile: **passed**
- JavaScript syntax (`app.js`, `panel.js`): **passed**
- JSON parsing (`manifest.json`, `SBOM.cdx.json`): **passed**
- Performance-math numeric JavaScript test: **passed**

## Release-critical coverage

- causal market-history reconstruction without look-ahead
- true unsampled best raw-score retention in displayed history
- independent best-score markers per 4-year window for `10 years` / `Max`
- causal post-marker bottom confirmation inside the configured zone-memory window
- independent confirmation association for multiple 4-year markers
- shared market-star markers in the historical and overview charts
- desktop hover and touch/pointer marker popup behavior
- compact permanent best-marker legend under the historical chart
- help text for all modular market-model inputs
- Sats Sentinel top-level panel collapse/expand behavior
- per-portfolio persistence of the Sentinel panel layout in browser storage
- stable frontend filenames and version-query cache busting
- `.gitignore` protection against legacy version/hash frontend bundles
- Sats Sentinel fail-closed source selection and no hidden public fallback
- Fulcrum/electrs/TLS pinning, journal persistence/purge and watch-only privacy boundaries
- live-price/range-refresh and Tor-routing regression coverage

## Bottom-confirmation correction

The market score marker represents the highest causal raw score in its selected window. Confirmation evidence can naturally arrive after that stress day (for example via rebound, divergence or trend reclaim). v0.21.0.11 therefore keeps the marker date unchanged and searches forward only within the configured `turning_zone_memory_days` window. Each candidate day is calculated strictly as-of that day. This changes the **association/visual diagnosis**, not the historical raw-score calculation and not the default thresholds.

## Frontend migration

The v0.21.0.11 repository tree contains only the stable frontend files. Existing legacy version/hash files in the live GitHub repository must be deleted once during migration. Exact paths are documented in [`PUBLISHING.md`](PUBLISHING.md). Future releases do not require this cleanup.
