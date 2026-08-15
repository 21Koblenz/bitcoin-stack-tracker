# Bitcoin Stack Tracker · Market Assessment v4 – Backtestbericht

**Basis:** v0.21.0.9 Testbuild · Score-Version `price-history-adaptive-v4-turning-points`

## Ziel

Der bestehende adaptive 0–100-Markteinschätzungs-Score bleibt unverändert. v4 ergänzt vier getrennte, modulare Wendepunktmodelle:

- **Bottom Zone:** relative Unterbewertung / Stresszone.
- **Bottom Confirmation:** Hinweise, dass Verkaufsdruck und Abwärtsdynamik nachlassen.
- **Top Zone:** relative Überhitzung / Überdehnung.
- **Top Confirmation:** Hinweise, dass Aufwärtsdynamik nachlässt bzw. eine Preis-Rejection begonnen hat.

Die Werte sind **keine Kaufsignale, Verkaufssignale, Prognosen oder Wahrscheinlichkeiten**. Ein hoher Zonenwert erklärt keinen exakten Boden bzw. kein exaktes Top.

## Netzwerk / Tor

Die vier neuen Modelle verwenden ausschließlich die bereits lokal verfügbare BTC-Preishistorie. Sie erzeugen **keine neue ausgehende Netzwerkverbindung**. Der bestehende öffentliche Live-/Historienpfad bleibt fail-closed: öffentliche Ziele werden nur über den integrierten SOCKS5/Tor-Pfad mit Remote-DNS angefragt; bei fehlendem Tor gibt es keinen Clearnet-Fallback. Lokale, ausdrücklich konfigurierte eigene Infrastruktur bleibt lokal-direkt.

## Default-Logik v4

- Wendepunkt-Lookback: **180 Tage**
- Mindestabstand für Divergenz-Swings: **14 Tage**
- Zonengedächtnis: **45 Tage**
- Divergenz-Preistoleranz: **8 %**
- schnelle/langsame Volatilität: **30 / 90 Tage**
- Bestätigungsgrenze: **40 / 100**
- Zonen-Schwelle: **75 / 100**
- Extremzonen-Schwelle: **85 / 100**
- alle Gewichte und Zeitfenster sind auf der Markteinschätzungs-Unterseite editierbar; `0` deaktiviert einzelne Signale.

## Kausaler historischer Gegencheck

Jeder ausgewertete Tag sieht ausschließlich Kurse bis zu diesem Tag. Für die Bewertung einer späteren Bestätigung werden die folgenden Tage jeweils einzeln neu berechnet; Zukunftswerte werden niemals in eine frühere Berechnung eingespeist.

| Typ | historischer Bereich | Tag | Hauptscore | Zone | Bestätigung am Tag | erste Bestätigung | Verzögerung |
|---|---|---:|---:|---:|---:|---:|---:|
| Boden | 2013 first-cycle crash low | 2013-07-05 | 69 | 61 | 0 | – | – Tage |
| Top | 2013 second blow-off top | 2013-12-04 | 10 | 88 | 37 | 54 | 3 Tage |
| Boden | 2014/15 bear-market low | 2015-01-14 | 100 | 97 | 16 | 69 | 7 Tage |
| Top | 2017 cycle top | 2017-12-17 | 5 | 90 | 45 | 45 | 0 Tage |
| Boden | 2018 bear-market low | 2018-12-15 | 96 | 92 | 47 | 47 | 0 Tage |
| Top | 2019 recovery local top | 2019-06-26 | 14 | 74 | 12 | 46 | 21 Tage |
| Boden | 2020 COVID crash | 2020-03-13 | 90 | 89 | 36 | 65 | 7 Tage |
| Top | 2021 first major top | 2021-04-14 | 12 | 77 | 25 | 41 | 3 Tage |
| Boden | 2021 summer low | 2021-07-20 | 74 | 67 | 15 | – | – Tage |
| Top | 2021 second major top | 2021-11-10 | 22 | 67 | 42 | 42 | 0 Tage |
| Boden | 2022 deleveraging low | 2022-06-18 | 98 | 91 | 16 | 51 | 3 Tage |
| Boden | 2022 FTX-region low | 2022-11-21 | 93 | 89 | 25 | 42 | 7 Tage |
| Top | 2024 first ATH-region top | 2024-03-14 | 7 | 90 | 65 | 65 | 0 Tage |
| Boden | 2024 correction low | 2024-08-05 | 65 | 63 | 0 | – | – Tage |
| Top | 2025 ATH-region top | 2025-10-06 | 19 | 76 | 12 | 48 | 7 Tage |
| Boden | 2026 bear-market stress low | 2026-02-05 | 92 | 89 | 15 | 57 | 3 Tage |

### Interpretation

- Die großen **Cycle-/Bear-Böden 2015, 2018, 2020, Juni 2022, November 2022 und Februar 2026** erreichen eine hohe Bottom Zone; die Bestätigung folgt typischerweise am selben Tag oder innerhalb weniger Tage.
- **Sommer 2021 und August 2024** werden bewusst nicht als große Bottom-Formation bestätigt. Das waren starke Korrekturen, aber keine vergleichbare langfristige Extrem-Unterbewertung.
- Die geprüften großen Topbereiche **2013, 2017, 2019, April/November 2021, März 2024 und Oktober 2025** erhalten eine Top-Zone bzw. ein gespeichertes Top-Zonenregime und anschließend eine Bestätigung.
- **2017 Juni** ist ein wichtiges Kontrollbeispiel: sehr hohe Top Zone, aber Bestätigung unter der Schwelle. Das Modell sagt damit „überhitzt“, nicht „Top bestätigt“.

## Kontrollpunkte außerhalb der ausgewählten Extremereignisse

| Datum | Hauptscore | Bottom Zone | Bottom Conf. | Top Zone | Top Conf. | Phase |
|---|---:|---:|---:|---:|---:|---|
| 2012-06-01 | 51 | 53 | 15 | 55 | 2 | Neutral |
| 2013-09-01 | 33 | 37 | 25 | 71 | 4 | Neutral |
| 2014-06-01 | 52 | 52 | 32 | 57 | 7 | Neutral |
| 2015-08-01 | 60 | 66 | 16 | 46 | 25 | Neutral |
| 2016-06-01 | 24 | 40 | 25 | 73 | 13 | Expansion |
| 2017-06-01 | 6 | 14 | 10 | 91 | 36 | Überhitzung |
| 2018-06-01 | 69 | 61 | 15 | 32 | 33 | Neutral |
| 2019-04-01 | 69 | 61 | 23 | 43 | 1 | gedrücktes Regime |
| 2020-11-01 | 29 | 33 | 26 | 71 | 23 | Neutral |
| 2021-08-15 | 34 | 34 | 29 | 72 | 17 | Neutral |
| 2022-03-01 | 50 | 56 | 25 | 58 | 1 | Neutral |
| 2023-06-01 | 51 | 43 | 7 | 43 | 24 | Neutral |
| 2024-11-22 | 12 | 19 | 23 | 84 | 25 | Expansion |
| 2025-05-22 | 15 | 11 | 16 | 80 | 17 | Expansion |
| 2026-04-01 | 79 | 70 | 27 | 33 | 31 | Kapitulation / Extremzone |

## Grenzen des Backtests

- Der Rechenweg ist **look-ahead-frei**, aber die historische Auswahl ist kein vollständig unabhängiger, unbekannter Datensatz. Bitcoin besitzt nur wenige abgeschlossene Marktzyklen und einige historische Phasen wurden bereits während der Modellentwicklung betrachtet.
- Daher darf der Test nicht als statistischer Beweis verstanden werden. Er dient als robuste Regression und Plausibilitätsprüfung.
- Ein hoher Bottom-/Top-Zonenwert kann lange bestehen. Erst die getrennte Confirmation soll eine mögliche nachlassende Bewegung anzeigen.
- Auch eine bestätigte Boden-/Topbildung kann später scheitern oder erneut getestet werden.

## Regression

Nach Integration von v4:

- **398 Pytest-Tests bestanden**
- **8 Subtests bestanden**
- **0 Fehler**
- JavaScript Performance/Math-Test: **OK**
- Hauptscore-Testvektor aus Adaptive v2/v3 bleibt unverändert: `9, 9, 10, 25, 55, 72, 89, 96, 96, 96`.

## Fazit

v4 verbessert die Wendepunktanalyse vor allem dadurch, dass **Bewertungszone und Richtungsbestätigung getrennt** werden. Das 45-Tage-Zonengedächtnis verhindert, dass eine extreme Zone sofort verschwindet, sobald der Kurs bereits zu drehen beginnt. Die bestehende adaptive Vola-/Regimebewertung bleibt die Basis und wird nicht durch absolute BTC-Preisgrenzen ersetzt.


## Automatic refresh v3

The market assessment is recalculated automatically in the open dashboard every 60 seconds from cached public history and the latest coordinator live price. The UI refresh does not initiate additional external price requests. The live-price coordinator remains responsible for its configured refresh interval (default 300 seconds).

## Historical score price overlay

- Historical market-assessment points already carry the causal BTC price for the same day.
- The UI can overlay that BTC price on a dedicated right-hand axis while the score remains fixed at 0-100 on the left.
- The price overlay can be disabled and its axis switched between linear and logarithmic scaling.
- Crosshair readout shows date at the bottom, score on the left, and BTC price on the right.
- No additional external source is introduced by the overlay.

## Startseiten-Overlay und Deckkraft

- Der historische Markteinschätzungs-Chart wurde vertikal vergrößert.
- Das BTC-Preis-Overlay besitzt eine eigene einstellbare Deckkraft (0–100 %, Standard 55 %).
- Der Startseiten-Chart bietet die Ansicht `Kurs + Markteinschätzung`.
- Bitcoin-Kurs bleibt auf der linken Achse; die Markteinschätzung nutzt rechts fest 0–100 und immer linear.
- Die historische Score-Serie wird nur geladen, wenn die neue Startseitenansicht aktiv ist.
- Historische Score-Werte werden kausal auf die angezeigte Preis-Zeitachse fortgeschrieben; es wird kein zukünftiger Score in frühere Zeitpunkte interpoliert.
- Markteinschätzung bleibt als öffentliche Marktdaten auch im Diskretmodus numerisch sichtbar.

Regression: 455 Tests + 8 Subtests bestanden.
