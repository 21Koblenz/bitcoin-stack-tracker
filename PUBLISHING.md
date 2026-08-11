# Veröffentlichung v0.21.0.7 über GitHub

1. Finales Projekt sowie `CHANGELOG.md`, `RELEASE-NOTES.md` und `CSV-IMPORT.md` prüfen.
2. Sicherstellen, dass das Tor Gateway weiterhin `v0.21.0.3` meldet.
3. Versionsgleichheit prüfen:
   - `VERSION.txt` = `0.21.0.7`
   - `custom_components/bitcoin_stack_tracker/manifest.json` = `0.21.0.7`
   - `custom_components/bitcoin_stack_tracker/const.py` = `0.21.0.7`
   - Frontend `BUILD_VERSION` = `0.21.0.7`
   - Frontend `FRONTEND_BUILD` = `021007-050b734c`
4. Alten Frontend-Cache-Asset `custom_components/bitcoin_stack_tracker/frontend/static/app-v021006-733b783d.js` aus dem Repository entfernen; v0.21.0.7 verwendet `app-v021007-050b734c.js`.
5. Lokal Tests und Syntaxprüfung ausführen.
6. Änderungen auf `main` veröffentlichen und den GitHub-Workflow **Validate** vollständig grün abwarten.
7. Git-Tag **exakt `v0.21.0.7`** auf diesem Commit erstellen.
8. Release-Titel: `Bitcoin Stack Tracker v0.21.0.7 – Bitpanda CSV & Fee Hotfix`.
9. Release Notes aus `RELEASE-NOTES.md` verwenden.
10. Release veröffentlichen; der bestehende Release-Asset-Workflow baut ZIP + SHA-256.

Der Tor-Gateway-Workflow darf bei diesem Integrationstag keinen neuen Gateway-Build veröffentlichen, solange dessen `config.yaml` weiter `0.21.0.3` enthält.
