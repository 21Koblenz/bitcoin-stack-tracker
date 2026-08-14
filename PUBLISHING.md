# Veröffentlichung v0.21.0.9 über GitHub

1. Finales Projekt sowie `README.md`, `CHANGELOG.md`, `RELEASE-NOTES.md` und `CSV-IMPORT.md` prüfen.
2. Sicherstellen, dass das Tor Gateway weiterhin **v0.21.0.3** meldet.
3. Versionsgleichheit prüfen:
   - `VERSION.txt` = `0.21.0.9`
   - `custom_components/bitcoin_stack_tracker/manifest.json` = `0.21.0.9`
   - `custom_components/bitcoin_stack_tracker/const.py` = `0.21.0.9`
   - Frontend `BUILD_VERSION` = `0.21.0.9`
   - Frontend `FRONTEND_BUILD` = `021009`
4. Cache-sichere Frontend-Dateien prüfen:
   - `frontend/panel-v021009-ae7b9cb3.js`
   - `frontend/index-v021009-3c9a03c7.html`
   - `frontend/static/app-v021009-1ef3c90f.js`
   - alte `app-v021007-*`- und `panel-v021006-*`-Kopien dürfen nicht mehr im Release liegen.
5. Lokal Tests und Syntaxprüfung ausführen. Finaler lokaler Stand: **373 Tests + 8 Subtests bestanden**.
6. Änderungen auf `main` veröffentlichen und den GitHub-Workflow **Validate** vollständig grün abwarten.
7. Git-Tag **exakt `v0.21.0.9`** auf diesem Commit erstellen.
8. Release-Titel: `Bitcoin Stack Tracker v0.21.0.9 – Revolut X, Ledger & Network Fees`.
9. GitHub-Release-Text aus `GITHUB-RELEASE-v0.21.0.9.md` verwenden.
10. Release veröffentlichen; der bestehende Release-Asset-Workflow baut das vollständige ZIP plus SHA-256 aus dem Release-Tag.

Der Tor-Gateway-Workflow darf bei diesem Integrationstag keinen neuen Gateway-Build veröffentlichen, solange dessen `config.yaml` weiter `0.21.0.3` enthält.
