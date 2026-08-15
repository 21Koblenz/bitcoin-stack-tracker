# Veröffentlichung des aktualisierten v0.21.0.9-Builds über GitHub

Dieser Stand behält bewusst **v0.21.0.9**. Auf GitHub existiert bereits ein Release/Tag mit derselben Version. Wenn **Immutable Releases nicht aktiviert** sind, kann das alte Release entfernt, der alte Tag gelöscht/neu gesetzt und `v0.21.0.9` auf dem neuen Release-Commit veröffentlicht werden. Falls Immutable Releases für das Repository aktiviert sind, lässt GitHub einen gelöschten immutable Release-Tag nicht unter demselben Namen wiederverwenden; dann wäre ein neuer Versions-/Tagname technisch erforderlich.

## Vor dem Commit

1. Alte Hash-Assets aus Git entfernen; siehe [`GIT-CLEANUP-v0.21.0.9.md`](GIT-CLEANUP-v0.21.0.9.md).
2. Den Inhalt des neuen GitHub-Release-ZIPs in den lokalen Repository-Checkout übernehmen.
3. Versionsgleichheit prüfen:
   - `VERSION.txt` = `0.21.0.9`
   - `custom_components/bitcoin_stack_tracker/manifest.json` = `0.21.0.9`
   - `custom_components/bitcoin_stack_tracker/const.py` = `0.21.0.9`
   - Frontend `BUILD_VERSION` = `0.21.0.9`
   - Frontend `FRONTEND_BUILD` = `021009`
4. Cache-sichere Frontend-Dateien des aktualisierten Builds:
   - `frontend/panel-v021009-ae7b9cb3.js`
   - `frontend/index-v021009-cacd75ff.html`
   - `frontend/static/app-v021009-bba91c83.js`
   - `frontend/static/style-v021009-c577172d.css`
   - `frontend/static/performance-math-v021006-733b783d.js` bleibt unverändert erhalten.
5. Finaler lokaler Stand: **457 Tests + 8 Subtests bestanden**, Python-Compile, JavaScript-Syntax, JSON/YAML und Versionskonsistenz geprüft.
6. Das Tor Gateway bleibt **v0.21.0.3**.

## Commit / GitHub

1. Änderungen auf `main` pushen und den Workflow **Validate** vollständig grün abwarten.
2. Das bestehende GitHub-Release `v0.21.0.9` löschen, wenn der aktualisierte Build exakt dieselbe Versionsnummer behalten soll.
3. Den bisherigen Git-Tag `v0.21.0.9` entfernen und **auf dem neuen finalen Commit** erneut erstellen/pushen.
4. Neues Release für Tag **`v0.21.0.9`** veröffentlichen.
5. Release-Titel:
   `Bitcoin Stack Tracker v0.21.0.9 – Sats Sentinel & Adaptive Market Assessment`
6. Release-Text aus [`GITHUB-RELEASE-v0.21.0.9.md`](GITHUB-RELEASE-v0.21.0.9.md) verwenden.
7. Der Workflow **Publish release assets** erzeugt danach automatisch:
   - `bitcoin-stack-tracker-home-assistant-v0.21.0.9.zip`
   - `bitcoin-stack-tracker-home-assistant-v0.21.0.9.zip.sha256`

## HACS-Hinweis

Da die Versionsnummer nicht erhöht wird, kann HACS bei Installationen, die bereits **0.21.0.9** melden, keinen normalen Versionssprung erkennen. Für diese Installationen **Redownload / Neu herunterladen** verwenden oder die Integration neu installieren und Home Assistant Core vollständig neu starten.

## Tor Gateway

Der Tor-Gateway-Workflow darf bei diesem Integrationstag keinen neuen Gateway-Build veröffentlichen, solange `bitcoin_stack_tracker_dashboard/config.yaml` weiterhin `0.21.0.3` enthält. Der vorhandene Workflow prüft dies anhand des Tag-/Gateway-Versionsvergleichs.
