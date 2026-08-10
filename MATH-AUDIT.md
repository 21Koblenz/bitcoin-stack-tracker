# Mathematical audit · v0.21.0.2

Dieses Dokument beschreibt die im Tracker verwendeten Rechenregeln. Es ist eine technische Dokumentation, keine Steuer- oder Anlageberatung.

## 1. Bitcoin und Sats

- `1 BTC = 100,000,000 sats`
- Ledger-Beträge werden intern mit `Decimal` verarbeitet.
- BTC wird auf 8 Nachkommastellen serialisiert.

## 2. FIFO und Einstand

Für jeden Kauf:

`Gesamteinstand = BTC × Kaufpreis + Kaufgebühr`

`Einstand je BTC = Gesamteinstand / BTC`

Verkäufe verbrauchen innerhalb jedes Depots zuerst das älteste noch offene Lot. Für einen FIFO-Match:

`anteilige Verkaufsgebühr = Verkaufsgebühr × Match-BTC / gesamte Verkaufs-BTC`

`Nettoerlös = Match-BTC × Verkaufspreis − anteilige Verkaufsgebühr`

`realisierter G/V = Nettoerlös − FIFO-Einstand`

Ein Fiat-Gewinn wird nur berechnet, wenn Kauf- und Verkaufs-Lot dieselbe Fiatwährung verwenden. Ohne FX-Kostenbasis bleibt der Match bewusst ungeklärt.

## 3. Unrealisierter und Gesamt-G/V

Nur offene Lots mit bekannter Kostenbasis gehen in den Buchgewinn ein:

`unrealisierter G/V = bekannte offene BTC × Marktpreis − offener Einstand`

`Gesamt-G/V = realisierter G/V + unrealisierter G/V`

BTC ohne bekannte Kostenbasis bleiben im Portfoliowert enthalten, erzeugen aber keinen erfundenen Buchgewinn.

## 4. DCA

`gewichteter Kaufkurs = Σ(BTC × Kaufpreis) / Σ(BTC)`

`Fiat-Aufwand inkl. Gebühren = Σ(BTC × Kaufpreis + Gebühr)`

`Ø sats pro Fiat = Σ(BTC) × 100,000,000 / Fiat-Aufwand inkl. Gebühren`

`Break-even-Kurs = Fiat-Aufwand inkl. Gebühren / Σ(BTC)`

`effektiver Einstand eines Kaufs = (BTC × Kaufpreis + Gebühr) / BTC`

Bester und schlechtester Kauf werden nach diesem effektiven Einstand bestimmt.

## 5. TWR

TWR entfernt externe Zu- und Abflüsse aus der Rendite. Der Zeitraum wird an jedem Cashflow in Teilperioden getrennt und die Teilperioden werden geometrisch verknüpft:

`TWR = Π(1 + r_i) − 1`

Käufe/Stack-Zugänge sind externe Zuflüsse, Verkäufe/Ausgaben externe Abflüsse. Transaktionsgebühren sind keine externen Cashflows und bleiben deshalb als Performancekosten sichtbar.

Für Einzahlungen wird der Cashflow vor der anschließenden Transaktion berücksichtigt. Für Auszahlungen wird die Transaktion vor dem externen Abfluss berücksichtigt. Dadurch führt eine vollständige Auszahlung nicht fälschlich zu −100 % Rendite.

## 6. XIRR / XNPV

XIRR löst den Zinssatz `r`, für den gilt:

`XNPV(r) = Σ(CF_i / (1 + r)^((d_i − d_0)/365)) = 0`

- 365-Tage-Konvention.
- Zahlungstage werden als ganze UTC-Kalendertage verarbeitet.
- Einzahlungen aus Sicht des Anlegers sind negativ, Auszahlungen positiv, der Endwert positiv.
- Bei mehreren mathematisch gültigen Wurzeln zeigt der Tracker die Kennzahl als mehrdeutig statt eine beliebige Wurzel auszugeben.

## 7. Cashflow-bereinigte absolute Veränderung

`absoluter G/V = Endwert − Startwert − Nettozuflüsse`

Dabei sind Zuflüsse positiv und Abflüsse negativ. Die Prozentangabe daneben ist TWR, kein pseudo-ROI auf kumulierte Käufe.

## 8. Drawdown

Für jeden Punkt der vollständigen verfügbaren Analyse-Reihe:

`Drawdown_t = Wert_t / bisheriges Hoch_t − 1`

Der maximale Drawdown ist der kleinste Wert dieser Reihe. Die visuelle Langzeit-Verdichtung wird erst für die Darstellung angewandt und beeinflusst die Kennzahl nicht.

## 9. Tages- und Intraday-Zustände

- Tageskurse und tägliche FIFO-Snapshots repräsentieren den Tagesendzustand in UTC.
- Intraday-Reihen verwenden die tatsächlichen Buchungszeitpunkte.
- Einstand, realisierter Gewinn und bekannte BTC werden intraday nach jeder Buchung neu berechnet.
- Langzeit-Displaypunkte behalten den tatsächlichen Beobachtungstag des ausgewählten Kurses.

## 10. Golden-Tests

Die Release-Tests enthalten unter anderem:

- TWR mit Cashflow mitten im Zeitraum: `+200 %` statt der früher möglichen `+250 %`.
- kompletter Verkauf bei unverändertem Marktpreis und 1 % Verkaufsgebühr: `−1 %` statt `−100 %`.
- XIRR mit 365-Tage-Basis über ein Schaltjahr.
- XIRR-Cashflows am selben Kalendertag ohne künstliche Intraday-Abzinsung.
- klassischer Cashflow mit zwei IRR-Wurzeln: Ergebnis wird als mehrdeutig erkannt.
- maximaler Drawdown aus `110 → 70`: `−36.3636… %`.
- mehrere TWR-Cashflows mit exakt identischem Zeitstempel bleiben getrennte Zustände.
- FIFO-Reihenfolge mit gemischten ISO-Zeitzonen und deterministischer Tie-Break-Reihenfolge.
