# Release QC · Bitcoin Stack Tracker v0.21.0.12

## Scope

Final v0.21.0.12 release with the tested non-blocking HD-wallet save path plus final watch-card balance synchronization.

Covered fixes:
- independent Receive and Change gap-limit discovery;
- all used HD addresses remain active plus the configured consecutive-unused gap;
- active-address-only balance/UTXO/TX coverage;
- privacy-safe per-monitor lightweight status aggregates;
- Fulcrum/Electrum and encrypted runtime-state restart persistence;
- vault reactivation of saved addresses/XPUB/YPUB/ZPUB/descriptors after unlock;
- non-blocking XPUB/descriptor save with background HD discovery;
- stale background scan supersession;
- watch-card Balance synchronization with Current wallet balance from the loaded transaction overview;
- stable frontend filenames with no recurring GitHub cleanup.

## Version consistency

- Integration / `VERSION.txt`: **0.21.0.12**
- Manifest: **0.21.0.12**
- Frontend build/cache version: **0.21.0.12**
- Tor Gateway: **0.21.0.3 unchanged**

## Validation

- Pytest collection: **502 tests**
- Pytest result: **502 passed**
- Pytest-reported subtests: **8 passed**
- Separate Node performance-math numeric test: **passed**
- Python compile: passed
- JavaScript syntax: passed
- JSON/SBOM parse: passed
- Frontend release-integrity checks: passed
- Dedicated Sentinel save/gap/restart/balance regression group: passed

## Privacy invariants

- Raw XPUB/YPUB/ZPUB/descriptor secrets remain in the password-protected vault.
- Device-bound runtime cache contains concrete pre-derived addresses, not raw HD public keys/descriptors.
- Lightweight status exposes aggregate counts/balances and does not expose concrete derived addresses.
- Explicit own Sentinel sources remain fail closed.

## Release layout

Stable frontend files only:
- `frontend/index.html`
- `frontend/panel.js`
- `frontend/static/app.js`
- `frontend/static/style.css`
- `frontend/static/performance-math.js`

No version/hash frontend files are generated. **No frontend cleanup is required for v0.21.0.12.**
