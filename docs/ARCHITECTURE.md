# Architecture and trust boundaries

This document is a contributor-oriented map of Bitcoin Stack Tracker. It is intentionally shorter than the implementation and focuses on where data lives, where network traffic may go and which code paths are performance-sensitive.

## Components

### Home Assistant integration

`custom_components/bitcoin_stack_tracker/` owns configuration, coordinators, portfolio calculations, historical public market data, the market-assessment model, encrypted storage and authenticated panel/API endpoints.

### Native frontend

`custom_components/bitcoin_stack_tracker/frontend/` is served by Home Assistant. The native panel communicates with the integration through authenticated Home Assistant/RPC paths. Static asset filenames are stable; query-string revisions perform cache busting.

### Sats Sentinel

Sats Sentinel is watch-only. It monitors public Bitcoin addresses and supported XPUB/descriptor-derived addresses. It does not need and must never store spend-capable secrets such as seeds, private keys or xprv values.

The portfolio vault and the watch-only locked-runtime catalogue are separate security concerns. The locked dashboard hides Sentinel details by default, while monitoring and enabled notifications may continue.

### Tor Gateway

`bitcoin_stack_tracker_dashboard/` provides the optional Tor Gateway app used for public outbound traffic. Public requests are fail-closed: absence/failure of Tor must not silently become direct clearnet access. Explicit validated LAN/private endpoints are the separate local-direct case.

## Network boundary

`network.py` is the central routing guard. New public providers must use the routed-session/Tor path rather than constructing an independent `aiohttp` session. Redirect targets must be validated and must not create a route bypass.

Provider requests should contain only the public information needed for the request. Wallet identifiers, portfolio values, addresses, XPUBs/descriptors and vault data do not belong in market-provider requests.

## Storage boundary

Private portfolio/watch configuration and public market/model caches have different sensitivity. Public historical price/assessment caches must not become an accidental container for wallet data.

High-frequency public caches are bounded and pruned. Writes should be coalesced when practical so five-minute in-memory updates do not produce five-minute full-store rewrites.

## Market assessment

The current assessment is intentionally shared and cached because the calculation is CPU-heavy. Multiple open dashboards must not multiply model work. Current model calculations run in Home Assistant's executor and use a bounded five-minute cadence.

Daily historical scores use a persistent generation/signature cache. The recent five-minute cache stores live observations and may reconstruct the previous 90 days from real five-minute OHLC closes. Reconstruction is causal and throttled; backfilled points are marked and never override an observed live point in the same bucket.

## Frontend performance

The frontend should request only the data needed for the current view, reuse derived calculations and avoid layout work for hidden sections. Large chart histories should be downsampled for display without destroying the underlying stored history.

Browser QR decoding must be local. Do not upload camera frames to an external scanning service merely to support a browser that lacks `BarcodeDetector`.

## Security-sensitive review areas

Changes deserve extra review when they touch:

- `network.py`, proxy/Tor handling, redirect validation or public providers;
- vault encryption/unlock/expiry and locked-state endpoints;
- Sats Sentinel address derivation or persistence;
- authentication/owner checks, CSP, iframe permissions or `no-store` headers;
- import/export and backup data;
- new dependencies or vendored browser code;
- background tasks, high-frequency polling and Home Assistant Store writes.

## Release contract

`CHANGELOG.md` is the single release history. `SECURITY.md`, `INSTALLATION.md`, `CSV-IMPORT.md`, `DATA-PORTABILITY.md`, `STORAGE.md`, `TOR-HINWEISE.md` and this architecture document provide focused current documentation. Historical generated release/QC drafts should not accumulate in the repository.
