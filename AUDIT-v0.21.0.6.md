# Audit v0.21.0.6 · Berechnung, Datenschutz, Privatsphäre und Sicherheit

Datum: 11.08.2026

## Umfang

Geprüft wurden die Home-Assistant-Custom-Integration, FIFO-/Metrik-/Historienlogik, CSV-Import/Dublettenprüfung, native Panel-RPC-Grenze, Browser-Datenhaltung, Tresor-/Backup-Kryptografie, Berechtigungsprüfung und die Datenwege zu öffentlichen Quellen. Das getrennte Tor Gateway wurde auf seine Schnittstellengrenze geprüft, aber in diesem Release nicht geändert.

Das ist ein **Code- und Regressionstest-Audit**, kein unabhängiger externer Penetrationstest.

## Gefundene und behobene Berechnungsprobleme

- FIFO-Abgänge behandeln Verkäufe und bewertete Ausgaben einheitlich; Kartenzahlungen verschwinden nicht mehr aus der FIFO-Auswertung.
- Der neue **Ø-Einkauf-bis-dahin**-Vergleich wird serverseitig aus bereits lokal vorhandenen Käufen aggregiert. Das Frontend erhält nur den historischen Durchschnitt und den daraus abgeleiteten Ø-P/L; es werden dafür keine zusätzlichen Notizen, Provider-IDs oder Import-Fingerprints übertragen.
- Teilweise verbrauchte Lots behalten ihren exakten Rest; der nächste Abgang verwendet diesen Rest zuerst.
- Gleichzeitige Buchungen verwenden in FIFO **und** Metriken dieselbe Tie-Reihenfolge: Zugang vor Abgang.
- Einzelne Add/Edit/Delete/Bulk-Mutationen können keinen neuen/größeren Oversell mehr persistieren.
- Ein erneutes gleich hohes ATH setzt `Tage seit ATH` zurück.
- Ein Drawdown bis auf 0 wird als -100 % erkannt.
- Altersbuckets verwenden konsistent 365,2425 Tage/Jahr; die konfigurierbare 365-Tage-Haltezeit-Regel bleibt davon unabhängig.
- Die Abgangsgebührenquote umfasst Verkäufe **und** bewertete Ausgaben; absolute Durchschnittsfees wurden als ungeeignete Vergleichskennzahl entfernt.
- XIRR verweigert eine versteckte Umrechnung bei gemischten Fiat-Cashflows ohne FX-Daten.
- Neue/bearbeitete Buchungen mit echten Zukunftszeitpunkten (>5 Minuten Clock-Skew) werden abgewiesen.

## Berechnungen, die explizit gegengeprüft wurden

- depotweises FIFO, mehrere Lots, Teil-Lot-Rest, nachfolgender Abgang;
- Kaufkostenbasis inklusive Kaufgebühr;
- proportionale Abgangsfee-Verteilung;
- Verkauf und `expense`/Kartenausgabe;
- Haltezeit-Regel und Altersverteilung;
- realisierter/unrealisierter/gesamter Gewinn;
- volumengewichtete Gebührenquoten;
- cashflow-neutraler HODL-Benchmark;
- randomisierte FIFO-Rechnung gegen eine unabhängige Queue-Referenz;
- optimierte historische Tages-Snapshots gegen vollständige FIFO-Neuberechnung;
- Drawdown-Randfälle sowie XIRR-Fiatgrenze.

Details: [`MATH-AUDIT.md`](MATH-AUDIT.md)

## Datenschutz- und Privatsphäre-Funde/Fixes

### CSV-Dublettenprüfung

Vor dem Audit musste das Frontend für die Dublettenprüfung das vollständige Ledger laden. Das war unnötig. In v0.21.0.6 findet der Abgleich vollständig in Home Assistant Core statt. Bestehende `import_ref_hash`-Werte bleiben Core-intern; das Frontend erhält nur ein Array aus `true/false`-Flags.

### Ledger-Payload

Ledger-Antworten werden über eine Feld-Allow-List reduziert. Interne Felder wie `import_ref_hash` und `fee_btc` werden nicht versehentlich an die Buchungsansicht weitergereicht. Chart-/Performance-Daten sind noch stärker reduziert und enthalten keine Notizen oder internen Identitäten.

### Browser-Caching und lokaler Speicher

Sensible Panel-Antworten sind `no-store`/private/same-origin/no-referrer gehärtet. `localStorage` enthält nur UI-/Sitzungspräferenzen und keine Passwörter, Ledgerzeilen, Notizen, Import-Hashes oder Transaktionsbeträge.

## Authentifizierung und RPC

Der HTTP-/Service-Layer verwendet die authentifizierte Home-Assistant-Identität. Weitergereichte/behauptete User-IDs werden nicht als Authentifizierungsquelle akzeptiert. Das Panel prüft `event.source`, exakte Origin und RPC-Kennung. Die CSP blockiert direkte Frontend-Netzwerkverbindungen (`connect-src 'none'`).

Das iframe bleibt Teil derselben vertrauenswürdigen HA-Origin; es ist keine separate opaque-origin Sicherheitsdomäne.

## Kryptografie

Geprüft wurde die aktuelle Konstruktion aus AES-256-GCM, Argon2id, HKDF-SHA-512, zufälligem DEK und separatem Geräteschlüssel. Portable Backups verwenden absichtlich eine separate passwortbasierte, geräteunabhängige Verschlüsselung. Passwörter werden nicht dauerhaft gespeichert.

Das Audit hat in diesen überprüften Kryptografiepfaden keine neue Berechnungs-/Datenflussinkonsistenz ergeben. Das ersetzt keine externe kryptografische Begutachtung.

## Netzwerkgrenze

Das Frontend besitzt keinen direkten öffentlichen Egress. Portfolio-/Ledgerdaten werden nicht an Kursanbieter gesendet. Öffentliche Daten laufen über das getrennte Tor Gateway; ausdrücklich konfigurierte lokale Node-Ziele dürfen direkt im LAN angesprochen werden.

## Performance mit Datenschutz

Die Performance-Optimierung erfolgt überwiegend durch Rechen-Caches, lineare FIFO-Verarbeitung, Binärsuche, serverseitige Aggregation und Lazy Loading. Sie benötigt keine zusätzliche externe Telemetrie. Große sensible Datensätze werden im Gegenteil später und zielgerichteter geladen.

## Verbleibende Schutzgrenzen

- kompromittierter HA-Host/Browser/Admin liegt außerhalb des Bedrohungsmodells;
- entsperrte, aktuell dargestellte Daten liegen im RAM des Browsers;
- keine externe Penetrationstest-Zertifizierung;
- keine Steuerberatung und keine Garantie für individuelle steuerliche Behandlung.

## Ergebnis

Das Audit hat reale Fehler gefunden. Diese wurden vor dem Release korrigiert und mit zusätzlichen Regressionstests abgesichert. Finale Testsuite: **351 Tests + 8 Subtests**, zusätzlich JavaScript-Numerik- und Syntaxprüfungen. v0.21.0.6 wird deshalb als gehärteter Audit-Release veröffentlicht.
