# Documentation map

The repository keeps the project-facing documentation small and current. Release history lives in one place: [`CHANGELOG.md`](../CHANGELOG.md), newest version first.

## Current documents

- [README](../README.md) — project overview and installation entry points
- [Contributing](../CONTRIBUTING.md) — development workflow, privacy/security invariants and PR expectations
- [Architecture](ARCHITECTURE.md) — components, trust boundaries, networking, storage and performance-sensitive paths
- [Installation](../INSTALLATION.md)
- [CSV import](../CSV-IMPORT.md)
- [Data portability](../DATA-PORTABILITY.md)
- [Security](../SECURITY.md)
- [Storage](../STORAGE.md)
- [Tor notes](../TOR-HINWEISE.md)
- [Publishing](../PUBLISHING.md)
- [Changelog](../CHANGELOG.md) — single release history, newest to oldest
- [SBOM](../SBOM.md)

## Engineering references

- `audits/` — current technical/math audits
- `testing/` — manual and model test notes
- `archive/audits/` — historical audit snapshots
- `archive/maintenance/` — historical repository-maintenance notes

Per-version GitHub release drafts and release-QC copies are intentionally not kept as separate repository documents. GitHub release text should be generated from the matching `CHANGELOG.md` section so release history has one source of truth.
