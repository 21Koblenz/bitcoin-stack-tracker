# Bitcoin Stack Tracker v0.21.0.8

## App- und Funktionsübersicht

**Bitcoin Stack Tracker** ist ein lokaler Bitcoin-only Portfolio- und Stack-Tracker für Home Assistant mit getrenntem Tor Gateway für öffentliche Datenquellen.

### Kernfunktionen

- mehrere Depots und Gesamtdepot
- Käufe, Verkäufe, Ausgaben, Gebühren, Notizen und depotweises FIFO
- CSV-Import mit bearbeitbarer Vorschau und ID-basierter Dubletten-Erkennung
- direkte Importer u. a. für Kraken, Coinbase, Binance, Bitpanda, Peach Bitcoin, Coinfinity, Pocket Bitcoin und Wavespace
- historische Kurs-, Stack-, Portfolio-, Einstands- und Gewinn/Verlust-Charts
- TWR, XIRR, BTC-CAGR, DCA, Drawdown und cashflow-neutraler HODL-Benchmark
- Haltezeit-Regel, gewichtetes Stack-Alter, Altersverteilung und FIFO-Abgänge
- Stacking-Geschwindigkeit, Netto-Fiat-Investment und Gebührenquoten
- getrennte Linear/Log-Skalen für linke und rechte Chart-Achse
- verschlüsselte portable `.bstbackup`-Backups
- Privacy-/Diskretmodus, BTC/Sats und fiatfreie Ansicht
- Deutsch/Englisch sowie Desktop-/Smartphone-Ansicht
- natives Home-Assistant-Seitenleistenpanel

### Datenschutz und Netzwerk

- Portfolio- und Buchungsdaten bleiben lokal in Home Assistant.
- CSV-Dublettenabgleiche bleiben in Core; bestehende Import-Hashes werden nicht in den Browser geladen.
- Öffentliche Kurs- und Historienabfragen laufen über das getrennte Tor Gateway.
- Lokale private Node-Ziele dürfen direkt im LAN angesprochen werden.
- Das Gateway hat keinen Zugriff auf Portfolio, Tresorpasswort oder Home-Assistant-API-Token.
---

## Änderungen in v0.21.0.8

### Peach Bitcoin CSV

- Neuer eigener Parser für Peach Bitcoin.
- Erwartete Spalten: `Date`, `Trade ID`, `Type`, `Amount`, `Price`, `Bitcoin Price`, `Currency`, `Premium`.
- `Amount` wird als Satoshi-Ganzzahl gelesen und exakt durch 100.000.000 in BTC umgerechnet.
- `bought`/`buy` wird als Kauf und `sold`/`sell` als Verkauf verarbeitet.
- `Trade ID` ist die primäre stabile Import-Identität.

### Premium und Gebühren

- `Price` bleibt der autoritative tatsächlich gezahlte bzw. erhaltene Fiatbetrag.
- `Bitcoin Price` enthält bei Peach den Premium-Aufschlag.
- Bei Käufen wird der Markt-/Referenzkurs ohne Premium mit `Bitcoin Price / (1 + Premium/100)` rekonstruiert.
- Die Differenz zwischen tatsächlichem `Price` und BTC-Wert zum rekonstruierten Marktpreis wird als Fiatgebühr geführt. Dadurch bleibt die Gesamtkostenrechnung konsistent und die Gebühr wird nicht doppelt auf den FIFO-Einstand aufgeschlagen.
- Bei Verkäufen wird der tatsächliche Fiat-Erlös verwendet; ein Premiumwert wird nicht pauschal als zusätzliche positive Gebühr interpretiert.

### README und Dokumentation

- Haupt-README vollständig zweisprachig Deutsch/Englisch.
- Peach Bitcoin in der CSV-Importübersicht aufgenommen.
- `CSV-IMPORT.md` um Peach-Erkennung, Sats-Einheit, Premium-Logik und Dublettenidentität ergänzt.

### Kompatibilität

- Custom Integration: **v0.21.0.8**
- Tor Gateway: weiterhin **v0.21.0.3**
- Mindestversion laut `hacs.json`: Home Assistant **2026.7.0**
- Kein Frontend-Cache-Busting erforderlich, da dieser Release keine Frontend-Assets ändert.

### Qualitätssicherung

Der grundlegende Berechnungs-, Datenschutz- und Security-Audit aus v0.21.0.6 bleibt bestehen. Für Peach wurden fünf gezielte Parser-Regressionstests ergänzt und erfolgreich ausgeführt.

**Full Changelog:** [`v0.21.0.7...v0.21.0.8`](https://github.com/21Koblenz/bitcoin-stack-tracker/compare/v0.21.0.7...v0.21.0.8)
