# Berechnungs-Audit · Bitcoin Stack Tracker v0.21.0.6

Stand: 11.08.2026. Das Audit prüft die mathematischen Kernpfade des Trackers mit deterministischen und randomisierten Regressionstests. Es ist keine Steuerberatung.

## FIFO und Abgänge

FIFO läuft **pro Depot** und sortiert nach dem realen UTC-Zeitpunkt. Bei identischem Zeitpunkt werden BTC-Zugänge (`purchase`, `stack`) vor BTC-Abgängen (`sale`, `expense`) verarbeitet; danach dient die stabile Entry-ID als Tie-Breaker.

Ein Abgang verbraucht das älteste noch offene Lot. Wird ein Lot nur teilweise verbraucht, bleibt exakt der Rest dieses Lots offen und wird beim nächsten Abgang zuerst verwendet. Kaufgebühren sind Bestandteil der Kostenbasis des jeweiligen Lots. Verkaufs-/Ausgabegebühren werden proportional auf die tatsächlich aus den Lots verwendeten BTC verteilt.

Bewertete `expense`-Buchungen, etwa Kartenzahlungen, bleiben im Ledger **Ausgaben**, werden mathematisch aber als FIFO-Abgänge mit Einstand, Netto-Gegenwert und realisiertem Ergebnis ausgewertet. Unbewertete Ausgaben verbrauchen Lots, ohne einen Fiat-Gegenwert oder Gewinn zu erfinden.

Zusätzlich wird je bewerteten Abgang ein **historischer Durchschnittsvergleich** berechnet. In der Oberfläche bleibt dieser Rechenweg sowohl pro FIFO-Abgangszeile als auch in der Gesamtübersicht sichtbar getrennt von FIFO: FIFO-Einstand/Gewinn/Rendite einerseits und historischer Ø-Vergleichseinstand/Gewinn/Rendite andererseits. Dafür werden alle `purchase`-Buchungen derselben Fiatwährung bis zum Abgangszeitpunkt BTC-gewichtet zusammengefasst. Der effektive Durchschnitt enthält die Kaufgebühren. Bereits zuvor verkaufte Käufe bleiben Teil des historischen Durchschnitts; `stack`-Einträge ohne Kaufpreis werden nicht einbezogen. Bei identischem Zeitstempel gilt dieselbe Reihenfolge wie FIFO: Zugänge vor Abgängen. Der daraus berechnete `Ø-P/L` verwendet den Netto-Gegenwert des jeweiligen FIFO-Anteils, ist aber **kein FIFO-, Steuer- oder offener Einstandswert**. Unterschiedliche Fiatwährungen werden nicht umgerechnet.

Neue, bearbeitete und per CSV importierte Buchungen dürfen keinen Oversell erzeugen oder einen bereits vorhandenen Legacy-Oversell vergrößern. Die Mutation wird erst nach erfolgreicher Kandidatenberechnung gespeichert.

## Haltezeit und Stack-Alter

Die **Haltezeit-Regel** ist eine frei einstellbare exakte Tageszahl, standardmäßig 365 Tage. Sie ist bewusst getrennt von der rein visuellen Altersverteilung.

Für die Altersanzeige verwendet der Tracker 365,2425 Tage pro Jahr. Ausgewiesen werden unter anderem: über/unter Haltezeit-Regel, in 30/90 Tagen zusätzlich über der Regel, BTC-gewichtetes Stack-Alter, ältestes offenes Lot und die Altersbuckets `<1`, `1–2`, `2–4`, `>4 Jahre`.

## Gewinn, Einstand und Gebühren

- **Realisierter Gewinn/Verlust:** Summe der bekannten FIFO-Ergebnisse abgeschlossener Verkäufe und bewerteter Ausgaben.
- **Unrealisierter Gewinn/Verlust:** aktueller Marktwert der offenen bekannten Lots minus deren offene Kostenbasis.
- **Gesamt:** realisiert + unrealisiert, sofern ein aktueller Preis vorliegt.
- **Netto investiertes Fiat:** Kaufaufwand inklusive Kaufgebühren minus Nettoerlöse aus Verkäufen. Kartenausgaben werden nicht fälschlich als an den Nutzer zurückgezahltes Fiat behandelt.

Gebührenquoten sind volumengewichtet. Die **Kaufgebührenquote** ist Kaufgebühren / Kaufvolumen. Die **Abgangsgebührenquote** umfasst Verkäufe und bewertete Ausgaben und ist Abgangsgebühren / Abgangsvolumen. Absolute Durchschnittsgebühren pro Trade werden nicht als Vergleichskennzahl verwendet. Eindeutig in BTC/Sats bekannte On-Chain-/Mining-/sonstige BTC-Gebühren werden separat als `BTC-Gebühren (gesamt)` aggregiert; unbekannte historische BTC-Gebühren werden nicht geraten.

## TWR, XIRR und BTC-CAGR

- **TWR:** zeitgewichtete Portfoliorendite; externe Cashflows werden aus der Strategieperformance herausgerechnet.
- **XIRR:** persönliche annualisierte Rendite auf Basis realer Cashflow-Zeitpunkte. Enthält der betrachtete Zeitraum bewertete Cashflows in mehreren Fiatwährungen, wird ohne vorhandene FX-Reihe **keine XIRR erfunden**.
- **BTC-CAGR:** annualisierte BTC-Marktpreisentwicklung seit der ersten bewerteten Buchung. Sie ist ausdrücklich keine persönliche Portfoliorendite und ergänzt TWR/XIRR.

## HODL-Benchmark

Der Benchmark ist cashflow-neutral: Beim Kauf investiert die Benchmark denselben externen Fiataufwand; bei Verkauf oder bewerteter Ausgabe entnimmt sie denselben Netto-Fiatgegenwert. Dadurch werden Strategie und HODL-Pfad mit denselben externen Cashflows verglichen. Bei gemischten Fiatwährungen ohne FX-Daten wird der Vergleich als unvollständig markiert statt stillschweigend umgerechnet.

## Drawdown

Drawdowns werden aus der cashflow-bereinigten Performance-Reihe abgeleitet. v0.21.0.6 korrigiert zwei Randfälle:

1. Ein erneutes Erreichen exakt desselben ATH setzt `Tage seit ATH` korrekt zurück.
2. Ein Rückgang von einem positiven Hoch auf exakt 0 wird als **-100 % Drawdown** erkannt; ein Null-Tief wird nicht mehr aus der Reihe herausgefiltert.

## Historische FIFO-Snapshots und Performance

Die optimierte Tages-Snapshot-Engine wurde gegen die vollständige `fifo_result`-Berechnung auf gemischten, randomisierten Kauf-/Verkauf-/Ausgabe-Ledgers verglichen. Offener Bestand, Kostenbasis, realisierte Ergebnisse, Haltezeitbestände und Gebühren stimmen bis auf vernachlässigbares Decimal-Rundungsrauschen weit unter Satoshi-/Cent-Präzision überein.

Zusätzlich wurde die optimierte FIFO-Implementierung gegen eine unabhängige Queue-Referenz auf einem randomisierten Ledger verglichen: Lot-Zuordnung, Teil-Lot-Reste, Kostenbasis, Nettoerlös und offener Restbestand stimmen überein.

## Zeitstempel

Ledger-Zeitstempel werden kanonisch auf UTC normalisiert. Die Rechenpfade verwenden echte Zeitpunkte statt lexikographischer ISO-Strings. Neue oder bearbeitete Ledgerbuchungen, die mehr als fünf Minuten in der Zukunft liegen, werden abgewiesen, weil zukünftige geplante Orders kein Ledgerkonzept des Trackers sind.

## Audit-Fazit

Die im erneuten Audit gefundenen Rechenfehler und Inkonsistenzen wurden vor v0.21.0.6 korrigiert und mit Regressionstests abgesichert. Das Audit bestätigt die getesteten Rechenregeln; es ist keine Garantie dafür, dass außerhalb des geprüften Codes niemals weitere Fehler existieren können.
