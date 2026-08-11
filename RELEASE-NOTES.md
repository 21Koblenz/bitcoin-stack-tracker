# Bitcoin Stack Tracker v0.21.0.4

## App- und Funktionsübersicht

**Bitcoin Stack Tracker** ist ein lokaler Bitcoin-only Portfolio- und Stack-Tracker für Home Assistant mit getrenntem Tor Gateway für öffentliche Datenquellen.

### Kernfunktionen

- mehrere Depots und Gesamtdepot
- Käufe, Verkäufe, Ausgaben, Gebühren, Notizen und depotweises FIFO
- Verkaufsübersicht mit FIFO-Einstand, Nettoerlös, Gewinn/Verlust und Rendite
- historische Kurs-, Stack-, Portfolio-, Einstands- und Gewinn/Verlust-Charts
- TWR, XIRR, DCA und Drawdown
- Ziele, Milestones, Halving- und Netzwerk-Markierungen
- CSV-Import mit prüfbarer Vorschau
- verschlüsselte portable `.bstbackup`-Backups
- Privacy-/Diskretmodus, BTC/Sats und fiatfreie Ansicht
- Deutsch/Englisch sowie Desktop-/Smartphone-Ansicht
- natives Home-Assistant-Seitenleistenpanel

### Datenschutz und Netzwerk

- Portfolio- und Buchungsdaten bleiben lokal in Home Assistant.
- Öffentliche Kurs- und Historienabfragen laufen über das getrennte Tor Gateway.
- Das Gateway verwendet nftables Fail Closed und hat keinen Zugriff auf Portfolio, Passwörter oder Home-Assistant-API-Tokens.
- Lokale private Node-Ziele dürfen direkt im LAN angesprochen werden.

## Changelog v0.21.0.4

Dieser Hotfix korrigiert die anbieterübergreifende CSV-Dublettenerkennung.

- **ID vor Wertevergleich:** Wenn eine CSV eine Order-, Trade-, Transaktions- oder Referenz-ID enthält, entscheidet diese Identität über Dubletten.
- **Kraken:** Mehrere Ausführungen mit exakt gleichem Zeitpunkt, BTC-Betrag, Kurs und Fee bleiben getrennt, wenn sich `txid` oder `ordertxid` unterscheidet.
- **Anbieterübergreifend:** Dasselbe Prinzip wird für unterstützte Coinbase-, Binance-, CoinTracking-/Pocket-, Coinfinity-, Wavespace- und generische CSV-Pfade genutzt, sofern eine eindeutige ID vorhanden ist.
- **Datenschutz:** Die Roh-ID wird nicht automatisch im Ledger gespeichert. Persistiert wird nur ein SHA-256-Hash aus Quelle und Quell-ID zur späteren Dublettenerkennung.
- **Fallback:** Fehlt eine ID, bleibt der bisherige Werte-Fingerprint aktiv.
- **Legacy-Imports:** Bereits vorhandene Altbuchungen ohne ID-Hash werden beim ersten erneuten Import mengenbasiert berücksichtigt, ohne zusätzliche gleichwertige Trades mit unterschiedlichen IDs zu verschlucken.
- **Tor Gateway:** bleibt auf **v0.21.0.3**, weil dieser Hotfix nur die Integration betrifft.

Die vollständige Versionshistorie steht in `CHANGELOG.md`.
