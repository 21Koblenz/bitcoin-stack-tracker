# Bitcoin Stack Tracker v0.21.0.8

[English](#english) · [Deutsch](#deutsch)


---

<a id="english"></a>
## English

**Bitcoin Stack Tracker** is a local-first, Bitcoin-only portfolio and stack tracker for Home Assistant. It manages purchases, sales, portfolios, targets, historical prices, FIFO assignments and performance analytics without requiring wallet keys or seed words.

> **Local first · Bitcoin only · public data exclusively through Tor**

### Overview

The project consists of two separate components:

1. **Home Assistant custom integration** – stores and calculates portfolio data and provides the native **Bitcoin Stack** sidebar panel.
2. **Bitcoin Stack Tracker Tor Gateway** – a minimal Home Assistant app for public price and historical-data requests through Tor with an nftables fail-closed killswitch.

The Tor Gateway has no access to the purchase ledger, portfolio data, tracker passwords or Home Assistant API tokens.

### Features

#### Portfolio and stack

- total holdings in BTC or sats
- multiple portfolios plus an aggregated portfolio
- cost basis, portfolio value and open cost basis
- realized and unrealized profit/loss
- long-term and short-term holdings
- privacy/discreet mode and fiat-free display
- German and English
- desktop and smartphone layouts

#### Purchases, sales and FIFO

- purchases with amount, price, fiat currency, fee, date, portfolio and note
- sales with per-portfolio FIFO assignment
- holdings with unknown cost basis
- plausibility checks before saving
- configurable holding period, 365 days by default
- FIFO disposals for sales and valued expenses with lot assignment, cost basis, proceeds/value, profit/loss and holding period
- additionally per disposal: **historical average purchase price up to that date**, BTC-weighted across all purchases up to the disposal date, plus a separate average-price P/L comparison; this does not replace FIFO
- pagination and mobile card layout

The FIFO/holding-period view is a calculation aid and not tax advice.

#### CSV import

Editable import preview for **Kraken, Coinbase, Binance, Bitpanda, Peach Bitcoin, Coinfinity, Pocket Bitcoin, Relai, Bittr/getbittr, Wavespace** and CoinTracking-compatible files. Duplicates and invalid transactions are checked; original CSV/ZIP files are not stored permanently.

For Peach Bitcoin, `Amount` is interpreted as satoshis. `Premium` is a percentage value. For purchases, the premium included in `Bitcoin Price` is mathematically removed and shown as a fiat fee, while `Price` remains the authoritative total amount actually paid.

Details: [`CSV-IMPORT.md`](CSV-IMPORT.md)

#### Targets

- multiple freely named stacking targets
- target amount in BTC or sats
- target per portfolio or for the aggregated portfolio
- progress, remaining amount and optional required fiat amount

#### Charts and analytics

- Bitcoin price
- stack history
- portfolio value
- total profit/loss
- cost basis plus unrealized profit/loss
- combined overlays
- independent linear/logarithmic scaling for the left and right Y axes
- time ranges from Today to Max
- TWR, XIRR, BTC CAGR, DCA, drawdown and cash-flow-neutral HODL benchmark
- stacking velocity, net fiat investment, fee ratios and stack-age distribution
- Bitcoin network, milestone and halving markers

### Backup and data portability

The encrypted portable `.bstbackup` intentionally contains only:

1. purchases and sales
2. portfolios
3. targets
4. history

Network/Tor/mempool configuration, Home Assistant access lists and encryption settings are not part of the portable backup. An imported backup therefore cannot overwrite installation or network settings.

Details: [`DATA-PORTABILITY.md`](DATA-PORTABILITY.md)

### Privacy and security

Portfolio data stays local in Home Assistant. The application does not send transactions, portfolio names, targets, holdings, master passwords or backup passwords to public price providers.

In password mode, the tracker uses Argon2id for password derivation and AES-256-GCM for authenticated encryption. The ledger uses envelope encryption with a separate device key. Master and backup passwords are not stored permanently.

The native Home Assistant panel communicates with the tracker iframe through a limited RPC channel. The tracker document also uses a restrictive Content Security Policy; direct network requests from the tracker frontend are blocked.

More details: [`SECURITY.md`](SECURITY.md)

### Tor and fail closed

Public price and historical-data requests must not fall back directly to the clearnet:

```text
Home Assistant Core
        │
        ├── explicitly configured local node → direct over LAN
        │
        └── public data source → SOCKS5 :9050 → Tor → Internet/API
```

The gateway uses nftables with default-drop rules. Only the Tor process may open public egress connections.

- `9050/tcp` – dedicated SOCKS5 path for Bitcoin Stack Tracker / Home Assistant Core
- `9051/tcp` – intentionally shared internal Tor SOCKS port for other Home Assistant apps
- `8099/tcp` – internal health endpoint

Details: [`TOR-HINWEISE.md`](TOR-HINWEISE.md)

### Installation

The full installation guide is available in [`INSTALLATION.md`](INSTALLATION.md).

#### One-click links for Home Assistant

**Add the integration through HACS**

[![Open Bitcoin Stack Tracker in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=21Koblenz&repository=bitcoin-stack-tracker&category=integration)

**Add the Tor Gateway app repository to Home Assistant**

[![Add Bitcoin Stack Tracker app repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2F21Koblenz%2Fbitcoin-stack-tracker)

**Set up the integration after installation/restart**

[![Set up Bitcoin Stack Tracker integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=bitcoin_stack_tracker)

Short version:

1. Install the integration using the HACS button.
2. Fully restart Home Assistant Core, then add the integration using the setup button.
3. Add the Tor Gateway repository using the app-repository button and install/start **Bitcoin Stack Tracker Tor Gateway**.
4. Open the tracker, set up the vault and keep an encrypted `.bstbackup` outside Home Assistant.

### Release

Current project version: **v0.21.0.8**. This small release adds the **Peach Bitcoin CSV importer** and makes the project README fully bilingual in German and English.

#### Changes since v0.21.0.7

- **Peach Bitcoin:** dedicated CSV parser for `Date`, `Trade ID`, `Type`, `Amount`, `Price`, `Bitcoin Price`, `Currency` and `Premium`.
- **Correct satoshi handling:** Peach `Amount` is explicitly interpreted as an integer satoshi amount and converted to BTC.
- **Premium/fee handling:** `Premium` is treated as a percentage. For purchases, the markup included in `Bitcoin Price` is reversed mathematically (`Bitcoin Price / (1 + Premium/100)`); the difference to the authoritative paid `Price` is tracked as a fiat fee without double-counting cost basis.
- **Duplicate detection:** `Trade ID` is used as the stable import identity; the raw ID is not stored in the ledger and only participates through the existing local hash mechanism.
- **Documentation:** README is fully bilingual German/English and Peach Bitcoin is documented in `CSV-IMPORT.md`.
- **Regression tests:** targeted Peach tests cover satoshi conversion, premium/fee calculation, Trade-ID duplicates, missing premium and sales.

The **Tor Gateway remains at v0.21.0.3**, because v0.21.0.8 only affects the custom integration and documentation.

The baseline calculation, privacy and security audit from [`AUDIT-v0.21.0.6.md`](AUDIT-v0.21.0.6.md) remains unchanged.

Release changes: [`CHANGELOG.md`](CHANGELOG.md)  
Release overview: [`RELEASE-NOTES.md`](RELEASE-NOTES.md)

### What this project explicitly is not

- not a wallet
- not an exchange
- not a seed manager
- not a private-key store
- not an automated trading system
- not a wallet backup
- not tax advice
- not an altcoin tracker

Never put seed words, wallet passphrases or private keys into tracker notes or backups.

### License

This project is licensed under **GNU Affero General Public License v3.0 only (`AGPL-3.0-only`)**. Use, modification and redistribution are allowed subject to the AGPL copyleft requirements for derivative and network-served modified versions. The full license text is available in [`LICENSE`](LICENSE).



---

<a id="deutsch"></a>
## Deutsch

**Bitcoin Stack Tracker** ist ein lokaler, Bitcoin-only Portfolio- und Stack-Tracker für Home Assistant. Er verwaltet Käufe, Verkäufe, Depots, Ziele, historische Kurse, FIFO-Zuordnungen und Performance-Auswertungen, ohne Wallet-Schlüssel oder Seed-Wörter zu benötigen.

> **Local first · Bitcoin only · öffentliche Daten ausschließlich über Tor**

### Überblick

Das Projekt besteht aus zwei getrennten Bausteinen:

1. **Home-Assistant-Custom-Integration** – speichert und berechnet Portfolio-Daten und stellt das native Seitenleistenpanel **Bitcoin Stack** bereit.
2. **Bitcoin Stack Tracker Tor Gateway** – minimales Home-Assistant-App-Modul für öffentliche Kurs- und Historienabfragen über Tor mit nftables-Fail-Closed-Killswitch.

Das Tor Gateway hat keinen Zugriff auf Kaufbuch, Depotdaten, Tracker-Passwörter oder Home-Assistant-API-Tokens.

### Funktionen

#### Portfolio und Stack

- Gesamtbestand in BTC oder Sats
- mehrere Depots plus Gesamtdepot
- Einstand, Portfoliowert und offener Einstand
- realisierter und unrealisierter Gewinn/Verlust
- Langzeit- und Kurzzeitbestand
- Privacy-/Diskretmodus und fiatfreie Darstellung
- Deutsch und Englisch
- Desktop- und Smartphone-Ansicht

#### Käufe, Verkäufe und FIFO

- Käufe mit Menge, Kurs, Fiatwährung, Gebühr, Datum, Depot und Notiz
- Verkäufe mit depotweiser FIFO-Zuordnung
- Bestand ohne bekannten Einstand
- Plausibilitätsprüfung vor dem Speichern
- frei einstellbare Haltezeit, standardmäßig 365 Tage
- FIFO-Abgänge für Verkäufe und bewertete Ausgaben mit Lot-Zuordnung, Einstand, Gegenwert, Gewinn/Verlust und Haltezeit
- Zusätzlich je Abgang: **Ø Einkauf bis dahin** als BTC-gewichteter historischer Einstand aller Käufe bis zu diesem Zeitpunkt sowie ein separater Ø-P/L-Vergleich; dieser Vergleich ersetzt FIFO nicht
- Pagination und mobile Kartenansicht

Die FIFO-/Haltezeitanzeige ist eine Rechenhilfe und keine Steuerberatung.

#### CSV-Import

Bearbeitbare Importvorschau für unter anderem **Kraken, Coinbase, Binance, Bitpanda, Peach Bitcoin, Coinfinity, Pocket Bitcoin, Relai, Bittr/getbittr, Wavespace** und CoinTracking-kompatible Dateien. Dubletten und unzulässige Buchungen werden geprüft; Original-CSV-/ZIP-Dateien werden nicht dauerhaft gespeichert.

Beim Peach-Bitcoin-Import wird `Amount` als Satoshi-Betrag interpretiert. `Premium` ist ein Prozentwert. Der in `Bitcoin Price` enthaltene Premium-Aufschlag wird für Käufe rechnerisch entfernt und als Fiatgebühr ausgewiesen, während `Price` als tatsächlich gezahlter Gesamtbetrag erhalten bleibt.

Details: [`CSV-IMPORT.md`](CSV-IMPORT.md)

#### Ziele

- mehrere frei benennbare Stacking-Ziele
- Zielmenge in BTC oder Sats
- Ziel pro Depot oder für das Gesamtdepot
- Fortschritt, Restmenge und optional benötigter Fiatbetrag

#### Charts und Auswertungen

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

### Backup und Datenportabilität

Das verschlüsselte portable `.bstbackup` enthält bewusst nur:

1. Käufe und Verkäufe
2. Depots
3. Ziele
4. Historie

Nicht Teil des portablen Backups sind Netzwerk-/Tor-/Mempool-Konfiguration, Home-Assistant-Zugriffslisten oder Verschlüsselungseinstellungen. Ein importiertes Backup kann dadurch keine Installations- oder Netzwerkparameter überschreiben.

Details: [`DATA-PORTABILITY.md`](DATA-PORTABILITY.md)

### Datenschutz und Sicherheit

Portfolio-Daten bleiben lokal in Home Assistant. Die Anwendung sendet keine Buchungen, Depotnamen, Ziele, Bestände, Master-Passwörter oder Backup-Passwörter an öffentliche Kursanbieter.

Im Passwortmodus verwendet der Tracker Argon2id zur Passwortableitung und AES-256-GCM für authentifizierte Verschlüsselung. Das Ledger verwendet Envelope-Verschlüsselung mit separatem Geräteschlüssel. Master- und Backup-Passwörter werden nicht dauerhaft gespeichert.

Das native Home-Assistant-Panel kommuniziert mit dem Tracker-iframe über einen begrenzten RPC-Kanal. Das Tracker-Dokument besitzt zusätzlich eine restriktive Content Security Policy; direkte Netzwerkaufrufe aus dem Tracker-Frontend sind blockiert.

Weitere Details: [`SECURITY.md`](SECURITY.md)

### Tor und Fail Closed

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

### Installation

Die vollständige Anleitung steht in [`INSTALLATION.md`](INSTALLATION.md).

#### 1-Klick-Links für Home Assistant

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

### Release

Aktueller Projektstand: **v0.21.0.8**. Dieser kleine Release ergänzt den **Peach-Bitcoin-CSV-Import** und erweitert die Projekt-README vollständig um Deutsch und Englisch.

#### Änderungen seit v0.21.0.7

- **Peach Bitcoin:** eigener CSV-Parser für `Date`, `Trade ID`, `Type`, `Amount`, `Price`, `Bitcoin Price`, `Currency` und `Premium`.
- **Sats korrekt:** `Amount` wird bei Peach ausdrücklich als ganzzahliger Satoshi-Betrag interpretiert und in BTC umgerechnet.
- **Premium/Gebühr:** `Premium` wird als Prozentwert behandelt. Für Käufe wird der in `Bitcoin Price` enthaltene Aufschlag mathematisch entfernt (`Bitcoin Price / (1 + Premium/100)`); die Differenz zum tatsächlich gezahlten `Price` wird als Fiatgebühr geführt, ohne den Einstand doppelt zu belasten.
- **Dubletten:** `Trade ID` wird als stabile Import-Identität verwendet; die Roh-ID wird nicht im Ledger gespeichert, sondern nur über den bestehenden lokalen Hash-Mechanismus berücksichtigt.
- **Dokumentation:** README vollständig zweisprachig Deutsch/Englisch; Peach Bitcoin ist zusätzlich in `CSV-IMPORT.md` dokumentiert.
- **Regressionstests:** gezielte Peach-Tests für Sats-Umrechnung, Premium-/Gebührenrechnung, Trade-ID-Dubletten, fehlendes Premium und Verkäufe.

Das **Tor Gateway bleibt v0.21.0.3**, da v0.21.0.8 ausschließlich die Custom Integration und Dokumentation betrifft.

Der grundlegende Berechnungs-, Datenschutz- und Security-Audit aus [`AUDIT-v0.21.0.6.md`](AUDIT-v0.21.0.6.md) bleibt unverändert bestehen.

Änderungen dieses Releases: [`CHANGELOG.md`](CHANGELOG.md)  
Release-Übersicht: [`RELEASE-NOTES.md`](RELEASE-NOTES.md)

### Was das Projekt ausdrücklich nicht ist

- keine Wallet
- keine Börse
- kein Seed-Manager
- kein Private-Key-Speicher
- kein automatischer Handel
- kein Wallet-Backup
- keine Steuerberatung
- keine Altcoin-Verwaltung

Seed-Wörter, Wallet-Passphrasen und Private Keys gehören niemals in Notizen oder Backups des Trackers.

### Lizenz

Dieses Projekt steht unter **GNU Affero General Public License v3.0 only (`AGPL-3.0-only`)**. Verwenden, verändern und weitergeben ist erlaubt; die Copyleft-Bedingungen der AGPL gelten für abgeleitete und über ein Netzwerk bereitgestellte modifizierte Versionen. Der vollständige Lizenztext steht in [`LICENSE`](LICENSE).

