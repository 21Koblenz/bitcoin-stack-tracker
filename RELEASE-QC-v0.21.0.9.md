# Release QC — v0.21.0.9 updated build

## Result

**PASS**

- Full local pytest suite: **457 passed + 8 subtests passed**
- Python compile: **PASS**
- JavaScript syntax (`app.js`, hashed app asset, native panel module): **PASS**
- Version consistency: `VERSION.txt`, `const.py`, `manifest.json`, frontend build and Sentinel User-Agent report **0.21.0.9**
- Frontend cache namespace: **v021009** with replacement hashed index/app/style assets and `release021009-r2` query bust
- Sats Sentinel source-policy regressions: **PASS**
- Fulcrum/electrs Electrum path + TLS certificate pinning regressions: **PASS**
- Sentinel journal purge on watch deletion: **PASS**
- Status-refresh form-preservation and save/source-test feedback: **PASS**
- Market-assessment causal/no-look-ahead history regressions: **PASS**
- Market-history crosshair, BTC-price overlay, opacity and EMA smoothing regressions: **PASS**
- Overview **Bitcoin price + market assessment** overlay regression: **PASS**
- Overview flat-line fix: daily scores are not forward-filled across every intraday BTC candle and the score axis auto-scales to visible values: **PASS**

## Release scope

This updated build intentionally keeps **v0.21.0.9**. It extends the initially published v0.21.0.9 build with Sats Sentinel, configurable Fulcrum/electrs/Mempool monitoring, adaptive/historical market assessment, live/chart refresh improvements and related privacy/UI hardening.

The Bitcoin Stack Tracker Tor Gateway remains **v0.21.0.3**.

## Publishing caveat

Because `v0.21.0.9` already exists as a GitHub tag/release, publishing this replacement with the identical tag is only possible when GitHub Immutable Releases are not enabled; otherwise GitHub does not allow the deleted immutable tag name to be reused. Existing HACS installations already on `0.21.0.9` may need **Redownload** because the semantic version does not increase.
