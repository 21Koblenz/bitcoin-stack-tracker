# Bitcoin Stack Tracker Tor Gateway v0.21.0.3

**ONLY TOR · FAIL CLOSED**

Das **Bitcoin Stack Tracker Tor Gateway** ist der abgeschottete Netzwerk-Baustein für den Bitcoin Stack Tracker in Home Assistant. Es stellt Tor als internen SOCKS5-Dienst bereit und verhindert mit einem nftables-Killswitch, dass öffentliche Preis- oder Historienabfragen direkt ins Clearnet ausweichen.

> Das Gateway verarbeitet **keine Portfolio-, Kauf-, Verkaufs-, Depot- oder Tresordaten**. Die eigentliche Benutzeroberfläche und die persönlichen Tracker-Daten liegen in der Home-Assistant-Custom-Integration.

## Was die App macht

- stellt Tor für öffentliche Bitcoin-Kurs- und Historienabfragen bereit
- erzwingt **Fail Closed** mit nftables und Default-Drop
- stellt einen eigenen internen SOCKS5-Pfad für Bitcoin Stack Tracker bereit
- bietet optional einen getrennten internen Tor-SOCKS-Port für andere Home-Assistant-Apps
- liefert einen internen Health-Endpunkt für den Supervisor-Watchdog
- erstellt eine Runtime-SBOM für die laufende App

```text
Home Assistant Core
        │
        ├── ausdrücklich konfigurierte lokale Node
        │             └── direkt im privaten LAN
        │
        └── öffentliche Datenquelle
                      │
                      ▼
               SOCKS5 :9050
                      │
                      ▼
                     Tor
                      │
                      ▼
                 Internet/API
```

## Datenschutz durch Trennung

Das Tor Gateway enthält ausdrücklich **nicht**:

- Käufe oder Verkäufe
- Portfolio- oder FIFO-Daten
- Depot- oder Zielnamen
- Master- oder Backup-Passwörter
- Wallet-Seeds oder Private Keys
- CSV-Importdaten
- portable Tracker-Backups
- Home-Assistant-API-Tokens
- Docker-Socket- oder Host-Dateisystemzugriff

## Fail Closed

Beim Start richtet die App nftables-Regeln mit Default-Drop ein. Nur der Tor-Prozess darf neue öffentliche Verbindungen öffnen. Kann der Killswitch nicht eingerichtet oder verifiziert werden, startet das Gateway nicht normal.

Für öffentliche Tracker-Daten gibt es **keinen direkten Clearnet-Fallback**.

Private, Link-Local- und LAN-Ziele werden über den Tor-Egress blockiert. Lokale Nodes werden von der Home-Assistant-Integration bewusst getrennt vom öffentlichen Tor-Pfad angesprochen.

## Interne Ports

| Port | Zweck | Auf dem HA-Host veröffentlicht? |
|---|---|---|
| `9050/tcp` | Core-only Tor SOCKS5 für Bitcoin Stack Tracker | Nein |
| `9051/tcp` | geteilter interner Tor SOCKS5 für andere HA-Apps | Nein |
| `8099/tcp` | interner Health-Endpunkt für den Watchdog | Nein |

## Installation

Das Repository kann direkt zu Home Assistant hinzugefügt werden:

[![Bitcoin Stack Tracker App-Repository hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2F21Koblenz%2Fbitcoin-stack-tracker)

Danach im **App Store** die App **Bitcoin Stack Tracker Tor Gateway** installieren und starten.

Für den vollständigen Bitcoin Stack Tracker wird zusätzlich die Custom Integration benötigt:

[![Bitcoin Stack Tracker in HACS öffnen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=21Koblenz&repository=bitcoin-stack-tracker&category=integration)

## Bedienung

Das Gateway besitzt absichtlich **kein eigenes Ingress-Dashboard**. Es ist ein reiner Netzwerkdienst.

Die Oberfläche des Projekts wird von der Custom Integration als natives Home-Assistant-Seitenleistenpanel **Bitcoin Stack** bereitgestellt.

Nach einer Installation oder Aktualisierung der Custom Integration sollte Home Assistant Core vollständig neu gestartet werden.

## Bei Problemen

Wenn lokale Tracker-Daten sichtbar sind, öffentliche Kurse aber fehlen:

1. Prüfen, ob **Bitcoin Stack Tracker Tor Gateway** läuft.
2. Den Tab **Protokoll** der App öffnen.
3. Auf Tor-, SOCKS- oder nftables-Fehler prüfen.
4. Im Bitcoin Stack Tracker den Tor-/Leak-Test ausführen.
5. Im App Store über **Nach Aktualisierungen suchen** die Repository-Daten neu laden.

Ein Tor-Ausfall darf lokale Buchungen und bereits vorhandene Cache-Daten nicht zerstören. Öffentliche Live-Abfragen bleiben in diesem Fall gesperrt, bis Tor wieder verfügbar ist.

## Sicherheit

Die App fordert `NET_ADMIN` ausschließlich für die Einrichtung des nftables-Killswitches an. Sie fordert keine Home-Assistant-API-Berechtigung, keinen Docker-Socket und keinen allgemeinen Zugriff auf das Host-Dateisystem an.

Das Gateway ist bewusst klein gehalten: Tor, Killswitch, SOCKS-Endpunkte, Health-Check und die dafür notwendige Laufzeitlogik.

## Dokumentation

Ausführliche technische und praktische Hinweise stehen im Tab **Dokumentation** beziehungsweise in [`DOCS.md`](DOCS.md).

Projektübersicht und vollständige Tracker-Dokumentation: [github.com/21Koblenz/bitcoin-stack-tracker](https://github.com/21Koblenz/bitcoin-stack-tracker)

## Lizenz

Bitcoin Stack Tracker steht unter **GNU Affero General Public License v3.0 only (`AGPL-3.0-only`)**. Der vollständige Lizenztext befindet sich im Haupt-Repository.
