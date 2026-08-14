# Bitcoin Stack Tracker v0.21.0.9

## App- und Funktionsübersicht

**Bitcoin Stack Tracker** ist ein lokaler Bitcoin-only Portfolio- und Stack-Tracker für Home Assistant mit getrenntem Tor Gateway für öffentliche Datenquellen.

### Kernfunktionen

- mehrere Depots und Gesamtdepot
- Käufe, Einnahmen, Verkäufe, Ausgaben, Transaktionsgebühren, Stack-Einträge und Notizen
- depotweises FIFO mit realisiertem/unrealisiertem Gewinn/Verlust und zusätzlichem historischen Durchschnittseinstand je Abgang
- eigenständige On-Chain-/Lightning-Gebühren in BTC/Sats mit Stack-Abzug und historischem Fiat-Gegenwert
- CSV-Import mit bearbeitbarer Vorschau und ID-/Werte-basierter Dubletten-Erkennung
- direkte Importer u. a. für Kraken, Coinbase, Binance, Bitpanda, **Revolut X**, Peach Bitcoin, Coinfinity, Pocket Bitcoin und Wavespace
- historische Kurs-, Stack-, Portfolio-, Einstands- und Gewinn/Verlust-Charts
- TWR, XIRR, Bitcoin-CAGR, DCA, Drawdown und cashflow-neutraler HODL-Benchmark
- Haltezeit-Regel, gewichtetes Stack-Alter, Altersverteilung und FIFO-Abgänge
- Stacking-Geschwindigkeit, Netto-Fiat-Investment und Gebührenanalyse
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

## Änderungen in v0.21.0.9

### Revolut X CSV-Import

- Neues Format: `Symbol`, `Type`, `Quantity`, `Price`, `Value`, `Fees`, `Date`.
- Nur BTC/XBT wird importiert. `Buy` → Kauf, `Sell` → Verkauf.
- `Quantity` wird direkt als BTC interpretiert.
- `Value` ist der Fiat-Handelswert vor Gebühren; `Fees` bleibt eine separate Fiatgebühr.
- Kauf: `Value + Fees`; Verkauf: `Value - Fees`.
- Unterstützt Tag-zuerst (`21 Jan 2026, 21:21:21`) und Monat-zuerst mit AM/PM.
- Fehlt `Price`, wird er aus `Value / Quantity` rekonstruiert.

### Neue manuelle Buchungen

- **Einnahme:** BTC-Zugang mit bekanntem historischem Wert; erzeugt einen FIFO-Lot wie ein Kauf, bleibt aber als Einnahme getrennt.
- **Ausgabe:** jetzt manuell auswählbar; wird als FIFO-Abgang mit realisiertem Gewinn/Verlust gerechnet, aber nicht als Verkauf bezeichnet.
- **Transaktionsgebühr:** eigenständiger On-Chain-/Lightning-BTC-Abgang in sats oder BTC. Er mindert den Stack und verbraucht FIFO, erzeugt aber keinen Fiat-Verkaufserlös.
- Beim Bearbeiten kann die Buchungsart geändert werden. Danach wird FIFO vollständig neu berechnet und validiert.

### Gebühren und Stack-Konsistenz

- On-Chain-/Lightning-Gebühren können für Eigenüberweisungen, UTXO-Konsolidierungen und sonstige Wallet-Operationen erfasst werden, damit Dashboard- und Wallet-Stack nicht auseinanderlaufen.
- Der Fiat-Gegenwert wird anhand des historischen BTC-Kurses am Buchungszeitpunkt ausgewiesen.
- Alte/importierte `fee_btc`-Felder werden nur dann zusätzlich vom Stack abgezogen, wenn sie ausdrücklich als stack-wirksam markiert sind; so werden Nettoimporte nicht doppelt belastet.
- „Gesamte Gebühren“ enthält explizite Fiatgebühren plus Fiat-Gegenwerte der erfassten BTC-/Sats-Gebühren. Handelsquoten bleiben auf Handels-/Ausgabevolumen bezogen.

### Plausibilitätsprüfung manueller Buchungen

- Kauf, Einnahme, Verkauf und Ausgabe werden mit dem historischen BTC-Kurs des Buchungstags/-zeitpunkts verglichen.
- Ab 10 % Abweichung erscheint eine Warnung. Sie blockiert das Speichern nicht.
- Angezeigt werden eingetragener Kurs, historischer Referenzkurs und Abweichung.
- Für alte Zeitpunkte wird niemals auf den heutigen Live-Kurs zurückgefallen; fehlt eine historische Referenz, wird die Prüfung übersprungen.
- Bei reinen Transaktionsgebühren wird der historische Kurs zur Fiatbewertung automatisch verwendet.

### Übersicht und Performance

- **„Fiat in Sicherheit gebracht“ → „Kaufkraft in Sicherheit gebracht“**.
- Separate Übersichten für Verkäufe, Ausgaben, Einnahmen und Transaktionsgebühren.
- Verkäufe und Ausgaben zeigen jeweils ihren realisierten Gewinn/Verlust; zusätzlich gibt es die Gesamtsumme des realisierten Ergebnisses.
- Neue Zeitraumreihenfolge: **1 Tag · seit Wochenbeginn · 1 Woche · seit Monatsbeginn · 30 Tage · 90 Tage · YTD · 1 Jahr · 3 Jahre · 5 Jahre · 10 Jahre · seit erstem Kauf · Max**.
- XIRR bleibt auf den ausgewählten Zeitraum bezogen und wird auf ein Jahr hochgerechnet.
- TWR neutralisiert externe Zu-/Abflüsse, sodass zusätzliche Käufe oder Einnahmen keine künstliche Rendite erzeugen.
- CAGR ist ausdrücklich die durchschnittliche annualisierte Entwicklung des Bitcoin-Marktpreises seit der ersten bewerteten Buchung, nicht die persönliche Rendite.

### Qualitätssicherung

- Gezielte v0.21.0.9-Regressionstests für Revolut X, historische Referenzkurse, Einnahmen, Ausgaben/FIFO, On-Chain-/Lightning-Gebühren und Kompatibilität mit älteren `fee_btc`-Daten.
- Finale lokale Testsuite: **373 Tests + 8 Subtests bestanden**.
- JavaScript-Syntax, Python-Compile, JSON/YAML und Versionskonsistenz wurden für den Release-Stand geprüft.

### Kompatibilität

- Custom Integration: **v0.21.0.9**
- Tor Gateway: weiterhin **v0.21.0.3**
- Der grundlegende Berechnungs-, Datenschutz- und Security-Audit aus v0.21.0.6 bleibt die bestehende Audit-Basis; v0.21.0.9 ergänzt gezielte Regressionen für die neuen Pfade.

**Full Changelog:** [`v0.21.0.8...v0.21.0.9`](https://github.com/21Koblenz/bitcoin-stack-tracker/compare/v0.21.0.8...v0.21.0.9)
