# Bitcoin Stack Tracker Tor Gateway v0.21.0.0

Das **Bitcoin Stack Tracker Tor Gateway** ist ausschließlich der Netzwerk-/Tor-Baustein des Bitcoin Stack Trackers. Die eigentliche Benutzeroberfläche und die Portfolio-Daten liegen in der Home-Assistant-Custom-Integration.

Der Ordnername `bitcoin_stack_tracker_dashboard` bleibt aus Upgrade-Kompatibilitätsgründen bestehen.

## Aufgaben

- Tor für öffentliche Preis- und Historienabfragen
- nftables Fail-Closed-Killswitch
- interner SOCKS5-Port `9050` für Home Assistant Core / Bitcoin Stack Tracker
- optional geteilter interner SOCKS5-Port `9051` für andere Home-Assistant-Apps
- interner Health-Endpunkt `8099` für den Supervisor-Watchdog
- Runtime-SBOM

## Bewusste Trennung

Das Gateway enthält ausdrücklich **nicht**:

- Portfolio oder Kaufbuch
- Ledger-/FIFO-Daten
- Depot- oder Zielnamen
- Master- oder Backup-Passwörter
- CSV-Parser oder Backup-/Restore-Logik
- Home-Assistant-API-Token
- Docker-Socket- oder Host-Dateisystemzugriff

```text
Home Assistant Core
        │
        ├── ausdrücklich konfigurierte lokale Node → direkt im privaten LAN
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

## Fail Closed

Das Gateway richtet beim Start nftables-Regeln mit Default-Drop ein. Nur der Tor-Prozess darf neue öffentliche Verbindungen öffnen. Kann der Killswitch nicht eingerichtet oder bestätigt werden, startet das Gateway nicht normal. Für öffentliche Tracker-Daten gibt es keinen direkten Clearnet-Fallback.

Private, Link-Local- und LAN-Ziele sind über den Tor-Egress blockiert. Dadurch kann auch der geteilte SOCKS-Port `9051` nicht als Proxy in das private Netzwerk verwendet werden.

## Interne Ports

- `9050/tcp` – Core-only Tor SOCKS5 für Bitcoin Stack Tracker
- `9051/tcp` – geteilter interner Tor SOCKS5 für andere Home-Assistant-Apps
- `8099/tcp` – interner Health-Endpunkt

Diese Ports werden nicht auf den Home-Assistant-Host veröffentlicht.

## Berechtigungen

`NET_ADMIN` wird ausschließlich benötigt, um die nftables-Regeln im Container einzurichten. Das Gateway fordert keine unnötigen Home-Assistant-, Docker- oder Host-Rechte an.

## Benutzeroberfläche

Das Gateway besitzt absichtlich **kein eigenes Ingress-Dashboard**. Die Benutzeroberfläche wird von `custom_components/bitcoin_stack_tracker` als natives Home-Assistant-Seitenleistenpanel **Bitcoin Stack** registriert.

Nach einem Update der Custom Integration ist ein **vollständiger Neustart von Home Assistant Core** erforderlich. Das Panel ist anschließend unter `/bitcoin-stack-tracker` erreichbar.

## Bei Problemen

Wenn der Tracker lokale Daten zeigt, aber öffentliche Kurse fehlen:

1. Prüfen, ob **Bitcoin Stack Tracker Tor Gateway** läuft.
2. App-Log öffnen und auf Tor-/Firewall-Fehler prüfen.
3. Im Tracker den Tor-/Leak-Test ausführen.
4. Bei einem Update zuerst den GitHub-/App-Stand und die Version des Gateways vergleichen.

Ein Tor-Ausfall darf lokale Buchungen und den vorhandenen Cache nicht zerstören. Öffentliche Live-Abfragen bleiben in diesem Fall gesperrt, bis Tor wieder verfügbar ist.
