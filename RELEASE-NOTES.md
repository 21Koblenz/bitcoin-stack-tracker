# Bitcoin Stack Tracker v0.21.0.5 Hotfix

## App- und Funktionsübersicht

**Bitcoin Stack Tracker** ist ein lokaler Bitcoin-only Portfolio- und Stack-Tracker für Home Assistant mit getrenntem Tor Gateway für öffentliche Datenquellen.

### Kernfunktionen

- mehrere Depots und Gesamtdepot
- Käufe, Verkäufe, Ausgaben, Gebühren, Notizen und depotweises FIFO
- CSV-Import mit prüfbarer Vorschau und ID-basierter Dubletten-Erkennung
- historische Kurs-, Stack-, Portfolio-, Einstands- und Gewinn/Verlust-Charts
- TWR, XIRR, DCA und Drawdown
- Ziele, Milestones, Halving- und Netzwerk-Markierungen
- verschlüsselte portable `.bstbackup`-Backups
- Privacy-/Diskretmodus, BTC/Sats und fiatfreie Ansicht
- Deutsch/Englisch sowie Desktop-/Smartphone-Ansicht
- natives Home-Assistant-Seitenleistenpanel

### Datenschutz und Netzwerk

- Portfolio- und Buchungsdaten bleiben lokal in Home Assistant.
- Öffentliche Kurs- und Historienabfragen laufen über das getrennte Tor Gateway.
- Das Gateway verwendet nftables Fail Closed und hat keinen Zugriff auf Portfolio, Passwörter oder Home-Assistant-API-Tokens.
- Lokale private Node-Ziele dürfen direkt im LAN angesprochen werden.

---

## Changelog v0.21.0.5

Dieser Hotfix behebt einen Service-Schema-Fehler aus **v0.21.0.4**.

- **CSV-Import wieder speicherbar:** `import_ref_hash` wird jetzt vom Home-Assistant-Service `bulk_import` akzeptiert.
- **Kraken-Dublettenfix funktioniert vollständig:** Unterschiedliche `txid`/`ordertxid` bleiben auch dann getrennte Buchungen, wenn Zeitpunkt, Menge, Kurs und Gebühr identisch sind.
- **Anbieterübergreifend:** Die gleiche Import-ID-Logik bleibt für unterstützte Order-, Trade-, TX- und Transaktions-IDs aktiv.
- **Regressionstest:** Prüft explizit, dass der Frontend-Payload vom `bulk_import`-Schema angenommen wird.
- **Cache-Busting:** Frontend-Assets auf `v021005-28d54128` aktualisiert.
- **Tor Gateway:** bleibt auf `v0.21.0.3`, da dieser Hotfix ausschließlich die Custom Integration betrifft.

**Full Changelog:**  
https://github.com/21Koblenz/bitcoin-stack-tracker/compare/v0.21.0.4...v0.21.0.5
