# Changelog

## v0.21.0.10 — 2026-08-16: Sats Sentinel, adaptive market assessment & chart overlays

### English

This release builds on **v0.21.0.9** and adds Sats Sentinel, the adaptive/historical market assessment, improved live/chart refresh behavior, and the related privacy/UI hardening.

#### Sats Sentinel
- Added **Sats Sentinel**, a privacy-first watch-only Bitcoin monitor for single/multiple addresses, XPUB/YPUB/ZPUB and descriptors. It never accepts private keys or seed words and cannot sign or spend.
- Added configurable query source: **Automatic**, **Fulcrum/Electrum**, **electrs/Electrum**, **own Mempool instance**, or a **configured public Mempool source over Tor**.
- Explicit own-source selection is strictly **fail closed**. A failed Fulcrum/electrs/Mempool endpoint produces offline/partial status and never silently falls back to another provider.
- Local/private Electrum or Mempool endpoints may be queried directly over LAN; `.onion` and public endpoints are routed through the bundled Tor SOCKS path with remote DNS and no clearnet fallback.
- Fulcrum/electrs support direct Electrum scripthash balance/history/UTXO calls. TLS supports normal CA validation and exact SHA-256 certificate pinning for self-signed Fulcrum certificates.
- Added encrypted device-bound runtime state that contains only concrete derived addresses/scripts, not XPUB/descriptor secrets.
- Added movement journal with sender → direction → recipient flow, categories, notes, per-watch thresholds, direction/channel filters, counterparties, paging and configured Mempool explorer links for addresses/TXIDs.
- Added Home Assistant events, persistent notifications, multiple `notify.*` services, self-hosted ntfy targets and webhooks with discreet/normal/detailed payload levels.
- Added notification test, simulated inbound/outbound test and live arbitrary-TXID source test without mutating wallet balances or baselines.
- Status refresh no longer redraws the configuration form and therefore no longer overwrites unsaved input. Save/source-test actions provide explicit visible success/failure feedback.
- Removing a watch entry now also permanently deletes all journal rows for that monitor from the encrypted Sentinel cache, including derived-address activity for XPUB/descriptor monitors.

#### Adaptive market assessment
- Added a modular **0–100 market assessment** based only on public historical Bitcoin price data. It is explicitly an additional assessment, not a buy signal, bottom/top declaration, forecast, probability or investment recommendation.
- Added adaptive volatility/reference windows, long-term valuation, drawdown, historical price position, deviation, momentum/RSI, cycle models, Mayer Multiple, ATH drawdown, 200-day distance, power-law ratio and configurable weights/thresholds.
- Added independent bottom/top zone and confirmation diagnostics with configurable turning-point weights and memory/separation parameters.
- Added a standard Home Assistant market-assessment sensor with raw decimal score precision.
- Added causal historical score reconstruction: each historical point uses only information available at that date, preventing look-ahead bias.
- Added a dedicated historical score chart with fixed 0–100 axis, crosshair, date/score axis badges, optional BTC-price overlay, independent right-side price axis, linear/log price scaling and adjustable BTC-overlay opacity.
- Added configurable **causal EMA display smoothing**: Off / 3 / 5 / 7 / 14 / 30 points. Smoothing changes only the drawn line, never the raw score or Home Assistant sensor. A display-default reset restores EMA 5, 3-year range, BTC overlay on, 55% opacity and logarithmic price axis.
- Added **Bitcoin price + market assessment** to the overview chart. It uses the same smoothing setting as the dedicated market chart; its independent score axis stays linear but auto-scales to the visible score range so small changes remain readable.
- Fixed the overview market overlay appearing as a horizontal line: historical scores are no longer forward-filled into every intraday BTC candle. Causal score samples are aligned to the price timeline and connected directly; completed historical daily scores become effective at day end and the current live score at its actual calculation time.

#### Live price, history and chart refresh
- Improved the price coordinator with source-specific refresh cadence and a public-market fast lane while keeping public traffic Tor-only.
- The current live price replaces/appends today's chart point so the visible chart can update before the next daily history write.
- Chart range changes now perform the appropriate real source refresh: exact intraday candles for short ranges and incremental daily-history synchronization for long ranges.
- Same-node Mempool address compatibility tries the configured `/api/address/...` path and, only on 404, the same node's `/api/v1/address/...` path. No host/provider fallback is introduced.
- Sats Sentinel no longer depends on `/utxo`; Mempool balance and UTXO counts are derived from address chain/mempool statistics while transaction history remains on the same configured source.

#### Privacy and source policy
- Sentinel source policy is deliberately separate from price-source failover. Portfolio price data may use configured source aggregation/failover; wallet monitoring never leaves an explicitly selected own source.
- Public/onion Sentinel requests use Tor with remote DNS; ordinary public non-onion targets require HTTPS/TLS.
- Market-assessment data is public market data and remains visible independently of portfolio privacy/discreet mode.
- Explorer links are separated from the Sentinel blockchain source, allowing Fulcrum/electrs monitoring while still opening TXIDs/addresses in a local Mempool web UI.

#### Quality assurance
- Final local release suite: **457 tests + 8 subtests passed**.
- Python compile, JavaScript syntax, frontend asset integrity, source-policy regressions, TLS pinning, journal purge, causal-history/no-look-ahead and chart-overlay tests pass.
- Home Assistant custom integration version: **v0.21.0.10**.
- Tor Gateway remains **v0.21.0.3**.

### Deutsch

Dieses Release baut auf **v0.21.0.9** auf und ergänzt Sats Sentinel, die adaptive/historische Markteinschätzung, verbesserte Live-/Chart-Aktualisierung sowie die dazugehörige Privacy- und UI-Härtung.

#### Sats Sentinel
- Neuer **Sats Sentinel** als Privacy-first Watch-only-Bitcoin-Wächter für einzelne/mehrere Adressen, XPUB/YPUB/ZPUB und Descriptoren. Private Keys oder Seed-Wörter werden nicht akzeptiert; Signieren oder Ausgeben ist nicht möglich.
- Einstellbare Abfragequelle: **Automatisch**, **Fulcrum/Electrum**, **electrs/Electrum**, **eigene Mempool-Instanz** oder eine **konfigurierte öffentliche Mempool-Quelle über Tor**.
- Eine explizit ausgewählte eigene Quelle arbeitet strikt **Fail Closed**. Fällt Fulcrum/electrs/Mempool aus, meldet Sentinel offline/teilweise und wechselt niemals heimlich zu einem anderen Provider.
- Lokale/private Electrum- oder Mempool-Ziele dürfen direkt im LAN angesprochen werden; `.onion`- und öffentliche Ziele laufen über den integrierten Tor-SOCKS-Pfad mit Remote-DNS und ohne Clearnet-Fallback.
- Fulcrum/electrs werden direkt über Electrum-Scripthash-Abfragen für Balance/History/UTXOs genutzt. TLS unterstützt normale CA-Prüfung und exaktes SHA-256-Zertifikat-Pinning für selbstsignierte Fulcrum-Zertifikate.
- Neuer verschlüsselter gerätegebundener Runtime-Zustand mit konkreten abgeleiteten Adressen/Scripts, aber ohne XPUB-/Descriptor-Geheimnisse.
- Neues Bewegungsjournal mit Sender → Richtung → Empfänger, Kategorien, Notizen, Schwellen pro Watch-Eintrag, Richtungs-/Kanalfiltern, Gegenadressen, Pagination und konfigurierten Mempool-Explorer-Links für Adressen/TXIDs.
- Home-Assistant-Events, Persistent Notifications, mehrere `notify.*`-Dienste, self-hosted ntfy-Ziele und Webhooks mit diskreter/normaler/detaillierter Darstellung.
- Benachrichtigungstest, simulierte Ein-/Ausgangstests und Live-TXID-Quellentest ohne Veränderung von Wallet-Balance oder Baseline.
- Der Statusrefresh rendert das Konfigurationsformular nicht mehr neu und überschreibt damit keine ungespeicherten Eingaben. Speichern und Quellen-Test zeigen sichtbares Erfolgs-/Fehlerfeedback.
- Beim Entfernen eines Watch-Eintrags werden jetzt auch alle zugehörigen Journal-Zeilen dauerhaft aus dem verschlüsselten Sentinel-Cache gelöscht, einschließlich abgeleiteter XPUB-/Descriptor-Adressen.

#### Adaptive Markteinschätzung
- Neuer modularer **0–100-Markteinschätzungs-Score** ausschließlich aus öffentlichen historischen Bitcoin-Kursdaten. Er ist ausdrücklich eine zusätzliche Einschätzung und kein Kaufsignal, keine Boden-/Top-Erklärung, Prognose, Wahrscheinlichkeit oder Anlageempfehlung.
- Adaptive Volatilitäts-/Referenzfenster, langfristige Bewertung, Drawdown, historische Preisposition, Abweichung, Momentum/RSI, Zyklusmodelle, Mayer Multiple, ATH-Drawdown, 200-Tage-Abstand, Power-Law-Verhältnis sowie einstellbare Gewichte/Schwellen.
- Unabhängige Boden-/Top-Zonen und Bestätigungsdiagnostik mit einstellbaren Wendepunktgewichten sowie Gedächtnis-/Abstandsparametern.
- Standard-Home-Assistant-Sensor für die Markteinschätzung mit dezimalem Rohscore.
- Kausale Rekonstruktion der Score-Historie: Jeder historische Punkt verwendet ausschließlich Informationen, die an diesem Datum bereits vorhanden waren; dadurch kein Look-ahead-Bias.
- Eigener historischer Score-Chart mit fester 0–100-Achse, Fadenkreuz, Datum-/Score-Achsenbadges, optionalem BTC-Preis-Overlay, eigener rechter Preisachse, linear/logarithmischer Preisskalierung und einstellbarer BTC-Overlay-Deckkraft.
- Einstellbare **kausale EMA-Anzeigeglättung**: Aus / 3 / 5 / 7 / 14 / 30 Punkte. Die Glättung verändert nur die gezeichnete Linie, niemals Rohscore oder HA-Sensor. „Standard wiederherstellen“ setzt EMA 5, 3 Jahre, BTC-Overlay an, 55 % Deckkraft und logarithmische Preisachse zurück.
- Neue Startseiten-Ansicht **Bitcoin-Kurs + Markteinschätzung**. Sie übernimmt dieselbe Glättung wie der Marktchart; die unabhängige Scoreachse bleibt linear, skaliert auf der Startseite aber automatisch auf den sichtbaren Scorebereich, damit auch kleine Veränderungen erkennbar bleiben.
- Fehler behoben, bei dem die Markteinschätzung auf der Startseite als Seitwärtslinie erscheinen konnte: historische Scores werden nicht mehr in jedes Intraday-Kursintervall vorwärts aufgefüllt. Die kausalen Score-Stützpunkte werden direkt auf die Kurszeitachse gelegt und verbunden; abgeschlossene Tagesscores gelten am Tagesende und der Live-Score erst ab seinem tatsächlichen Berechnungszeitpunkt.

#### Live-Kurs, Historie und Chart-Refresh
- Price Coordinator mit quellenabhängiger Aktualisierungsfrequenz und Public-Market-Fast-Lane erweitert; öffentliche Verbindungen bleiben Tor-only.
- Der aktuelle Live-Kurs ersetzt/ergänzt den heutigen Chartpunkt, damit der sichtbare Chart nicht auf den nächsten Tages-History-Write warten muss.
- Zeitraumwechsel führen jetzt den passenden echten Quellenrefresh aus: exakte Intraday-Kerzen für kurze Bereiche und inkrementelle Tageshistorien-Synchronisierung für lange Bereiche.
- Mempool-Adresskompatibilität bleibt auf derselben Node: zuerst `/api/address/...`, ausschließlich bei 404 `/api/v1/address/...`; kein Host-/Provider-Fallback.
- Sats Sentinel benötigt keinen `/utxo`-Endpunkt mehr; Balance und UTXO-Anzahl werden bei Mempool aus Chain-/Mempool-Statistiken abgeleitet, die Transaktionshistorie bleibt auf derselben konfigurierten Quelle.

#### Privacy und Quellenregeln
- Sentinel-Quellenregeln bleiben bewusst von Preisquellen-Failover getrennt. Portfolio-Preisdaten dürfen konfigurierte Aggregation/Fallbacks verwenden; Wallet-Überwachung verlässt eine explizit gewählte eigene Quelle niemals.
- Öffentliche/Onion-Sentinel-Abfragen laufen über Tor mit Remote-DNS; normale öffentliche Non-Onion-Ziele benötigen HTTPS/TLS.
- Markteinschätzung ist öffentliche Marktdatenanalyse und bleibt unabhängig vom Portfolio-Diskretmodus sichtbar.
- Explorer-Links sind von der Sentinel-Blockchainquelle getrennt: Überwachung kann über Fulcrum/electrs laufen, während TXIDs/Adressen weiterhin in einer lokalen Mempool-Weboberfläche geöffnet werden.

#### Qualitätssicherung
- Finale lokale Release-Suite: **457 Tests + 8 Subtests bestanden**.
- Python-Compile, JavaScript-Syntax, Frontend-Asset-Integrität, Quellenregeln, TLS-Pinning, Journal-Löschung, kausale Historie/No-Look-Ahead und Chart-Overlay-Regressionen sind grün.
- Home-Assistant-Custom-Integration: **v0.21.0.10**.
- Tor Gateway bleibt **v0.21.0.3**.

## v0.21.0.9 — Initial published build (2026-08-14): Revolut X, manuelle Buchungen & Netzwerkgebühren

### Revolut X CSV
- Neuer eigener Parser für `Symbol`, `Type`, `Quantity`, `Price`, `Value`, `Fees`, `Date`.
- `BTC`/`XBT` wird übernommen; andere Assets werden übersprungen.
- `Buy` wird Kauf, `Sell` wird Verkauf; `Quantity` ist BTC und `Fees` eine separate Fiatgebühr.
- `Value` bleibt der Brutto-Handelswert vor Gebühren: Kauf-Gesamtbetrag = `Value + Fees`, Verkaufs-Nettoerlös = `Value - Fees`.
- Unterstützt u. a. `21 Jan 2026, 21:21:21` sowie Monat-zuerst mit AM/PM; fehlt `Price`, wird er aus `Value / Quantity` rekonstruiert.

### Manuelle Buchungen & FIFO
- Neue Buchungsart **Einnahme**: bewerteter BTC-Zugang mit FIFO-Einstand wie bei einem Kauf, aber separat ausgewiesen.
- **Ausgabe** ist nun auch manuell auswählbar und realisiert Gewinn/Verlust über dieselbe depotweise FIFO-Logik wie ein Verkauf, bleibt aber semantisch getrennt.
- Die Buchungsart kann beim Bearbeiten geändert werden. Danach wird die vollständige FIFO-Kette atomar neu validiert; ein neu erzeugter/größerer Oversell wird weiterhin verhindert.
- Übersicht ergänzt um getrennte Summen für Verkäufe, Ausgaben, Einnahmen und Transaktionsgebühren sowie den gesamten realisierten Gewinn/Verlust.
- **„Fiat in Sicherheit gebracht“** wurde in **„Kaufkraft in Sicherheit gebracht“** umbenannt; Einnahmen zählen dort bewusst nicht als Fiat-Kauf.

### On-Chain- und Lightning-Transaktionsgebühren
- Neue eigenständige Buchungsart **Transaktionsgebühr** mit Netzwerk `On-Chain` oder `Lightning` und Betrag in BTC/Sats.
- Die Gebühr mindert den tatsächlichen Stack und verbraucht die entsprechenden FIFO-Lots, ohne einen fiktiven Verkaufserlös zu erzeugen.
- Der historische BTC-Kurs am Buchungszeitpunkt dient zur Anzeige des Fiat-Gegenwerts der Gebühr.
- Bestehende importierte `fee_btc`-Werte reduzieren den Stack nur zusätzlich, wenn sie ausdrücklich als stack-wirksam markiert sind; dadurch werden Legacy-/Nettoimporte nicht doppelt belastet.
- Gebührenanalyse: Gesamte Gebühren enthalten explizite Fiatgebühren plus Fiat-Gegenwerte erfasster BTC-/Sats-Gebühren; reine Netzwerkgebühren verzerren keine Handelsvolumenquote.

### Historische Plausibilitätsprüfung
- Manuelle Käufe, Einnahmen, Verkäufe und Ausgaben werden nicht blockierend mit dem historischen BTC-Kurs des Buchungszeitpunkts verglichen.
- Ab **10 %** Abweichung erscheint eine Warnung mit eingegebenem Kurs, Referenzkurs und prozentualer Abweichung.
- Für alte Buchungen wird niemals der heutige Live-Kurs als Ersatz benutzt. Ist kein historischer Referenzkurs vorhanden, wird die Prüfung nur übersprungen.

### Performance & Zeiträume
- Neue Reihenfolge: **1 Tag · seit Wochenbeginn · 1 Woche · seit Monatsbeginn · 30 Tage · 90 Tage · YTD · 1 Jahr · 3 Jahre · 5 Jahre · 10 Jahre · seit erstem Kauf · Max**.
- `seit Wochenbeginn` startet Montag 00:00; `1 Woche` ist rollierend sieben Tage; `seit Monatsbeginn` startet am Monatsersten 00:00.
- XIRR bleibt die geldgewichtete persönliche Rendite des **gewählten Zeitraums**, auf ein Jahr hochgerechnet.
- TWR bleibt cashflow-neutral: zusätzliche Käufe/Einnahmen erhöhen die Rendite nicht künstlich; Transaktionsgebühren bleiben echte Performancekosten.
- CAGR wird klarer als durchschnittliche annualisierte Entwicklung des Bitcoin-Marktpreises beschrieben und von persönlicher XIRR/TWR abgegrenzt.

### Kompatibilität & Tests
- Home-Assistant-Integration: **v0.21.0.9**.
- Tor Gateway: weiterhin **v0.21.0.3**.
- Neue gezielte Regressionstests für Revolut X, historische Referenzkurse, Einnahmen, Ausgaben/FIFO und Netzwerkgebühren.
- Finale lokale Testsuite: **373 Tests + 8 Subtests bestanden**; zusätzlich JavaScript-Syntax, Python-Compile, JSON/YAML und Versionskonsistenz geprüft.

## v0.21.0.8 — Peach Bitcoin CSV Import

### Peach Bitcoin
- Neuer eigener Peach-Bitcoin-CSV-Parser für die Spalten `Date`, `Trade ID`, `Type`, `Amount`, `Price`, `Bitcoin Price`, `Currency` und `Premium`.
- `Amount` wird bei Peach ausschließlich als Satoshi-Ganzzahl interpretiert; 100.000 sats werden exakt zu 0,001 BTC.
- `Price` bleibt der tatsächlich gezahlte bzw. erhaltene Fiat-Gesamtbetrag.
- `Premium` wird als Prozentwert behandelt. Bei Käufen wird der in `Bitcoin Price` enthaltene Aufschlag mit `Bitcoin Price / (1 + Premium/100)` entfernt; die Differenz zum gezahlten `Price` wird als Fiatgebühr ausgewiesen, ohne den FIFO-Einstand doppelt zu erhöhen.
- `Trade ID` dient als stabile Import-Identität; Roh-IDs werden weiterhin nicht ungefragt im Ledger gespeichert.
- Verkäufe werden unterstützt; bei Verkäufen bleibt der tatsächliche Fiat-Erlös maßgeblich und es wird kein positiver Premiumwert blind als zusätzliche Gebühr gebucht.

### Dokumentation
- README vollständig zweisprachig Deutsch/Englisch.
- Peach Bitcoin in der Importübersicht und in `CSV-IMPORT.md` dokumentiert.

### Tests und Release-Aufteilung
- Fünf gezielte Peach-Regressionstests: Sats-Umrechnung, Premium-/Gebührenrechnung, Trade-ID-Dubletten, fehlendes Premium und Verkauf.
- **Home-Assistant-Integration:** v0.21.0.8.
- **Tor Gateway:** bleibt v0.21.0.3.

## v0.21.0.7 — Bitpanda CSV & Fee Hotfix

### Bitpanda-Import
- Neuer eigener Bitpanda-Parser für Transaction Reports mit Erkennung über `Venue: Bitpanda`, `Reported by Bitpanda GmbH` und die charakteristische Header-Struktur.
- Der vorhandene BTC/XBT-Normalisierer bleibt die zentrale Bitcoin-only-Grenze. Käufe und Verkäufe anderer Assets sowie reine Fiat-Deposits werden ignoriert.
- `buy` wird als Kauf und `sell` als Verkauf verarbeitet; `In/Out` ist nur Zusatzinformation und bestimmt nicht die Buchungsart.
- `Transaction ID` wird als primäre stabile Import-Identität verwendet. Roh-IDs werden weiterhin nicht im Ledger gespeichert, sondern nur lokal gehasht.
- Physische CSV-Zeilennummern bleiben auch bei Bitpanda-Metadatenzeilen erhalten, damit Importfehler auf die tatsächliche Datei verweisen.

### Withdrawal- und Gebührenlogik
- BTC-`withdrawal` bleibt ein Transfer und erzeugt keinen FIFO-Verkauf.
- Eine explizite Bitpanda-Withdrawal-Fee in BTC wird dem seit dem vorherigen BTC-Withdrawal aufgebauten Kauf-Batch zugeordnet.
- Gemeinsame BTC-Fees werden proportional nach Brutto-BTC auf ganze Satoshis verteilt; der letzte Kauf erhält den exakten Rest, sodass die Summe exakt der exportierten BTC-Fee entspricht.
- Die Netzwerkfee reduziert den tatsächlichen Stack und bleibt als `fee_btc` erhalten; sie wird nicht künstlich in eine Fiat-Fee umgerechnet.
- Im Bitpanda-Ausführungspreis enthaltene Handelsgebühren/Prämien werden als separates `included_fee` gespeichert. Sie zählen in der Gebührenanalyse, verändern aber den FIFO-Einstand nicht ein zweites Mal.
- Liefert die CSV eine explizite Fiat-Handelsgebühr, wird diese als enthaltene Gebühr übernommen. Ist sie nur aus `Amount Fiat`, Brutto-BTC und Marktpreis ableitbar, wird die Differenz als geschätzt markiert. Ist sie aus dem CSV nicht rekonstruierbar, wird die 0,99-%-BTC-Prämie ausschließlich als editierbare Analytics-Schätzung verwendet.

### Importvorschau und Kontrolle
- Importvorschau und Speicherung unterstützen enthaltene Handelsgebühren einschließlich Schätzkennzeichen.
- Die Rechenkontrolle verwendet für Bitpanda den ursprünglichen Trade-BTC-Betrag vor einer späteren Withdrawal-Fee; hohe On-Chain-Gebühren erzeugen dadurch keine falsche Kaufabweichung.
- Fehlende Bitpanda-`Fee`-Werte (`-`) sind zulässig und machen eine ansonsten vollständige Kauf-/Verkaufszeile nicht ungültig.
- Export und Dashboard-Gebührenmetriken berücksichtigen `included_fee`, ohne die Kostenbasis doppelt zu belasten.

### HACS / Home Assistant
- Gemeinsamer `Validate`-Workflow mit HACS Action und Hassfest.
- `actions/checkout@v5`.
- Manifest mit `@21Koblenz` als `codeowners`, HACS/Hassfest-konformer Schlüsselreihenfolge und `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)`.
- **Tor Gateway bleibt v0.21.0.3**.

### Tests
- Bitpanda-Regressionen decken Buy/Sell, BTC/XBT-Filter, Altcoin-Ausschluss, Deposits, BTC-Withdrawals, mehrere Käufe pro Withdrawal-Batch, Satoshi-genaue Fee-Verteilung, physische Zeilennummern, ID-basierte Dubletten und enthaltene Handelsgebühren ab.
- Finale Testsuite: **354 Tests + 8 Subtests bestanden**; JavaScript-Syntaxprüfung, Python-Compile-Check, JSON-Parsing und Versionskonsistenz ebenfalls erfolgreich.

## v0.21.0.6 — Calculation, Privacy & Large-Ledger Performance Audit

### Berechnung und FIFO

- Verkäufe **und bewertete Ausgaben** werden vollständig als FIFO-Abgänge verarbeitet; Wavespace-/Kartenzahlungen erscheinen korrekt in der FIFO-Abgangsübersicht.
- FIFO-Abgänge zeigen zusätzlich **Ø Einkauf bis dahin** und einen separaten Ø-P/L-Vergleich. Pro Abgangszeile werden FIFO-Gewinn/FIFO-Rendite und Ø-Gewinn/Ø-Rendite als eigene Felder angezeigt; die Kopfübersicht enthält ebenfalls einen separaten historischen Durchschnittsblock mit Vergleichskaufkurs, Vergleichseinstand und absolutem/relativem Ergebnis. Grundlage ist der BTC-gewichtete effektive Einstand aller Käufe derselben Fiatwährung bis zum Abgangszeitpunkt inklusive Kaufgebühren; der Wert ist ausdrücklich kein FIFO-/Steuerwert und verändert die FIFO-Zuordnung nicht.
- Teilweise verbrauchte Kauf-Lots behalten ihren exakten Rest. Der nächste Verkauf oder die nächste Ausgabe verwendet zuerst den Rest des ältesten noch offenen Lots.
- Kostenbasis inklusive anteiliger Kaufgebühren und proportionale Abgangsgebühren wurden erneut mit unabhängigen und randomisierten Referenztests gegengeprüft.
- Mehrere Kauf-Lots innerhalb eines größeren Abgangs werden einzeln zum jeweiligen historischen Einstand ausgewertet; die Gesamt-Kostenbasis ergibt sich aus der Summe der tatsächlich verbrauchten Lot-Anteile.
- Gleichzeitige Buchungen verwenden konsistent dieselbe UTC-Tie-Reihenfolge: BTC-Zugang vor BTC-Abgang.
- Add/Edit/Delete/Bulk-Import validieren atomar und verhindern neuen oder größeren Oversell.
- Drawdown-Randfälle korrigiert: ein Tief bei 0 entspricht -100 %, ein erneutes gleich hohes ATH setzt `Tage seit ATH` zurück.
- XIRR verweigert gemischte Fiat-Cashflows ohne FX-Daten, statt eine nicht vorhandene Währungsumrechnung zu unterstellen.
- Altersbuckets verwenden 365,2425 Tage/Jahr; die konfigurierbare Haltezeit-Regel bleibt eine separate exakte Tagesregel.
- Neue oder bearbeitete Buchungen mit mehr als fünf Minuten Zukunftsabweichung werden abgewiesen.

### Kennzahlen und Charts

- BTC-CAGR seit erster bewerteter Buchung mit klarer Abgrenzung zu TWR und XIRR.
- Stacking-Geschwindigkeit für 30 Tage, 365 Tage und seit Beginn.
- Realisierter, unrealisierter und gesamter Gewinn/Verlust getrennt.
- Netto investiertes Fiat.
- Aktueller/maximaler Drawdown, Tage seit letztem Hoch und längste abgeschlossene Erholungsdauer.
- Haltezeit-Block mit über/unter Haltezeit-Regel, nächste 30/90 Tage, gewichtetem Stack-Alter, ältestem offenen Lot und Altersverteilung.
- Volumengewichtete Kauf- und Abgangsgebührenquote; Abgänge umfassen Verkauf und bewertete Ausgabe.
- BTC-/On-Chain-Gebühren werden nur dann als Sats ausgewiesen, wenn ein tatsächlicher BTC-Gebührenwert vorhanden oder exakt rekonstruierbar ist; unbekannte Altwerte werden nicht geraten.
- Cashflow-neutraler HODL-Benchmark mit denselben externen Ein- und Auszahlungen wie die tatsächliche Strategie.
- Linke und rechte Chart-Y-Achse können unabhängig Linear oder Logarithmisch dargestellt werden.

### Large-Ledger-Performance

- Behebt die `Zeitüberschreitung bei Home Assistant Core`-Probleme nach großen CSV-Imports bzw. beim anschließenden Öffnen und Navigieren im Tresor.
- `bulk_import` verwendet den bereits zur Oversell-Prüfung berechneten FIFO-Cache weiter, statt denselben kompletten FIFO-Lauf unmittelbar erneut auszuführen.
- FIFO nutzt pro Rechenlauf einen lokalen Lot-Cursor und scannt vollständig verbrauchte Lots nicht bei jedem späteren Abgang erneut. Jeder neue Rechenlauf startet trotzdem nach kompletter chronologischer Sortierung wieder vorne, sodass nachträglich eingefügte ältere Trades die FIFO-Zuordnung korrekt verändern können.
- Historische Tagesstände werden in einem chronologischen Durchlauf aufgebaut, statt für jeden Kurstag FIFO komplett neu zu berechnen.
- Historische Preiszuordnung verwendet vorbereitete Reihen und Binärsuche; TWR, XIRR, Chartserien und Performancewerte werden pro Dashboard-Snapshot wiederverwendet.
- XIRR normalisiert/sortiert Cashflows nur einmal pro Rechenlauf.
- Intraday-FIFO verwendet laufende Summen und lokale Lot-Zeiger.
- Schwere Overview-Berechnungen laufen erst nach dem sichtbaren Chart in einer Browser-Idle-Phase und werden beim Reiterwechsel verworfen.
- Dashboard-Sektionen werden lazy geladen; Einstellungen und Sicherheit benötigen kein vollständiges Ledger.
- Ledger-/FIFO-Indizes reduzieren wiederholte lineare Browser-Suchen.
- Das bestätigte CSV-Import-Timeout wurde zusätzlich auf 300 Sekunden erhöht; die eigentliche Lösung sind die Performance-Optimierungen.

### Datenschutz, Privatsphäre und Sicherheit

- CSV-Dublettenprüfung findet vollständig in Home Assistant Core statt; bestehende `import_ref_hash`-Werte werden nicht mehr in den Browser geladen.
- Der Core-Dubletten-Endpunkt liefert nur boolesche Dubletten-Flags und ist mengenbegrenzt/rate-limitiert.
- Dashboard, Chart, FIFO und Ledger verwenden minimierte Payloads bzw. Allow-Lists; Notizen, Provider-IDs und interne Import-/BTC-Fee-Metadaten werden nur dort übertragen, wo sie tatsächlich benötigt werden.
- Authentifizierte Panel-Antworten verwenden `Cache-Control: no-store, private`, `Pragma: no-cache`, same-origin/no-referrer-Härtung und `X-Content-Type-Options: nosniff`.
- Die restriktive CSP blockiert direkte Netzwerkverbindungen des Tracker-Frontends.
- Veraltete Lazy-Responses können keinen neueren Dashboard-Zustand überschreiben.
- Nicht-Owner erhalten weiterhin redigierte Verbindungsinformationen.
- Verschlüsselungsmodell (Argon2id, AES-256-GCM, HKDF-SHA-512/Envelope-Keying) wurde im Code-/Datenfluss-Audit erneut geprüft; der Audit ist kein externer Penetrationstest.

### CSV/FIFO-Oberfläche und Kompatibilität

- `FIFO SALES / Verkaufsübersicht` heißt jetzt **FIFO ABGÄNGE / FIFO-Abgänge**.
- Verkauf und Ausgabe werden als Art angezeigt; die Kopfzahl zählt echte Abgangsbuchungen statt einzelne Lot-Matches.
- ID-basierte Dublettenerkennung aus v0.21.0.4/v0.21.0.5 bleibt aktiv.
- Frontend Cache-Busting: `v021006-733b783d`.
- **Tor Gateway bleibt v0.21.0.3**; v0.21.0.6 betrifft ausschließlich die Custom Integration.

### Audit und Tests

- Neuer Berechnungs-, Datenschutz-, Privatsphäre- und Security-Code-Audit: [`AUDIT-v0.21.0.6.md`](AUDIT-v0.21.0.6.md).
- Berechnungsdetails: [`MATH-AUDIT.md`](MATH-AUDIT.md).
- Finale Testsuite: **351 Tests + 8 Subtests**; JavaScript-Numerik- und Syntaxprüfungen bestanden.

## v0.21.0.5 — Bulk-Import-Schema Hotfix

- Behebt den Fehler `extra keys not allowed @ data['transactions'][0]['import_ref_hash']` beim Bestätigen von CSV-Imports.
- `import_ref_hash` ist jetzt im tatsächlichen `bulk_import`-Transaktionsschema erlaubt.
- Die in v0.21.0.4 eingeführte ID-basierte Dubletten-Erkennung für Kraken und andere unterstützte CSV-Quellen kann dadurch serverseitig gespeichert und ausgewertet werden.
- Regressionstest ergänzt, damit Frontend-Payload und Home-Assistant-Service-Schema künftig nicht mehr auseinanderlaufen.
- Tor Gateway bleibt auf **v0.21.0.3**; dort ist keine Änderung nötig.

## v0.21.0.4 — CSV Duplicate Identity Hotfix

### Dublettenerkennung

- CSV-Buchungen mit identischem Zeitpunkt, BTC-Betrag, Kurs und Gebühr werden nicht mehr automatisch zusammengelegt, wenn die Quelle unterschiedliche Order-, Trade- oder Transaktions-IDs liefert.
- Kraken berücksichtigt `txid` und `ordertxid` gemeinsam. Mehrere gleich große Ausführungen derselben Order bleiben dadurch getrennte Buchungen, sobald sich mindestens eine Quell-ID unterscheidet.
- Die ID-basierte Erkennung gilt anbieterübergreifend für unterstützte CSV-Formate, soweit eine stabile Order-, Trade-, Transaktions- oder Referenz-ID vorhanden ist.
- Roh-IDs werden weiterhin nicht ungefragt im Ledger gespeichert. Für die Dublettenerkennung wird nur ein SHA-256-Hash aus Quelle und Quell-ID persistiert.
- Quellen ohne eindeutige ID verwenden weiterhin den bisherigen Werte-Fingerprint aus Typ, Zeitpunkt, Depot, BTC-Menge, Währung, Kurs und Gebühr.
- Für bereits vor diesem Hotfix importierte Buchungen ohne ID-Hash gibt es eine mengenbasierte Legacy-Abwärtskompatibilität: vorhandene identische Altbuchungen werden beim ersten erneuten Import einmalig angerechnet, weitere gleichwertige Zeilen mit unterschiedlichen IDs bleiben erhalten.

### Release-Aufteilung

- **Home-Assistant-Integration:** v0.21.0.4.
- **Tor Gateway:** bleibt v0.21.0.3, da dieser Hotfix keine Netzwerk-/Gateway-Änderung enthält. Dadurch erscheint für diesen Release kein unnötiges Tor-Gateway-Update.

### Tests

- Regressionstests für Kraken-Ausführungen mit identischen Handelswerten und unterschiedlichen `txid`/`ordertxid`.
- Regressionstest für Coinfinity-Buchungen mit identischen Werten und unterschiedlichen Order-IDs.
- Bestehende CSV-Parser-Regressionstests bleiben grün.

## v0.21.0.3 — CSV Import & Fee Accounting Hotfix

### Coinfinity

- `Amount Crypto` wird beim aktuellen Coinfinity-Report als BTC-Dezimalwert gelesen. Werte wie `0.00020000 BTC` ergeben exakt 20.000 sats; nachgestellte Nullen einer Sats-Ganzzahl werden nicht mehr abgeschnitten.
- `Mining Fee Crypto` wird als Satoshi-Betrag interpretiert. Leer oder 0 bedeutet Lightning; ein positiver Wert kennzeichnet eine On-Chain-Auszahlung.
- `Amount EUR` bleibt der tatsächlich überwiesene Gesamtbetrag. Service Fee und Mining Fee werden davon abgezogen und nicht ein zweites Mal auf den Zahlbetrag aufgeschlagen.
- Der tatsächlich erhaltene BTC-Betrag aus `Amount Crypto` bleibt unverändert. Für die Kostenbasis wird der effektive Kurs so normalisiert, dass BTC-Wert plus Gebühren exakt wieder `Amount EUR` ergibt.
- Order-ID, Adresse, Transaktions-ID und Lightning-Invoice bleiben optionale Vorschaufelder und landen nicht ungefragt in der Buchungsnotiz.

### Sats und Gebühren bei Verkäufen

- Die gemeinsame BTC/Sats-Anzeige entfernt keine nachgestellten Nullen mehr aus ganzzahligen Satoshi-Werten. Aus 20.000 sats kann dadurch nicht mehr fälschlich 2 sats werden.
- BTC→Sats wird für die Anzeige auf einen ganzzahligen Satoshi-Wert gerundet.
- Wird eine Verkaufsgebühr eindeutig in BTC/Sats ausgewiesen, zählt sie als zusätzlicher BTC-Abgang. Der Fiat-Gegenwert der Fee bleibt separat erhalten, sodass Stack, Nettoerlös und FIFO dieselbe tatsächlich abgegangene BTC-Menge verwenden.
- Diese eindeutige BTC-Fee-Behandlung gilt für die entsprechenden Verkaufspfade von Kraken Ledger, Binance Trade, CoinTracking/Pocket und Wavespace. Unklare generische Gebühren werden weiterhin nicht blind als zusätzlicher BTC-Abgang interpretiert.

### Wavespace

- BTC-Karten- und Verkaufsgebühren werden zusätzlich zur eigentlichen BTC-Menge vom Stack abgezogen. Beispiel: 100.000 sats Kartenumsatz + 371 sats Fee = 100.371 sats BTC-Abgang.
- `payWaveLowValuePurchase`, `POSPurchase`, `card purchase` und `card payment` werden als Buchungsart **Ausgabe** importiert.
- Bewertete Wavespace-Ausgaben verwenden für die Kontrollrechnung weiterhin die Verkaufslogik `BTC × Kurs − Fee = Fiat-Ausgabe`, bleiben im Buchungsbuch aber als **Ausgabe** gekennzeichnet.
- `ATMWithdrawal ... Card Authorization` bleibt eine Verkauf-/Bargeldabhebungsbuchung; ein normaler `CURRENCY_SWAP` BTC→Fiat bleibt ebenfalls **Verkauf**.
- Kartenhinweise können weiterhin aus einer zugeordneten `APPLICATION_FEE`-Zeile übernommen werden; Händlername, Kartenfee und optional aktivierbare Quelldaten bleiben erhalten.

### Export und Tests

- CSV-Export behandelt bewertete Ausgaben beim Fiat-Kontrollbetrag wie Verkäufe und zieht die gespeicherte Fee vom Bruttowert ab.
- Coinfinity-Regressionstests verwenden das reale aktuelle Schema mit BTC in `Amount Crypto` und Sats in `Mining Fee Crypto`.
- Regressionstests decken Sats mit nachgestellten Nullen, Lightning/On-Chain-Erkennung, BTC-Verkaufsfees sowie Wavespace-Kartenzahlungen als Ausgaben ab.

## v0.21.0.2 — Mathematical Audit Hotfix

### Charts und Performance

- TWR vollständig neu berechnet: externe Zu- und Abflüsse werden an ihrem tatsächlichen Buchungszeitpunkt getrennt und Teilperioden geometrisch verknüpft.
- Kauf- und Verkaufsgebühren wirken als Performancekosten; eine vollständige Auszahlung erzeugt nicht mehr fälschlich −100 % TWR.
- XIRR/XNPV auf die übliche 365-Tage-Konvention mit ganzen Zahlungstagen umgestellt; mehrdeutige IRR-Fälle werden erkannt statt willkürlich auf eine Lösung reduziert.
- XIRR-Suchraum für sehr kurze Zeiträume erweitert, damit stark annualisierte Tages-/Mehrtagesszenarien nicht unnötig als „nicht verfügbar“ enden.
- Maximaler Drawdown wird aus der vollständigen verfügbaren Analyse-Reihe berechnet und nicht mehr aus der für die Anzeige verdichteten Langzeitreihe.
- Langzeit-Downsampling behält den tatsächlichen Beobachtungstag eines Kurses bei; Werte werden nicht mehr künstlich ans Bucket-Ende verschoben.
- Tageskurse und tägliche FIFO-Snapshots werden einheitlich als Tagesendzustände behandelt.
- Intraday-Einstand, realisierter Gewinn und bekannte BTC werden nach jeder einzelnen Buchung neu ausgespielt statt nur mit dem finalen Tageszustand.

### FIFO, Gebühren und Zeitstempel

- FIFO-Sortierung verwendet echte UTC-Zeitpunkte statt lexikographischer ISO-Strings.
- Neue und bearbeitete Buchungen werden kanonisch als UTC-Zeitstempel gespeichert; Legacy-Migrationen sortieren ebenfalls nach dem realen Zeitpunkt.
- Historische Tages-Snapshots verwenden echte UTC-Zeitpunkte und einen neuen Chart-Cache-Schema-Stand, damit alte Cachewerte neu aufgebaut werden.
- Bei teilweise aufgelösten/überverkauften Verkäufen wird die Verkaufsgebühr proportional auch dem unaufgelösten Anteil des Nettoerlöses zugeordnet.
- FIFO-Verkaufsübersichten zählen BTC-Menge und Match-Anzahl nur innerhalb der angezeigten Fiatwährung.

### DCA, Gewinn/Verlust und Sensoren

- „Bester/Schlechtester Kauf“ verwendet den effektiven Einstand je BTC inklusive Kaufgebühren.
- Persönliche Sparjahre beginnen beim ersten passenden Kauf und rechnen Kalendergrenzen in UTC.
- Die missverständliche Prozentkennzahl „Gewinn / kumulierte Käufe“ wurde entfernt; kumulierte Kaufaufwendungen werden nur noch als klar bezeichnete Bezugsgröße angezeigt.
- Durchschnittlicher offener Kaufpreis und Buchgewinn-Prozent liefern ohne offenen bekannten Einstand „nicht verfügbar“ statt mathematisch falscher 0-Werte.
- Historische Durchschnittskaufpreise schreiben ohne bekannten offenen Bestand keinen künstlichen Nullwert mehr.

### Tests

- Numerische Golden-Tests für TWR, vollständige Auszahlung, Gebühren, XIRR-365-Tage, gleiche Zahlungstage, mehrdeutige XIRR-Wurzeln und Drawdown ergänzt.
- Regressionsprüfungen für UTC-FIFO, identische Zeitstempel, Tages-Snapshots, DCA, Multiwährung, Intraday-FIFO und Display-/Analyse-Trennung ergänzt.

## v0.21.0.1 — History Hotfix

- Historische BTC-Tagesdaten werden nicht mehr allein anhand eines frühen Startdatums als vollständig behandelt.
- Lücken werden über nachgelagerte Tor-Fallback-Quellen gefüllt; bereits vorhandene lokale Werte bleiben erhalten.
- Dichte-, Gap-, Start- und Endbereichsprüfungen verhindern unvollständige „Max“-Historien.
- Tor-Gateway-Workflow ist versionsunabhängig und nicht mehr auf v0.21.0.0 fest verdrahtet.

## v0.21.0.0 — Initial Public Release

### Portfolio, FIFO und Auswertungen

- Bitcoin-only Portfolio- und Stack-Tracking mit mehreren Depots.
- Käufe, Verkäufe, Gebühren, Notizen und depotweise FIFO-Zuordnung.
- Verkaufsübersicht mit FIFO-Einstand, Verkaufserlös, Gewinn/Verlust und Rendite.
- Bitcoin-Kurs-, Stack-, Portfoliowert- und Gewinn/Verlust-Charts mit mehreren Zeiträumen und Overlays.
- TWR-, XIRR-, DCA- und Drawdown-Auswertungen.
- Ziele, Milestones, Halving- und Bitcoin-Netzwerk-Markierungen.

### Import und Datenportabilität

- CSV-Import mit bearbeitbarer Vorschau und Plausibilitätsprüfung für unterstützte Börsen und Broker.
- Verschlüsselte portable `.bstbackup`-Backups für Käufe/Verkäufe, Depots, Ziele und Historie.
- Netzwerk-, Tor-, Zugriffs- und Verschlüsselungseinstellungen werden nicht aus portablen Backups wiederhergestellt.

### Home Assistant und mobile Nutzung

- Natives Home-Assistant-Seitenleistenpanel **Bitcoin Stack**.
- Zugriff über die authentifizierte Home-Assistant-Benutzeridentität.
- Desktop- und mobile Darstellung einschließlich Home-Assistant-Companion-App.
- Seitenwechsel in Buchungs- und Verkaufslisten springen an den Anfang der jeweiligen Liste.

### Tor und Fail Closed

- Eigenes Tor Gateway mit nftables-Default-Drop-Killswitch.
- Öffentliche Kurs- und Historienquellen ausschließlich über Tor.
- Lokale private Node-Ziele können direkt im privaten Netzwerk angesprochen werden.
- Automatische Supervisor-interne Erkennung des GitHub-installierten Tor Gateways und Kompatibilität mit lokalen Entwicklungsinstallationen.
- Kein öffentlicher DNS-/Clearnet-Fallback bei Fehlern der Gateway-Auflösung.

### Sicherheit

- Argon2id-basierte Passwortableitung und AES-256-GCM für den geschützten Tresor.
- Begrenzter Panel-/iframe-RPC-Kanal und restriktive Content Security Policy.
- Fail-closed Netzwerkpfad für öffentliche Datenquellen.
- Größenlimits, Zugriffskontrollen und gehärtete Backup-/Restore-Grenzen.
- Release-Metadaten, SBOM und reproduzierbare Integritätsprüfungen im Repository.

### Lizenz

- Öffentlicher Neustart unter **AGPL-3.0-only**.
