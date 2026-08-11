# Veröffentlichung v0.21.0.4 über GitHub

Dieser Release ist ein **Integrations-Hotfix**. Die Home-Assistant-Integration wird auf **v0.21.0.4** erhöht; das Tor Gateway bleibt auf **v0.21.0.3**, weil sich dort kein Code geändert hat.

## Ablauf

1. Den vollständigen Projektstand auf `main` übernehmen.
2. Prüfen:
   - `VERSION.txt` = `0.21.0.4`
   - `custom_components/bitcoin_stack_tracker/manifest.json` = `0.21.0.4`
   - `custom_components/bitcoin_stack_tracker/const.py` = `0.21.0.4`
   - Frontend `BUILD_VERSION` = `0.21.0.4`
   - `bitcoin_stack_tracker_dashboard/config.yaml` bleibt `0.21.0.3`
3. Tag `v0.21.0.4` auf `main` erstellen.
4. GitHub Release für `v0.21.0.4` veröffentlichen.
5. `.github/workflows/release-assets.yaml` erzeugt ZIP + SHA-256 für den getaggten Stand.
6. `.github/workflows/publish-tor-gateway.yaml` erkennt, dass der Release-Tag nicht der unveränderten Gateway-Version entspricht, und veröffentlicht deshalb **kein neues Gateway-Image**.

## Release-Titel

`Bitcoin Stack Tracker v0.21.0.4 – CSV Duplicate Identity Hotfix`

## Prüfen nach Veröffentlichung

HACS soll `v0.21.0.4` als neueste Integrationsversion erkennen. Im Home-Assistant-App-Store darf für das Tor Gateway durch diesen Integrations-Hotfix kein neues `0.21.0.4`-Update erscheinen.
