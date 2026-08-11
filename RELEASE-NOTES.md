# Bitcoin Stack Tracker v0.21.0.6

## App- und Funktionsübersicht

**Bitcoin Stack Tracker** ist ein lokaler Bitcoin-only Portfolio- und Stack-Tracker für Home Assistant mit getrenntem Tor Gateway für öffentliche Datenquellen.

### Kernfunktionen

- mehrere Depots und Gesamtdepot
- Käufe, Verkäufe, Ausgaben, Gebühren, Notizen und depotweises FIFO
- CSV-Import mit bearbeitbarer Vorschau und ID-basierter Dubletten-Erkennung
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

## Änderungen in v0.21.0.6

### Berechnungs-Audit

- FIFO verarbeitet Verkäufe **und bewertete Ausgaben** als Abgänge; Wavespace-/Kartenzahlungen erscheinen dadurch korrekt in der FIFO-Abgangsübersicht.
- Jeder FIFO-Abgang enthält zusätzlich **Ø Einkauf bis dahin** und **Ø-P/L**: einen portfolio-weiten, BTC-gewichteten historischen Durchschnitt aller Käufe derselben Fiatwährung bis zum jeweiligen Abgangszeitpunkt. Dieser Vergleich dient der intuitiven Einordnung und bleibt strikt getrennt vom FIFO-Ergebnis. Pro Buchungs-/Lotzeile werden FIFO-Gewinn und FIFO-Rendite sowie Ø-Gewinn und Ø-Rendite separat angezeigt; auch die FIFO-Abgangs-Gesamtübersicht zeigt beide Rechenwege getrennt.
- Teilweise verbrauchte Kauf-Lots behalten ihren exakten Rest und werden vom nächsten Abgang zuerst weiterverwendet.
- Kaufkostenbasis inklusive Kaufgebühren sowie proportionale Abgangsfee-Verteilung wurden erneut regressionsgetestet.
- Metriken und FIFO verwenden bei identischem Zeitpunkt dieselbe Reihenfolge: BTC-Zugang vor BTC-Abgang.
- Add/Edit/Delete/Bulk-Import validieren einen Kandidaten atomar und verhindern neuen oder größeren Oversell.
- Drawdown bis 0 wird korrekt als -100 % erkannt; ein erneutes gleich hohes ATH setzt `Tage seit ATH` zurück.
- XIRR verweigert gemischte Fiat-Cashflows ohne FX-Daten statt eine Umrechnung zu erfinden.
- Altersbuckets verwenden 365,2425 Tage/Jahr; die konfigurierbare Haltezeit-Regel (standardmäßig 365 Tage) bleibt eine separate exakte Tagesregel.
- Neue/bearbeitete Buchungen mehr als fünf Minuten in der Zukunft werden abgewiesen.

### Kennzahlen

- BTC-CAGR seit erster bewerteter Buchung mit klarer Abgrenzung zu TWR/XIRR.
- Stacking-Geschwindigkeit für 30 Tage, 365 Tage und seit Beginn.
- realisierter, unrealisierter und gesamter Gewinn/Verlust getrennt.
- Netto investiertes Fiat.
- aktueller/maximaler Drawdown, Tage seit Hoch und längste Erholungsdauer.
- Haltezeit-Block: über/unter Regel, nächste 30/90 Tage, gewichtetes Stack-Alter, ältestes offenes Lot und Altersverteilung.
- volumengewichtete Kauf- und **Abgangsgebührenquote**; Abgänge schließen bewertete Ausgaben ein.
- BTC-Gebühren werden als tatsächliche BTC/Sats-Gebühren ausgewiesen; unbekannte historische Werte werden nicht geraten.
- cashflow-neutraler HODL-Benchmark mit denselben externen Ein-/Auszahlungen wie die tatsächliche Strategie.

### Performance

- FIFO verwendet einen nur für den aktuellen Rechenlauf gültigen Lot-Cursor statt verbrauchte Lots wiederholt zu durchsuchen.
- große Bulk-Imports verwenden den bereits zur Validierung berechneten FIFO-Cache weiter.
- historische Tagesstände werden in einem chronologischen Durchlauf aufgebaut statt FIFO für jeden Tag komplett neu zu rechnen.
- historische Preiszuordnung verwendet vorbereitete Reihen und Binärsuche; TWR/XIRR/Chartserien werden pro Dashboard-Snapshot gecacht.
- schwere Overview-Berechnungen laufen nach dem sichtbaren Chart in einer Idle-Phase und werden beim Reiterwechsel abgebrochen.
- Dashboard-Sektionen werden lazy geladen; Einstellungen/Sicherheit benötigen kein vollständiges Ledger.
- FIFO-/Ledger-Indizes reduzieren wiederholte lineare Browser-Suchen.

### Datenschutz, Privatsphäre und Sicherheit

- vollständiges Ledger wird nicht mehr für CSV-Dublettenprüfung in den Browser geladen.
- neuer Core-Dubletten-Endpunkt liefert ausschließlich boolesche Flags; Import-Hashes verbleiben in Core.
- Ledger-Payload verwendet eine Allow-List und entfernt interne `import_ref_hash`-/`fee_btc`-Metadaten.
- sensible Panel-Antworten sind `no-store`, private, same-origin und no-referrer gehärtet.
- CSP blockiert direkte Frontend-Netzwerkverbindungen.
- veraltete Lazy-Responses können keinen neueren Dashboard-Zustand überschreiben.
- Nicht-Owner erhalten weiterhin nur redigierte Verbindungsinformationen.
- schwerer Dublettenabgleich ist begrenzt/rate-limitiert.

### Charts und FIFO-Oberfläche

- linke und rechte Y-Achse können unabhängig Linear/Log eingestellt werden, z. B. BTC-Preis = Log und Stack = Log.
- `FIFO SALES / Verkaufsübersicht` wurde in **FIFO ABGÄNGE / FIFO-Abgänge** überführt.
- Verkauf und Ausgabe werden als Art angezeigt; die Kopfzahl zählt echte Abgangsbuchungen statt einzelne Lot-Matches.

### Release/Kompatibilität

- Frontend Cache-Busting: `v021006-733b783d`.
- **Tor Gateway bleibt v0.21.0.3**; keine Gateway-Änderung in diesem Release.
- v0.21.0.6 bündelt **alle Änderungen seit v0.21.0.5**: Large-Ledger-Performance, neue Kennzahlen, FIFO-Abgänge, Chart-Skalen sowie die abschließenden Berechnungs-/Datenschutz-/Privatsphäre-Audit-Fixes.

### Audit und Qualitätssicherung

Der vollständige Bericht steht in [`AUDIT-v0.21.0.6.md`](AUDIT-v0.21.0.6.md), die Berechnungsdetails in [`MATH-AUDIT.md`](MATH-AUDIT.md). Das Audit ist ein Code-/Regressionstest-Audit und kein externer Penetrationstest.

Finale Testsuite: **351 Tests + 8 Subtests bestanden**; JavaScript-Numeriktest und Syntaxprüfungen ebenfalls erfolgreich.

**Full Changelog:** [`v0.21.0.5...v0.21.0.6`](https://github.com/21Koblenz/bitcoin-stack-tracker/compare/v0.21.0.5...v0.21.0.6)
