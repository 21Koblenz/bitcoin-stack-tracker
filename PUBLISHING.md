# Veröffentlichung v0.21.0.3 über GitHub

Diese Anleitung beschreibt den regulären Hotfix-Release **v0.21.0.3** auf Basis des bestehenden öffentlichen Repositorys.

## 1. Release-Stand auf `main` übernehmen

1. Den vollständigen v0.21.0.3-Projektstand auf `main` übernehmen.
2. Prüfen, dass `README.md`, `CHANGELOG.md`, `RELEASE-NOTES.md`, `VERSION.txt`, Integration und Tor-Gateway überall v0.21.0.3 ausweisen.
3. Die vollständige Test-Suite ausführen.
4. Erst danach den Release-Tag setzen.

## 2. Release-Commit

Empfohlener Commit-Titel:

```text
CSV import and fee accounting hotfix v0.21.0.3
```

## 3. Release erstellen

1. **Releases → Draft a new release** öffnen.
2. Neuen Tag erstellen: `v0.21.0.3`.
3. Target: `main`.
4. Release-Titel: `Bitcoin Stack Tracker v0.21.0.3 – CSV Import & Fee Accounting Hotfix`.
5. Inhalt aus `RELEASE-NOTES.md` übernehmen.
6. Release veröffentlichen.

## 4. Tor-Gateway-Image

Der Workflow `.github/workflows/publish-tor-gateway.yaml` prüft, dass Tag und Gateway-Version exakt zusammenpassen. Beim Release-Tag wird das Multi-Arch-Image für `amd64` und `aarch64` nach GHCR veröffentlicht.

Nach dem Release unter **Actions** prüfen, dass der Tag-Lauf vollständig erfolgreich war.

## 5. Integrität

Für eine zusätzliche Release-ZIP kann verwendet werden:

```bash
tools/release-integrity.sh bitcoin-stack-tracker-home-assistant-v0.21.0.3.zip
```

Das Skript erzeugt mindestens eine SHA-256-Datei und optional eine Minisign-Signatur, wenn ein Publisher-Schlüssel angegeben wurde.

## 6. Automatische Release-Dateien

Beim Veröffentlichen eines normalen GitHub-Releases startet `.github/workflows/release-assets.yaml` automatisch. Der Workflow erzeugt aus exakt dem getaggten Git-Stand:

- `bitcoin-stack-tracker-home-assistant-v0.21.0.3.zip`
- `bitcoin-stack-tracker-home-assistant-v0.21.0.3.zip.sha256`

und hängt beide Dateien als Release-Assets an das bereits veröffentlichte GitHub-Release an.

Die von GitHub zusätzlich angebotenen Dateien `Source code (zip)` und `Source code (tar.gz)` sind davon unabhängig.
