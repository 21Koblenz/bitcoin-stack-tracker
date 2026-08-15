# Bitcoin Stack Tracker – Adaptive Kaufchance v2 – historischer Gegencheck

Testmodell: `price-history-adaptive-v2` (0–100, höher = relativ günstig).

## Methodik

- Nur öffentliche tägliche BTC-Kurse; keine Portfolio-, FIFO- oder persönlichen Kaufdaten.
- Kein Look-ahead: Ein historischer Tag kennt ausschließlich Daten, die bis zu diesem Tag bereits vorlagen.
- Volatilitätsadaptiv: Trendabstände, Drawdowns und Momentum werden gegen die **bis zum Vortag bekannte** realisierte Volatilität normalisiert.
- Regimeadaptiv: Die normalisierten Signale werden gegen ihre eigene Verteilung der vorherigen bis zu 1.460 Tage (ca. 4 Jahre) eingeordnet.
- Alte absolute Preise werden nicht als zukünftige Schwellen verwendet.
- Externe Plausibilitätskontrolle: Coin-Metrics-MVRV ist nur im Backtest aufgeführt und **nicht Bestandteil des HA-Sensors**.

## Historische Phasen

| Datum | Phase | BTC USD | 365T Vola | 365T Drawdown | Mayer | Score | Bewertung | MVRV Kontrolle |
|---|---|---:|---:|---:|---:|---:|---|---:|
| 2017-12-17 | Bullmarkt 2017 – Topbereich | $19,250 | 89.1% | −2.0% | 3.64 | **5** | Sehr hoch bewertet | 4.25 |
| 2018-02-06 | 2018 – erster großer Abverkauf | $7,739 | 99.4% | −60.6% | 0.97 | **60** | Interessant | 1.48 |
| 2018-12-15 | Bärenmarkt 2018 – Bodenbereich | $3,185 | 85.5% | −83.8% | 0.51 | **96** | Extrem günstig | 0.69 |
| 2019-06-26 | 2019 – lokale Bullmarktspitze | $12,863 | 67.2% | −0.0% | 2.48 | **14** | Sehr hoch bewertet | 2.57 |
| 2019-12-18 | 2019 – späte Korrektur | $7,285 | 71.8% | −43.4% | 0.78 | **78** | Günstig | 1.30 |
| 2020-03-13 | Corona-Crash 2020 | $5,628 | 86.1% | −56.2% | 0.65 | **90** | Extrem günstig | 1.00 |
| 2020-12-31 | Bullmarkt 2020 – Jahresende | $29,023 | 78.3% | −0.0% | 2.17 | **12** | Sehr hoch bewertet | 3.14 |
| 2021-04-14 | Bullmarkt 2021 – erstes Top | $62,870 | 66.3% | −0.9% | 1.93 | **12** | Sehr hoch bewertet | 3.38 |
| 2021-07-20 | 2021 – Sommer-Crash | $29,767 | 75.1% | −53.1% | 0.67 | **74** | Günstig | 1.54 |
| 2021-11-10 | Bullmarkt 2021 – zweites Top | $64,756 | 78.8% | −4.1% | 1.42 | **22** | Hoch bewertet | 2.72 |
| 2022-06-18 | Bärenmarkt 2022 – Kapitulation | $19,014 | 69.6% | −71.8% | 0.48 | **98** | Extrem günstig | 0.84 |
| 2022-11-21 | Bärenmarkt 2022 – FTX-Nachlauf | $15,778 | 67.1% | −73.3% | 0.71 | **93** | Extrem günstig | 0.78 |
| 2023-01-01 | 2023 – früher Boden/Nachlauf | $16,607 | 64.4% | −65.0% | 0.84 | **81** | Sehr günstig | 0.84 |
| 2024-03-14 | 2024 – neues Hoch | $71,505 | 43.5% | −2.2% | 1.80 | **7** | Sehr hoch bewertet | 2.68 |
| 2024-08-05 | 2024 – starke Korrektur | $54,344 | 48.8% | −25.6% | 0.88 | **65** | Günstig | 1.73 |
| 2025-10-06 | Bullmarkt 2025 – ATH-Bereich | $124,824 | 43.7% | −0.0% | 1.18 | **19** | Sehr hoch bewertet | 2.29 |
| 2026-02-05 | Bärenmarkt 2026 – starker Ausverkauf | $63,495 | 44.1% | −49.1% | 0.62 | **92** | Extrem günstig | 1.15 |
| 2026-05-24 | Bärenmarkt 2026 – Erholung | $76,620 | 41.6% | −38.6% | 0.95 | **69** | Günstig | – |

## Kernaussage zur Markt-Reifung

- 06.02.2018: ca. −60,6 % Drawdown bei rund 99,5 % annualisierter 365-Tage-Volatilität → **60/100**.
- 05.08.2024: nur ca. −25,6 % Drawdown bei rund 48,8 % Volatilität → **65/100**.
- 05.02.2026: ca. −49,1 % Drawdown bei rund 44,1 % Volatilität → **92/100**.

Damit verlangt das Modell in einem späteren, ruhigeren Bitcoin-Markt keinen historischen −80-%-Crash mehr, um eine extreme Kaufchance zu erkennen.

## Kategorien

- 0–19: Sehr hoch bewertet
- 20–34: Hoch bewertet
- 35–49: Neutral
- 50–64: Interessant
- 65–79: Günstig
- 80–89: Sehr günstig
- 90–100: Extrem günstig

## Teststatus

- Projekttests: **384 bestanden + 8 Subtests, 0 Fehler**
- Zusätzliche Adaptive-Tests: gleiche prozentuale Korrektur wird im niedrigen Volatilitätsregime höher bewertet; Zukunftsdaten verändern historische Scores nicht; Diagnoseattribute sind vorhanden.

Datenbasis für den Backtest: Coin Metrics tägliche BTC-Referenzkurse. Der verwendete CSV-Snapshot reicht bis 24.05.2026.