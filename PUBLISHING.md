# Publishing v0.21.0.11 on GitHub

## One-time frontend cleanup

The current v0.21.0.10 repository still contains five legacy version/hash-named frontend assets next to the stable files. Delete these files **once** when applying v0.21.0.11:

- `custom_components/bitcoin_stack_tracker/frontend/index-v021010-60203b9c.html`
- `custom_components/bitcoin_stack_tracker/frontend/panel-v021010-ae7b9cb3.js`
- `custom_components/bitcoin_stack_tracker/frontend/static/app-v021010-f51973f8.js`
- `custom_components/bitcoin_stack_tracker/frontend/static/performance-math-v021006-733b783d.js`
- `custom_components/bitcoin_stack_tracker/frontend/static/style-v021010-c577172d.css`

Keep the stable files `index.html`, `panel.js`, `static/app.js`, `static/style.css` and `static/performance-math.js`. From v0.21.0.11 onward, releases overwrite only these names and use `?v=<VERSION>` for cache busting. `.gitignore` blocks the legacy patterns.

## Repository update

1. Copy/overlay the prepared **v0.21.0.11 GITHUB-DROP-IN** into the existing repository and overwrite matching files. Do **not** mass-delete unrelated historical documents or Git metadata.
2. Delete only the five legacy frontend files listed above.
3. Add `GITHUB-RELEASE-v0.21.0.11.md` and `RELEASE-QC-v0.21.0.11.md`; existing older release/QC documents may remain as history.
4. Confirm `VERSION.txt`, `manifest.json`, `const.py`, frontend `BUILD_VERSION`, SBOM metadata and Sentinel User-Agent all report **0.21.0.11**.
5. Run validation, commit and push.

## GitHub release

- Tag: **`v0.21.0.11`**
- Suggested title: **Bitcoin Stack Tracker v0.21.0.11 — Sats Sentinel & Causal Market Assessment**
- Release text: [`GITHUB-RELEASE-v0.21.0.11.md`](GITHUB-RELEASE-v0.21.0.11.md)
- The existing release workflow builds `bitcoin-stack-tracker-home-assistant-v0.21.0.11.zip` and its SHA-256 file automatically when the non-prerelease GitHub Release is published.

The Tor Gateway remains **v0.21.0.3**. Its workflow sees that the integration tag does not match the gateway version and therefore does not publish a new gateway image for v0.21.0.11.
