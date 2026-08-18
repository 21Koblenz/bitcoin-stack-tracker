# Contributing to Bitcoin Stack Tracker

Contributions are welcome. The project is a Home Assistant custom integration plus the Sats Sentinel watch-only subsystem and the optional Tor Gateway app.

## Before you start

- Open an issue for larger behavioural changes so the privacy and compatibility impact can be discussed first.
- Keep pull requests focused. Avoid unrelated formatting or generated-file churn.
- Never commit seeds, private keys, xprv values, API tokens, real wallet exports, Home Assistant backups, `.storage` data or personally identifying logs.
- Test with disposable public addresses/XPUBs only.

## Security and privacy invariants

Changes must preserve these boundaries:

1. **No spend keys.** Sats Sentinel is watch-only. Seeds, private keys and xprv material do not belong in this project.
2. **Tor fail-closed for public internet traffic.** Public provider requests must use the bundled Tor route. Do not add a clearnet fallback.
3. **Local direct access is explicit.** Direct connections are limited to validated local/private endpoints where the feature explicitly permits them.
4. **No private telemetry.** Portfolio, wallet, address, XPUB/descriptor and vault data must not be sent to analytics, CDNs, QR services or market-data providers.
5. **Locked means private by default.** The locked dashboard must not reveal balances, addresses, wallet metadata or source configuration unless the owner explicitly enabled the local locked-Sentinel view.
6. **Sensitive HTTP responses are `no-store`.** Do not weaken CSP, authenticated RPC or owner-only management checks.
7. **Browser QR scanning stays local.** Camera frames and decoded QR payloads must remain on the device/Home Assistant installation.

If a contribution requires weakening one of these rules, describe the reason and threat-model change explicitly in the PR. Such changes should not be merged accidentally.

## Repository layout

- `custom_components/bitcoin_stack_tracker/` — Home Assistant integration/backend.
- `custom_components/bitcoin_stack_tracker/frontend/` — native panel frontend. Keep stable asset names (`index.html`, `app.js`, `style.css`, `performance-math.js`); use query-string cache revisions instead of versioned duplicate filenames.
- `bitcoin_stack_tracker_dashboard/` — optional Tor Gateway Home Assistant app.
- `tests/` — regression, security, model and frontend/static tests.
- `tools/` — release/audit/self-test tooling.
- `docs/` — engineering notes, audits and manual test references.
- `CHANGELOG.md` — the single release history, newest version first.

See `docs/ARCHITECTURE.md` for the major trust boundaries and runtime components.

## Development workflow

1. Fork or create a feature branch from current `main`.
2. Make the smallest coherent change.
3. Add/update regression tests for behavioural fixes.
4. Run the focused tests for the changed area, then the full available test suite.
5. Run JavaScript syntax checks for changed frontend files and Python compile/tests for backend changes.
6. Confirm no new direct public network path, secret persistence or sensitive logging was introduced.
7. Open a pull request and complete the checklist.

## Useful validation

The repository CI runs HACS validation, hassfest and dependency-security checks. Contributors should also run the repository tests locally when possible.

For frontend changes, at minimum verify `app.js` and `panel.js` parse successfully and test both desktop and mobile layouts. For Sats Sentinel changes, test locked and unlocked states. For network changes, test both normal Tor operation and fail-closed behaviour when Tor is unavailable.

## Market-assessment changes

The score is a market assessment, not a trading signal. Historical calculations must remain causal: a historical point may not use market data from a later date. Expensive score work belongs outside the Home Assistant event loop and should be cached/throttled.

Five-minute backfilled points are reconstructed from real historical OHLC closes; they must stay distinguishable from live observations, and live observations take precedence for the same bucket.

## Documentation and releases

- Update `CHANGELOG.md` for user-visible changes. Keep the newest version at the top.
- Do not create per-version `GITHUB-RELEASE-*.md`, `RELEASE-QC-*.md` or duplicate release-note files in the repository.
- GitHub release text can be generated from the relevant `CHANGELOG.md` section at release time.
- Keep README concise; put engineering details in focused files under `docs/`.

## Style

Prefer straightforward code, explicit bounds and fail-closed behaviour over clever shortcuts. Avoid blocking the Home Assistant event loop. Keep comments focused on non-obvious security, privacy, performance and compatibility decisions.
