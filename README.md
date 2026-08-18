# Bitcoin Stack Tracker v0.21.0.13

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

#### Ledger, fees and FIFO

- purchases and income with amount, price, fiat currency, fee, date, portfolio and note
- sales and expenses with per-portfolio FIFO assignment and realized profit/loss
- standalone **on-chain / Lightning transaction fees** in sats or BTC; they reduce the tracked stack and are valued in fiat at the historical BTC price of the booking time
- holdings with unknown cost basis
- manual booking type can be corrected later without deleting/recreating the row; FIFO is fully revalidated after the change
- non-blocking historical-price plausibility warning for manual priced bookings from **10% deviation**
- configurable holding period, 365 days by default
- FIFO disposals for sales, valued expenses and BTC transaction fees with lot assignment, cost basis, proceeds/value, profit/loss/FIFO effect and holding period
- additionally per disposal: **historical average purchase price up to that date**, BTC-weighted across all purchases up to the disposal date, plus a separate average-price P/L comparison; this does not replace FIFO
- pagination and mobile card layout

The FIFO/holding-period view is a calculation aid and not tax advice.

#### CSV import

Editable import preview for **Kraken, Coinbase, Binance, Bitpanda, Revolut X, Peach Bitcoin, Coinfinity, Pocket Bitcoin, Relai, Bittr/getbittr, Wavespace** and CoinTracking-compatible files. Duplicates and invalid transactions are checked; original CSV/ZIP files are not stored permanently.

For **Revolut X**, the compact `Symbol, Type, Quantity, Price, Value, Fees, Date` statement is detected automatically. BTC/XBT `Buy` and `Sell` rows are imported; `Quantity` is BTC and `Fees` is a separate fiat fee.

For Peach Bitcoin, `Amount` is interpreted as satoshis. `Premium` is a percentage value. For purchases, the premium included in `Bitcoin Price` is mathematically removed and shown as a fiat fee, while `Price` remains the authoritative total amount actually paid.

Details: [`CSV-IMPORT.md`](CSV-IMPORT.md)

#### Targets

- multiple freely named stacking targets
- target amount in BTC or sats
- target per portfolio or for the aggregated portfolio
- progress, remaining amount and optional required fiat amount

#### Charts, market assessment and analytics

- Bitcoin price
- adaptive **0–100 market assessment** from public historical price data; explicitly not a buy signal
- causal historical market-assessment chart with BTC-price overlay, crosshair values, configurable price opacity and linear/log price axis
- optional **causal EMA smoothing** (Off / 3 / 5 / 7 / 14 / 30 points); display-only and shared with the overview-chart overlay
- overview chart mode **Bitcoin price + market assessment** with an independent linear score axis that auto-scales to the visible score range
- real short-range assessment snapshots without extra model work: **1 h on 1 day · 6 h on week-to-date/1 week · 12 h on month-to-date/30 days**; snapshots come from the existing five-minute current-score run, are not interpolated, and are retained for up to 45 days
- bottom/top zone and confirmation diagnostics, configurable weights, thresholds and adaptive volatility/cycle windows
- stack history
- portfolio value
- total profit/loss
- cost basis plus unrealized profit/loss
- combined overlays
- independent linear/logarithmic scaling for the left and right Y axes
- time ranges: **1 day · week-to-date · 1 week · month-to-date · 30 days · 90 days · YTD · 1 year · 3 years · 5 years · 10 years · since first purchase · Max**
- TWR, selected-range annualized XIRR, BTC-market CAGR, DCA, drawdown and cash-flow-neutral HODL benchmark
- stacking velocity, net fiat investment, fee ratios and stack-age distribution
- Bitcoin network, milestone and halving markers

#### Sats Sentinel

- privacy-first, watch-only Bitcoin monitoring for addresses, address groups, XPUB/YPUB/ZPUB and descriptors; no private keys, seeds, signing or spending
- configurable query source: **automatic · Fulcrum/Electrum · electrs/Electrum · own Mempool · configured public Mempool over Tor**
- explicit source selection is **fail closed**: if the selected own source is down, Sentinel reports offline/partial and never silently switches to a public provider
- local/private Fulcrum/electrs/Mempool targets may be queried directly over LAN; `.onion` and public targets use Tor with remote DNS
- Fulcrum/electrs support Electrum scripthash balance/history/UTXO queries; TLS and exact SHA-256 certificate pinning support self-signed Fulcrum certificates
- separate device-bound AES-256-GCM Sentinel runtime vault stores the public watch-only material required for 24/7 locked monitoring (address/XPUB/descriptor, derived addresses and connection metadata); it never stores seeds, private keys, xprv or spend/signing keys
- when the portfolio vault is locked, the entire Sentinel wallet/address/balance/source card is **hidden by default** and its data is not requested by the locked frontend; an unlocked per-browser/per-device option can explicitly show the watch-only card without changing background monitoring or notifications
- movement journal with sender → direction → recipient flow, configurable categories, notes, thresholds and paging; TXIDs/addresses can link to the separately configured Mempool explorer
- Home Assistant events, persistent notifications, multiple `notify.*` services, self-hosted ntfy and webhooks with discreet/normal/detailed payloads
- removing a watch entry also permanently purges that monitor's journal history from the encrypted Sentinel cache

### Backup and data portability

The encrypted portable `.bstbackup` intentionally contains only:

1. ledger entries (purchases, income, sales, expenses, transaction fees and stack entries)
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

Current project version: **v0.21.0.13**. This release consolidates the post-v0.21.0.12 RC line through RC20 and fixes HD-wallet false-zero discovery, Home Assistant timer/CPU regressions, Companion QR scanning and stale wallet-card frontend state.

#### Changes since v0.21.0.12

- **HD discovery bootstrap:** existing small Gap values remain user-controlled, but initial discovery checks a standard 20-address window before declaring a branch unused. New HD monitors default to Receive 20 / Change 20.
- **xpub Auto script detection:** historical activity resolves native SegWit, nested SegWit, Taproot or legacy; plain xpub serialization is no longer treated as a definitive legacy script hint.
- **Locked Sentinel privacy:** the encrypted runtime vault keeps Sentinel monitoring alive while the portfolio vault is locked, but the locked screen hides the entire Sentinel wallet/address/balance/source card by default and does not fetch that management payload. An unlocked local display option can opt back in; monitoring/alerts stay active either way.
- **Lower Fulcrum/electrs load:** bounded batches/yields, hourly sliced reconciliation and coalesced runtime-store writes reduce Core/storage churn.
- **Market-assessment performance:** one shared current-score executor cache plus a persistent causal history-score cache. The price chart remains live while the CPU-heavy current score is refreshed at most every five minutes from the newest quote. Those existing model runs also feed a lightweight public intraday snapshot store (1 h / 6 h / 12 h display buckets for short overview ranges) without any additional model calculation. A newly added or corrected durable daily history value changes the content signature, rebuilds the daily score series once and immediately stores the new generation persistently.
- **Vault timer fix:** old callback registrations are cancelled/rebound and the expiry worker no longer accepts Home Assistant's datetime tick as the `hass` argument.
- **Companion QR fix:** scan results/abort are handled by external-bus message type with a three-second startup handshake.
- **Collapsed wallet cards:** cards default collapsed and the v5 local preference key resets stale production-browser state once.
- **Bounded journal:** Sentinel retains the newest 5,000 activity rows.
- **Validation:** dedicated release/security, functional/performance, current-score-cache and persistent history-cache regressions pass on the final build. The uploaded RC20 component archive did not contain the full repository test suite, so the previous 502+8 result is not represented as rerun.

**After updating, fully restart Home Assistant Core and hard-reload the frontend.**

The **Tor Gateway remains at v0.21.0.3**.

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

#### Buchungen, Gebühren und FIFO

- Käufe und Einnahmen mit Menge, Kurs, Fiatwährung, Gebühr, Datum, Depot und Notiz
- Verkäufe und Ausgaben mit depotweiser FIFO-Zuordnung und realisiertem Gewinn/Verlust
- eigenständige **On-Chain-/Lightning-Transaktionsgebühren** in sats oder BTC; sie mindern den erfassten Stack und werden zum historischen BTC-Kurs des Buchungszeitpunkts in Fiat bewertet
- Bestand ohne bekannten Einstand
- Buchungsart kann später korrigiert werden, ohne die Buchung zu löschen; FIFO wird danach vollständig neu validiert
- nicht blockierende historische Kurs-Plausibilitätswarnung bei manuellen bewerteten Buchungen ab **10 % Abweichung**
- frei einstellbare Haltezeit, standardmäßig 365 Tage
- FIFO-Abgänge für Verkäufe, bewertete Ausgaben und BTC-Transaktionsgebühren mit Lot-Zuordnung, Einstand, Gegenwert, Gewinn/Verlust/FIFO-Effekt und Haltezeit
- Zusätzlich je Abgang: **Ø Einkauf bis dahin** als BTC-gewichteter historischer Einstand aller Käufe bis zu diesem Zeitpunkt sowie ein separater Ø-P/L-Vergleich; dieser Vergleich ersetzt FIFO nicht
- Pagination und mobile Kartenansicht

Die FIFO-/Haltezeitanzeige ist eine Rechenhilfe und keine Steuerberatung.

#### CSV-Import

Bearbeitbare Importvorschau für unter anderem **Kraken, Coinbase, Binance, Bitpanda, Revolut X, Peach Bitcoin, Coinfinity, Pocket Bitcoin, Relai, Bittr/getbittr, Wavespace** und CoinTracking-kompatible Dateien. Dubletten und unzulässige Buchungen werden geprüft; Original-CSV-/ZIP-Dateien werden nicht dauerhaft gespeichert.

Beim **Revolut-X-Import** wird das kompakte Format `Symbol, Type, Quantity, Price, Value, Fees, Date` automatisch erkannt. Übernommen werden BTC/XBT `Buy` und `Sell`; `Quantity` ist BTC und `Fees` ist eine separate Fiatgebühr.

Beim Peach-Bitcoin-Import wird `Amount` als Satoshi-Betrag interpretiert. `Premium` ist ein Prozentwert. Der in `Bitcoin Price` enthaltene Premium-Aufschlag wird für Käufe rechnerisch entfernt und als Fiatgebühr ausgewiesen, während `Price` als tatsächlich gezahlter Gesamtbetrag erhalten bleibt.

Details: [`CSV-IMPORT.md`](CSV-IMPORT.md)

#### Ziele

- mehrere frei benennbare Stacking-Ziele
- Zielmenge in BTC oder Sats
- Ziel pro Depot oder für das Gesamtdepot
- Fortschritt, Restmenge und optional benötigter Fiatbetrag

#### Charts, Markteinschätzung und Auswertungen

- Bitcoin-Kurs
- adaptive **0–100-Markteinschätzung** aus öffentlichen historischen Kursdaten; ausdrücklich kein Kaufsignal
- kausaler historischer Markteinschätzungs-Chart mit BTC-Preis-Overlay, Fadenkreuzwerten, einstellbarer Preis-Deckkraft und linearer/logarithmischer Preisachse
- optionale **kausale EMA-Glättung** (Aus / 3 / 5 / 7 / 14 / 30 Punkte); rein visuell und identisch für das Startseiten-Overlay
- Startseiten-Chartmodus **Bitcoin-Kurs + Markteinschätzung** mit eigener linearer Scoreachse, die auf den sichtbaren Scorebereich skaliert
- echte Kurzzeit-Score-Snapshots ohne zusätzliche Modelllast: **1 h bei Heute · 6 h bei Seit Wochenbeginn/1 Woche · 12 h bei Seit Monatsbeginn/30 Tage**; die Punkte stammen aus der bestehenden 5-Minuten-Current-Score-Berechnung, werden nicht interpoliert und bis zu 45 Tage gespeichert
- Boden-/Top-Zonen und Bestätigungsdiagnostik, einstellbare Gewichte, Schwellen sowie adaptive Volatilitäts-/Zyklusfenster
- Stack-Verlauf
- Portfoliowert
- Gesamtgewinn/-verlust
- Einstand + Buchgewinn/-verlust
- kombinierte Overlays
- linke und rechte Y-Achse unabhängig linear/logarithmisch
- Zeiträume: **1 Tag · seit Wochenbeginn · 1 Woche · seit Monatsbeginn · 30 Tage · 90 Tage · YTD · 1 Jahr · 3 Jahre · 5 Jahre · 10 Jahre · seit erstem Kauf · Max**
- TWR, auf den gewählten Zeitraum annualisierte XIRR, BTC-Markt-CAGR, DCA-, Drawdown- und cashflow-neutraler HODL-Benchmark
- Stacking-Geschwindigkeit, Netto-Fiat-Investment, Gebührenquoten und Stack-Altersverteilung
- Bitcoin-Netzwerk-, Milestone- und Halving-Markierungen

#### Sats Sentinel

- Privacy-first Watch-only-Überwachung für Adressen, Adressgruppen, XPUB/YPUB/ZPUB und Descriptoren; keine Private Keys, Seeds, Signaturen oder Ausgaben
- frei wählbare Abfragequelle: **Automatisch · Fulcrum/Electrum · electrs/Electrum · eigene Mempool-Instanz · konfigurierte öffentliche Mempool-Instanz über Tor**
- explizite Quellenwahl ist **Fail Closed**: fällt die gewählte eigene Quelle aus, meldet Sentinel offline/teilweise und wechselt niemals heimlich zu einem öffentlichen Provider
- lokale/private Fulcrum-/electrs-/Mempool-Ziele dürfen direkt im LAN laufen; `.onion` und öffentliche Ziele gehen über Tor mit Remote-DNS
- Fulcrum/electrs nutzen Electrum-Scripthash-Abfragen für Balance/History/UTXOs; TLS und exaktes SHA-256-Zertifikat-Pinning unterstützen selbstsignierte Fulcrum-Zertifikate
- separater gerätegebunden AES-256-GCM-verschlüsselter Sentinel-Runtime-Tresor enthält das für die 24/7-Überwachung bei gesperrtem Tresor nötige öffentliche Watch-only-Material (Adresse/XPUB/Descriptor, abgeleitete Adressen und Verbindungsmetadaten); niemals Seeds, Private Keys, xprv oder Spend-/Signierschlüssel
- bei gesperrtem Portfolio-Tresor ist die komplette Sentinel-Wallet-/Adress-/Bestands-/Quellenkarte **standardmäßig verborgen** und wird vom gesperrten Frontend gar nicht angefordert; im entsperrten Sentinel-Bereich kann die Anzeige lokal pro Browser/Gerät ausdrücklich aktiviert werden, ohne Überwachung oder Benachrichtigungen zu beeinflussen
- Bewegungsjournal mit Sender → Richtung → Empfänger, Kategorien, Notizen, Schwellen und Pagination; TXIDs/Adressen können auf den getrennt konfigurierten Mempool-Explorer verlinken
- Home-Assistant-Events, Persistent Notifications, mehrere `notify.*`-Dienste, self-hosted ntfy und Webhooks mit diskreter/normaler/detaillierter Darstellung
- beim Entfernen eines Watch-Eintrags wird auch dessen komplette Journal-Historie dauerhaft aus dem verschlüsselten Sentinel-Cache gelöscht

### Backup und Datenportabilität

Das verschlüsselte portable `.bstbackup` enthält bewusst nur:

1. Buchungen (Käufe, Einnahmen, Verkäufe, Ausgaben, Transaktionsgebühren und Stack-Einträge)
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

Aktueller Projektstand: **v0.21.0.13**. Dieses Release bündelt die RC-Linie nach v0.21.0.12 bis RC20 und behebt HD-Wallet-False-Zero-Erkennung, Home-Assistant-Timer-/CPU-Regressions, Companion-QR-Scanning und veralteten Wallet-Card-Frontend-Zustand.

#### Änderungen seit v0.21.0.12

- **HD-Discovery-Bootstrap:** bestehende kleine Gap-Werte bleiben benutzergesteuert, aber die Initialsuche prüft 20 Adressen, bevor ein Branch als unbenutzt gilt. Neue HD-Watches starten mit Receive 20 / Change 20.
- **xpub-Auto-Script-Erkennung:** Historie entscheidet zwischen Native SegWit, Nested SegWit, Taproot und Legacy; das nackte xpub-Präfix gilt nicht mehr als eindeutiger Legacy-Hinweis.
- **Locked-Sentinel-Privatsphäre:** Der verschlüsselte Runtime-Tresor hält die Sentinel-Überwachung bei gesperrtem Portfolio-Tresor aktiv, aber der Sperrbildschirm blendet die komplette Wallet-/Adress-/Bestands-/Quellenkarte standardmäßig aus und lädt dieses Management-Payload nicht. Eine lokale Anzeigeoption kann sie bewusst wieder einblenden; Überwachung/Alarme laufen in beiden Fällen weiter.
- **Weniger Fulcrum/electrs-Last:** begrenzte Batches/Yields, stündlich geslictes Reconcile und zusammengefasste Runtime-Store-Writes reduzieren Core-/Storage-Churn.
- **Markteinschätzungs-Performance:** Der Kurschart bleibt live, der rechenintensive aktuelle Score wird dagegen höchstens alle fünf Minuten gemeinsam im Executor mit dem dann neuesten Kurs berechnet. Diese ohnehin vorhandenen Modellläufe speisen zusätzlich einen kleinen öffentlichen Intraday-Snapshot-Store; die Übersicht verdichtet echte Werte auf 1 h / 6 h / 12 h, ohne zusätzliche Modellberechnung. Die kausale History-Score-Serie liegt persistent in Home Assistant und wird nur bei geänderten Modellparametern/Modellversion/Währung oder historischen Tageskursen neu aufgebaut. Overlay-Requests sind pro Zeitraum race-sicher dedupliziert; kurze Ansichten erhalten zusätzlich einen unsichtbaren historischen Vorlauf.
- **Vault-Timer-Fix:** alte Callback-Registrierungen werden entfernt/neu gebunden; der Expiry-Worker kann den datetime-Tick nicht mehr als `hass` erhalten.
- **Companion-QR-Fix:** Scan-Ergebnis/Abbruch werden nach External-Bus-Nachrichtentyp mit 3-Sekunden-Start-Handshake verarbeitet.
- **Eingeklappte Wallet-Karten:** Standard eingeklappt; v5-Local-Preference setzt veralteten Produktiv-Browser-Zustand einmalig zurück.
- **Begrenztes Journal:** Sentinel behält die neuesten 5.000 Aktivitätseinträge.
- **Prüfung:** statische/Security-, Funktions-/Performance-, Current-Cache- sowie persistente History-Cache-/Overlay-Regressionen bestanden. Das hochgeladene RC20-Component-Archiv enthielt nicht die komplette Repository-Testsuite; das frühere 502+8-Ergebnis wird nicht als erneut ausgeführt dargestellt.

**Nach dem Update Home Assistant Core vollständig neu starten und das Frontend hart neu laden.**

Das **Tor Gateway bleibt v0.21.0.3**.

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

