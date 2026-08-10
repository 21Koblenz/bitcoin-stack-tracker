# Bitcoin Stack Tracker v0.21.0.3

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

## Changelog v0.21.0.3

Dieser Hotfix korrigiert CSV-Import, Sats-Darstellung und Gebührenbehandlung auf Basis von **v0.21.0.2**.

- **Coinfinity:** `Amount Crypto` wird als BTC gelesen; `Mining Fee Crypto` als Sats. Leer/0 bedeutet Lightning, ein positiver Mining-Fee-Wert On-Chain.
- **Coinfinity-Zahlbetrag:** `Amount EUR` bleibt der tatsächlich überwiesene Betrag. Service- und Mining-Fee werden davon abgezogen und nicht doppelt aufgeschlagen; der erhaltene BTC-Betrag bleibt unverändert.
- **Sats-Anzeige:** Ganzzahlige Sats verlieren keine nachgestellten Nullen mehr. `0.00020000 BTC` entspricht zuverlässig 20.000 sats.
- **BTC-Verkaufsfees:** Eindeutig in BTC/Sats ausgewiesene Verkaufsgebühren werden als zusätzlicher Stack-Abgang berücksichtigt; der Fiat-Gegenwert der Fee bleibt separat erhalten.
- **Wavespace-Kartengebühren:** Kartenfee-Sats werden zusätzlich zum Kartenumsatz vom Stack abgezogen.
- **Wavespace-Ausgaben:** `payWaveLowValuePurchase`, `POSPurchase`, `card purchase` und `card payment` werden als **Ausgabe** importiert, aber für die Fiat-Kontrollrechnung wie ein Verkauf behandelt.
- **Wavespace-Verkäufe:** Normale BTC→Fiat-Swaps sowie ATM-Bargeldabhebungen bleiben Verkäufe.
- **Export:** Bewertete Ausgaben verwenden konsistent `BTC × Kurs − Fee` als Fiat-Gesamtwert.
- **Tests:** Regressionstests decken das reale Coinfinity-Schema, Sats mit Endnullen, BTC-Verkaufsfees und Wavespace-Kartenausgaben ab.

Die vollständige Versionshistorie steht in `CHANGELOG.md`.
