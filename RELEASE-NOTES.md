# Bitcoin Stack Tracker v0.21.0.0

## App- und Funktionsübersicht

**Bitcoin Stack Tracker** ist ein lokaler Bitcoin-only Portfolio- und Stack-Tracker für Home Assistant mit getrenntem Tor Gateway für öffentliche Datenquellen.

### Kernfunktionen

- mehrere Depots und Gesamtdepot
- Käufe, Verkäufe, Gebühren, Notizen und depotweises FIFO
- Verkaufsübersicht mit FIFO-Einstand, Erlös, Gewinn/Verlust und Rendite
- historische Kurse, Stack-, Portfolio- und P/L-Charts
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

## Changelog v0.21.0.0

Dies ist der **erste öffentliche Release** des Repositorys.

- vollständiger Bitcoin-only Portfolio-/FIFO-/Chart-/Ziel-Funktionsumfang
- mobile Home-Assistant-Companion-Kompatibilität
- versionierte Frontend-Assets gegen veraltete Browser-/WebView-Caches
- automatische Erkennung des Supervisor-internen Tor-Gateway-Alias für GitHub- und lokale Installationen
- fail-closed DNS-/SOCKS-/Gateway-Prüfung ohne öffentlichen Fallback
- portable verschlüsselte Backups mit bewusst begrenztem Restore-Umfang
- gehärtete Panel-Kommunikation, CSP und Netzwerkgrenzen
- SBOM und Release-Integritätswerkzeuge
- Lizenzwechsel des neuen öffentlichen Repository-Stands auf **AGPL-3.0-only**
