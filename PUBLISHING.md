# Publishing v0.21.0.12 on GitHub

## Repository update

1. Copy/overlay the prepared **v0.21.0.12 GITHUB-DROP-IN** into the existing repository and overwrite matching files.
2. **Do not delete any frontend files.** The stable file layout introduced in v0.21.0.11 is already the permanent layout.
3. Confirm `VERSION.txt`, `manifest.json`, `const.py`, frontend build/cache versions, SBOM metadata and the Sentinel User-Agent all report **0.21.0.12**.
4. Keep the older v0.21.0.11 release/QC documents as history.
5. Run validation, commit and push.

## GitHub release

- Tag: **`v0.21.0.12`**
- Suggested title: **Bitcoin Stack Tracker v0.21.0.12 — Sats Sentinel HD-Wallet Reliability**
- Release text: [`GITHUB-RELEASE-v0.21.0.12.md`](GITHUB-RELEASE-v0.21.0.12.md)
- The existing release workflow should build `bitcoin-stack-tracker-home-assistant-v0.21.0.12.zip` and its SHA-256 file when the non-prerelease GitHub Release is published.

The Tor Gateway remains **v0.21.0.3**. The integration tag does not match the gateway version, so no new Tor Gateway image should be published for v0.21.0.12.
