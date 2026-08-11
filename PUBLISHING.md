# Veröffentlichung v0.21.0.5 über GitHub

Dieser Release ist ein **Integrations-Hotfix**. Das Tor Gateway bleibt auf **v0.21.0.3**.

1. Geänderte Dateien auf `main` hochladen.
2. Alte v0.21.0.4 Cache-Busting-Assets löschen (siehe `DELETE-OLD-FILES.txt` im Changed-Files-Paket).
3. Prüfen:
   - `VERSION.txt` = `0.21.0.5`
   - `custom_components/bitcoin_stack_tracker/manifest.json` = `0.21.0.5`
   - `custom_components/bitcoin_stack_tracker/const.py` = `0.21.0.5`
   - Frontend `BUILD_VERSION` = `0.21.0.5`
4. Tag `v0.21.0.5` auf `main` erstellen.
5. Release-Titel: `Bitcoin Stack Tracker v0.21.0.5 Hotfix`.
6. Release veröffentlichen.

Der Release-Asset-Workflow erzeugt ZIP und SHA-256.
