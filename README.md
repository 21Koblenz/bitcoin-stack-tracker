# Bitcoin Stack Tracker v0.21.0.6

**Bitcoin Stack Tracker** ist ein lokaler, Bitcoin-only Portfolio- und Stack-Tracker für Home Assistant. Er verwaltet Käufe, Verkäufe, Depots, Ziele, historische Kurse, FIFO-Zuordnungen und Performance-Auswertungen, ohne Wallet-Schlüssel oder Seed-Wörter zu benötigen.

> **Local first · Bitcoin only · öffentliche Daten ausschließlich über Tor**

## Überblick

Das Projekt besteht aus zwei getrennten Bausteinen:

1. **Home-Assistant-Custom-Integration** – speichert und berechnet Portfolio-Daten und stellt das native Seitenleistenpanel **Bitcoin Stack** bereit.
2. **Bitcoin Stack Tracker Tor Gateway** – minimales Home-Assistant-App-Modul für öffentliche Kurs- und Historienabfragen über Tor mit nftables-Fail-Closed-Killswitch.

Das Tor Gateway hat keinen Zugriff auf Kaufbuch, Depotdaten, Tracker-Passwörter oder Home-Assistant-API-Tokens.

## Funktionen

### Portfolio und Stack

- Gesamtbestand in BTC oder Sats
- mehrere Depots plus Gesamtdepot
- Einstand, Portfoliowert und offener Einstand
- realisierter und unrealisierter Gewinn/Verlust
- Langzeit- und Kurzzeitbestand
- Privacy-/Diskretmodus und fiatfreie Darstellung
- Deutsch und Englisch
- Desktop- und Smartphone-Ansicht

### Käufe, Verkäufe und FIFO

- Käufe mit Menge, Kurs, Fiatwährung, Gebühr, Datum, Depot und Notiz
- Verkäufe mit depotweiser FIFO-Zuordnung
- Bestand ohne bekannten Einstand
- Plausibilitätsprüfung vor dem Speichern
- frei einstellbare Haltezeit, standardmäßig 365 Tage
- FIFO-Abgänge für Verkäufe und bewertete Ausgaben mit Lot-Zuordnung, Einstand, Gegenwert, Gewinn/Verlust und Haltezeit
- Zusätzlich je Abgang: **Ø Einkauf bis dahin** als BTC-gewichteter historischer Einstand aller Käufe bis zu diesem Zeitpunkt sowie ein separater Ø-P/L-Vergleich; dieser Vergleich ersetzt FIFO nicht
- Pagination und mobile Kartenansicht

Die FIFO-/Haltezeitanzeige ist eine Rechenhilfe und keine Steuerberatung.

### CSV-Import

Bearbeitbare Importvorschau für unter anderem Kraken, Coinbase, Binance, Coinfinity, Pocket Bitcoin, Relai, Bittr/getbittr, Wavespace und CoinTracking-kompatible Dateien. Dubletten und unzulässige Buchungen werden geprüft; Original-CSV-/ZIP-Dateien werden nicht dauerhaft gespeichert.

Details: [`CSV-IMPORT.md`](CSV-IMPORT.md)

### Ziele

- mehrere frei benennbare Stacking-Ziele
- Zielmenge in BTC oder Sats
- Ziel pro Depot oder für das Gesamtdepot
- Fortschritt, Restmenge und optional benötigter Fiatbetrag

### Charts und Auswertungen

- Bitcoin-Kurs
- Stack-Verlauf
- Portfoliowert
- Gesamtgewinn/-verlust
- Einstand + Buchgewinn/-verlust
- kombinierte Overlays
- linke und rechte Y-Achse unabhängig linear/logarithmisch
- Zeiträume von Heute bis Max
- TWR, XIRR, BTC-CAGR, DCA-, Drawdown- und cashflow-neutraler HODL-Benchmark
- Stacking-Geschwindigkeit, Netto-Fiat-Investment, Gebührenquoten und Stack-Altersverteilung
- Bitcoin-Netzwerk-, Milestone- und Halving-Markierungen

## Backup und Datenportabilität

Das verschlüsselte portable `.bstbackup` enthält bewusst nur:

1. Käufe und Verkäufe
2. Depots
3. Ziele
4. Historie

Nicht Teil des portablen Backups sind Netzwerk-/Tor-/Mempool-Konfiguration, Home-Assistant-Zugriffslisten oder Verschlüsselungseinstellungen. Ein importiertes Backup kann dadurch keine Installations- oder Netzwerkparameter überschreiben.

Details: [`DATA-PORTABILITY.md`](DATA-PORTABILITY.md)

## Datenschutz und Sicherheit

Portfolio-Daten bleiben lokal in Home Assistant. Die Anwendung sendet keine Buchungen, Depotnamen, Ziele, Bestände, Master-Passwörter oder Backup-Passwörter an öffentliche Kursanbieter.

Im Passwortmodus verwendet der Tracker Argon2id zur Passwortableitung und AES-256-GCM für authentifizierte Verschlüsselung. Das Ledger verwendet Envelope-Verschlüsselung mit separatem Geräteschlüssel. Master- und Backup-Passwörter werden nicht dauerhaft gespeichert.

Das native Home-Assistant-Panel kommuniziert mit dem Tracker-iframe über einen begrenzten RPC-Kanal. Das Tracker-Dokument besitzt zusätzlich eine restriktive Content Security Policy; direkte Netzwerkaufrufe aus dem Tracker-Frontend sind blockiert.

Weitere Details: [`SECURITY.md`](SECURITY.md)

## Tor und Fail Closed

Öffentliche Preis- und Historienabfragen dürfen nicht direkt ins Clearnet ausweichen:

```text
Home Assistant Core
        │
        ├── ausdrücklich konfigurierte lokale Node → direkt im LAN
        │
        └── öffentliche Datenquelle → SOCKS5 :9050 → Tor → Internet/API
```

Das Gateway nutzt nftables mit Default-Drop-Regeln. Nur der Tor-Prozess darf öffentlichen Egress öffnen.

- `9050/tcp` – exklusiver SOCKS5-Pfad für Bitcoin Stack Tracker / Home Assistant Core
- `9051/tcp` – bewusst geteilter interner Tor-SOCKS-Port für andere Home-Assistant-Apps
- `8099/tcp` – interner Health-Endpunkt

Details: [`TOR-HINWEISE.md`](TOR-HINWEISE.md)

## Installation

Die vollständige Anleitung steht in [`INSTALLATION.md`](INSTALLATION.md).

### 1-Klick-Links für Home Assistant

**Integration über HACS hinzufügen**

[![Bitcoin Stack Tracker in HACS öffnen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=21Koblenz&repository=bitcoin-stack-tracker&category=integration)

**Tor-Gateway-App-Repository zu Home Assistant hinzufügen**

[![Bitcoin Stack Tracker App-Repository hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2F21Koblenz%2Fbitcoin-stack-tracker)

**Integration nach Installation/Neustart einrichten**

[![Bitcoin Stack Tracker Integration einrichten](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=bitcoin_stack_tracker)

Kurzfassung:

1. Integration über den HACS-Button installieren.
2. Home Assistant Core vollständig neu starten und danach die Integration über den Einrichtungs-Button hinzufügen.
3. Das Tor-Gateway-Repository über den App-Repository-Button hinzufügen und **Bitcoin Stack Tracker Tor Gateway** installieren/starten.
4. Tracker öffnen, Tresor einrichten und ein verschlüsseltes `.bstbackup` außerhalb von Home Assistant sichern.

## Release

Aktueller Projektstand: **v0.21.0.6**. Dieser Release bündelt **alle Änderungen seit v0.21.0.5**.

### Änderungen seit v0.21.0.5

- **Large-Ledger-Performance:** große CSV-Imports, Tresor-Unlock, Dashboard, Charts und FIFO wurden für Ledgers mit vielen Buchungen optimiert; FIFO-Caches werden wiederverwendet, historische Tagesstände chronologisch aufgebaut und Preisreihen per Binärsuche aufgelöst.
- **Lazy Loading & Browser-Performance:** Ledger, FIFO und große Historienreihen werden erst bei Bedarf geladen; schwere Overview-Berechnungen laufen verzögert/abbrechbar und wiederholte Vollsuchen wurden durch Indizes/Caches ersetzt.
- **FIFO-Abgänge:** Verkäufe und bewertete Ausgaben/Kartenzahlungen werden vollständig ausgewertet. Teil-Lot-Reste bleiben erhalten und werden beim nächsten Abgang zuerst verbraucht; mehrere Kauf-Lots behalten jeweils ihre eigene historische Kostenbasis.
- **Ø Einkauf bis dahin:** Zusätzlich zum steuer-/lotbezogenen FIFO-Ergebnis zeigt jeder Abgang den BTC-gewichteten durchschnittlichen Einstand **aller Käufe in derselben Fiatwährung bis zu diesem Zeitpunkt** inklusive Kaufgebühren. Bereits zuvor verkaufte Käufe bleiben bewusst Teil dieses historischen Durchschnitts. Daraus wird ein separater Ø-P/L-Vergleich berechnet, damit sofort sichtbar ist, ob der Abgang gegenüber dem damaligen Gesamt-Durchschnitt im Plus oder Minus lag. Es findet keine FX-Umrechnung statt. In den einzelnen FIFO-Abgangszeilen werden **FIFO-Gewinn/FIFO-Rendite** und **Ø-Gewinn/Ø-Rendite** getrennt ausgewiesen. Die Kopfübersicht enthält ebenfalls zwei getrennte Blöcke: die echte FIFO-Gesamtrechnung und den historischen Durchschnittsvergleich mit BTC-gewichtetem Vergleichskaufkurs, Vergleichseinstand sowie absolutem und relativem Ø-Ergebnis.
- **Berechnungs-Audit:** Drawdown-, ATH-, XIRR-, Zeitstempel-, Oversell- und Gebühren-Randfälle wurden erneut geprüft und korrigiert.
- **Neue Kennzahlen:** BTC-CAGR, Stacking-Geschwindigkeit, realisierter/unrealisierter/gesamter Gewinn, Netto-Fiat-Investment, Drawdown/Recovery, Haltezeit-/Stack-Alter-Auswertung und cashflow-neutraler HODL-Benchmark.
- **Gebühren:** Kauf- und Abgangsgebühren werden als volumengewichtete Quoten ausgewiesen; echte BTC-/On-Chain-Gebühren werden in Sats berücksichtigt, unbekannte historische Werte nicht geraten.
- **Charts:** linke und rechte Y-Achse können unabhängig Linear oder Logarithmisch dargestellt werden.
- **Datenschutz/Privatsphäre:** CSV-Dublettenabgleich läuft vollständig in Home Assistant Core; bestehende Import-Hashes verlassen Core nicht. Ledger-, Chart- und FIFO-Payloads wurden minimiert und sensible Antworten gegen Browser-/Proxy-Caching gehärtet.
- **FIFO-Oberfläche:** `FIFO SALES / Verkaufsübersicht` wurde zu **FIFO ABGÄNGE / FIFO-Abgänge**; Verkauf und Ausgabe werden getrennt gekennzeichnet und die Kopfzahl zählt echte Abgänge statt Lot-Matches.

Das **Tor Gateway bleibt v0.21.0.3**, da v0.21.0.6 ausschließlich die Custom Integration betrifft.

Auditbericht: [`AUDIT-v0.21.0.6.md`](AUDIT-v0.21.0.6.md)

Änderungen dieses Releases: [`CHANGELOG.md`](CHANGELOG.md)  
Release-Übersicht: [`RELEASE-NOTES.md`](RELEASE-NOTES.md)

## Was das Projekt ausdrücklich nicht ist

- keine Wallet
- keine Börse
- kein Seed-Manager
- kein Private-Key-Speicher
- kein automatischer Handel
- kein Wallet-Backup
- keine Steuerberatung
- keine Altcoin-Verwaltung

Seed-Wörter, Wallet-Passphrasen und Private Keys gehören niemals in Notizen oder Backups des Trackers.

## Lizenz

Dieses Projekt steht unter **GNU Affero General Public License v3.0 only (`AGPL-3.0-only`)**. Verwenden, verändern und weitergeben ist erlaubt; die Copyleft-Bedingungen der AGPL gelten für abgeleitete und über ein Netzwerk bereitgestellte modifizierte Versionen. Der vollständige Lizenztext steht in [`LICENSE`](LICENSE).
