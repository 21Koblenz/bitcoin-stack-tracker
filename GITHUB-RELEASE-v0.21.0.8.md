# Bitcoin Stack Tracker v0.21.0.8 — Peach Bitcoin CSV Import

Small CSV-import and documentation release.

## Changes

- Added a dedicated **Peach Bitcoin** CSV importer.
- Peach `Amount` is interpreted as **satoshis**.
- Supports the columns `Date`, `Trade ID`, `Type`, `Amount`, `Price`, `Bitcoin Price`, `Currency`, `Premium`.
- `Premium` is interpreted as a percentage; for purchases the included markup is reversed to reconstruct the reference BTC price and the difference is tracked as a fiat fee without double-counting cost basis.
- `Trade ID` is used for stable duplicate detection through the existing local hash mechanism.
- README is now fully available in **German and English**.
- `CSV-IMPORT.md` documents the Peach import format and calculation rules.
- Five targeted Peach parser regression tests pass.

## Compatibility

- Custom Integration: **v0.21.0.8**
- Tor Gateway: **v0.21.0.3** (unchanged)

**Full Changelog:** https://github.com/21Koblenz/bitcoin-stack-tracker/compare/v0.21.0.7...v0.21.0.8
