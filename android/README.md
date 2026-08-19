# Bitcoin Stack Tracker for Android

Native Android port of Bitcoin Stack Tracker. This directory is intentionally separate from the Home Assistant integration so the existing installation remains unchanged while the Android client is developed and audited.

## Security contract

The Android app must preserve the tracker network policy instead of becoming a generic WebView wrapper:

- Public and `.onion` destinations use the bundled Tor runtime only.
- There is no automatic direct-Clearnet fallback when Tor is unavailable.
- Public non-onion targets require HTTPS with certificate verification.
- Explicitly configured own private/LAN nodes may connect directly.
- Private/LAN targets are never silently sent to a public provider.
- Public hostnames are resolved through Tor; a direct local transport must revalidate DNS results as private/local before opening a socket.
- Redirects must be disabled or re-routed through the same policy before following them.
- If Tor is unavailable, the app remains usable from encrypted local/cache data and explicitly configured local nodes only.

The Home Assistant gateway can additionally enforce egress with nftables. A normal Android APK cannot reproduce that kernel boundary by itself. This first foundation therefore treats one audited routing layer as the only allowed network entry point. A production release must add and test the Android-side egress/leak guard (for example a dedicated `VpnService` design) before claiming an OS-level killswitch equivalent.

## Privacy contract

- Bitcoin-only; no ads, analytics, telemetry, cloud account or crash-tracking SDK.
- No seed words, private keys, xprv/tprv or signing capability.
- Device-bound secrets use Android Keystore AES-256-GCM and prefer StrongBox when available.
- Android Auto Backup/device-transfer backup is disabled for app data. Portable exports remain an explicit encrypted tracker feature.
- Watch-only material for Sats Sentinel is stored separately from portfolio secrets.
- Master/backup passwords must never be stored. Password-mode migration will keep Argon2id + authenticated encryption semantics from the Home Assistant implementation.

## Tor

The project pins Guardian Project Tor Android and jtorctl. The app binds to the bundled `TorService`, waits for a live SOCKS endpoint and only then permits public requests. SOCKS connections use an unresolved destination so name resolution happens on the Tor side.

## Android platform

- `compileSdk` / `targetSdk`: 37
- minimum Android: API 28
- Java: 17
- UI: Jetpack Compose
- local network access: Android 17's `ACCESS_LOCAL_NETWORK` is declared and must only be requested when the user actually configures/uses a local node.

## Migration order

1. Native shell, Tor runtime, fail-closed routing policy, Keystore vault.
2. Encrypted local data model, ledger, fees, FIFO and portable backup compatibility.
3. Portfolio/stack overview, targets, history, market assessment and performance analytics.
4. Sats Sentinel watch-only engine with address/XPUB/descriptor sources, local Electrum/Fulcrum/electrs/Mempool and Tor public sources.
5. CSV imports and editable ledger workflow.
6. Background monitoring/notifications, Tor isolation rotation, leak tests, reproducible release pipeline and security audit.

## Current status

This branch is a security-first foundation, not a production release yet. It deliberately establishes the boundaries that later feature code must use rather than porting the large frontend first and trying to retrofit privacy afterwards.
