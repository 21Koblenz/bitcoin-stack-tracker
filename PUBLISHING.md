# Veröffentlichung v0.21.0.6 über GitHub

1. Finales Projekt und `CHANGELOG.md`, `RELEASE-NOTES.md`, `AUDIT-v0.21.0.6.md` prüfen.
2. Sicherstellen, dass das Tor Gateway weiterhin `v0.21.0.3` meldet.
3. Versionsgleichheit prüfen:
   - `VERSION.txt` = `0.21.0.6`
   - `custom_components/bitcoin_stack_tracker/manifest.json` = `0.21.0.6`
   - `custom_components/bitcoin_stack_tracker/const.py` = `0.21.0.6`
   - Frontend `BUILD_VERSION` = `0.21.0.6`
4. Änderungen auf `main` veröffentlichen.
5. Git-Tag **exakt `v0.21.0.6`** auf diesem Commit erstellen.
6. Release-Titel: `Bitcoin Stack Tracker v0.21.0.6 – Calculation, Privacy & Performance Audit`.
7. Release Notes aus `RELEASE-NOTES.md` verwenden.
8. Release veröffentlichen; der bestehende Release-Asset-Workflow baut ZIP + SHA-256.

Der Tor-Gateway-Workflow darf bei diesem Integrationstag keinen neuen Gateway-Build veröffentlichen, weil dessen `config.yaml` weiter `0.21.0.3` enthält.
