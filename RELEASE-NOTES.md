# Bitcoin Stack Tracker v0.21.0.2

## App- und Funktionsübersicht

**Bitcoin Stack Tracker** ist ein lokaler Bitcoin-only Portfolio- und Stack-Tracker für Home Assistant mit getrenntem Tor Gateway für öffentliche Datenquellen.

### Kernfunktionen

- mehrere Depots und Gesamtdepot
- Käufe, Verkäufe, Gebühren, Notizen und depotweises FIFO
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

## Changelog v0.21.0.2

Dieser Hotfix korrigiert die beim mathematischen Audit gefundenen Rechen- und Chartfehler auf Basis von **v0.21.0.1**.

- **TWR:** Cashflows werden am Buchungszeitpunkt getrennt; Teilperioden werden geometrisch verknüpft. Gebühren bleiben Performancekosten. Komplette Auszahlungen werden korrekt behandelt.
- **XIRR:** 365-Tage-Konvention mit ganzen Zahlungstagen; sehr große annualisierte Kurzfrist-Raten werden unterstützt; mehrere gültige Lösungen werden als mehrdeutig angezeigt.
- **Drawdown:** Berechnung auf der vollständigen verfügbaren Analyse-Reihe statt auf der verdichteten Display-Reihe.
- **Intraday-P/L:** Einstand, realisierter Gewinn und bekannte BTC werden nach jeder einzelnen Buchung fortgeschrieben.
- **Tagesgrenzen:** Tageskurse und FIFO-Snapshots werden konsistent als Tagesendzustände verarbeitet.
- **UTC/FIFO:** Sortierung, Migration, neue und bearbeitete Buchungen verwenden echte UTC-Zeitpunkte; Offset-Strings können die FIFO-Reihenfolge nicht mehr verdrehen.
- **FIFO-Verkäufe:** Multiwährungs-Summen sind konsistent; anteilige Verkaufsgebühren werden auch bei unaufgelösten/überverkauften Anteilen im Nettoerlös berücksichtigt.
- **DCA:** Bester/schlechtester Kauf basiert auf effektivem Einstand inklusive Kaufgebühren; persönliche Sparjahre beginnen beim ersten passenden Kauf.
- **Gewinnkennzahlen:** Der irreführende pseudo-ROI auf kumulierte Kaufaufwendungen wurde entfernt. Offener Buchgewinn-Prozent bleibt an den offenen Einstand gebunden.
- **Sensoren:** Mathematisch undefinierte Durchschnitts-/Prozentwerte werden als nicht verfügbar statt als 0 ausgegeben.
- **Chartdarstellung:** Langzeitpunkte behalten ihren realen Beobachtungstag; Display-Verdichtung beeinflusst die Analytics nicht.
- **Tests:** Golden- und Regressionstests decken TWR, XIRR, Drawdown, FIFO-Zeitzonen, Gebühren, DCA und Intraday-Zustände ab.

Ausführliche Formeln und Prüffälle stehen in `MATH-AUDIT.md`.
