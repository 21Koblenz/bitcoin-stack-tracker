# Publishing v0.21.0.10 on GitHub

## Repository update

1. Replace the repository contents with the prepared v0.21.0.10 drop-in while preserving your Git metadata.
2. Remove obsolete hashed frontend assets from the current v0.21.0.9 tree; see the external cleanup list shipped with the release package.
3. Remove the old root release helper files:
   - `GITHUB-RELEASE-v0.21.0.9.md`
   - `RELEASE-QC-v0.21.0.9.md`
4. Add the new files:
   - `GITHUB-RELEASE-v0.21.0.10.md`
   - `RELEASE-QC-v0.21.0.10.md`
   - `custom_components/bitcoin_stack_tracker/wallet_watch.py`
   - new v021010 hashed frontend assets
5. Confirm versions:
   - `VERSION.txt` = `0.21.0.10`
   - `custom_components/bitcoin_stack_tracker/manifest.json` = `0.21.0.10`
   - `custom_components/bitcoin_stack_tracker/const.py` = `0.21.0.10`
   - frontend `BUILD_VERSION` = `0.21.0.10`
6. Run the release tests/integrity checks and commit.

## GitHub release

- Tag: **`v0.21.0.10`**
- Suggested title: **Bitcoin Stack Tracker v0.21.0.10 — Sats Sentinel & Adaptive Market Assessment**
- Release text: [`GITHUB-RELEASE-v0.21.0.10.md`](GITHUB-RELEASE-v0.21.0.10.md)
- Release asset: `bitcoin-stack-tracker-home-assistant-v0.21.0.10.zip`
- Checksum asset: `bitcoin-stack-tracker-home-assistant-v0.21.0.10.zip.sha256`

This is a normal semantic version increment, so the existing `v0.21.0.9` release/tag remains untouched as release history.
