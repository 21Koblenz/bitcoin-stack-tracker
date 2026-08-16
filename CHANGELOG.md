# Changelog

## v0.21.0.12 — 2026-08-16: Sats Sentinel HD-wallet reliability, persistence & non-blocking scans

### English

This maintenance release builds on **v0.21.0.11** and hardens Sats Sentinel for real XPUB/YPUB/ZPUB and descriptor wallets: correct independent gap-limit discovery, restart persistence, non-blocking saves, consistent balances and complete active-address transaction coverage.

#### XPUB/descriptor gap discovery
- `receive_count` is a true **Receive gap limit**, not a cap on total monitored receive addresses. Sentinel keeps all used receive addresses and stops only after the configured number of consecutive unused addresses after the used range.
- `change_count` follows the **same independent gap-limit logic** on the change branch. Receive and Change are never combined into a shared limit.
- Example with gap 2: five used Receive addresses result in indexes 0–6 being active; three used Change addresses result in indexes 0–4 being active.
- Full Sentinel activation on startup/reload and global settings save uses the same HD gap discovery as saving an individual watch target. An already discovered XPUB/descriptor can no longer collapse back to raw `Receive N + Change N` counts.
- A device-bound encrypted standby pool contains **concrete pre-derived addresses only**, allowing the active gap to advance while the main vault is locked. Raw XPUB/descriptor secrets remain outside the runtime cache.
- XPUB/descriptor watch cards show the actual active `Receive … · Change …` split.

#### Balance, UTXOs and transaction history
- The lightweight 15-second status refresh returns privacy-safe per-monitor aggregates so watch cards retain balance, derived-address counts and UTXO counts without opening transaction history.
- Current wallet balance, UTXO totals and historical transaction discovery use the **same active used-address + gap set**; inactive encrypted standby addresses are excluded.
- The watch-card **Balance** now reuses the already authoritative **Current wallet balance** returned by the transaction overview whenever that overview is available, so both displays stay identical instead of diverging through separate frontend calculations.
- Loading the transaction overview immediately refreshes the watch card with that authoritative balance.
- Transaction counts are deduplicated by real Bitcoin transaction ID: one Bitcoin transaction touching several wallet addresses is counted once.
- Concrete derived addresses remain omitted from the lightweight status endpoint.

#### Restart persistence and Fulcrum settings
- Fulcrum/Electrum connection settings and the encrypted concrete-address runtime state are restored after a Home Assistant restart instead of silently reverting to defaults.
- After the main vault is unlocked, the persisted Sats Sentinel configuration is reactivated from the password-protected vault so saved addresses, XPUB/YPUB/ZPUB targets, descriptors, labels and gap limits return as the authoritative configuration.
- Saving a watch target first persists changed Sentinel/Fulcrum settings, preventing a newly entered host/port/TLS configuration from being lost when the watch entry is saved immediately afterwards.
- Restart regression coverage uses fresh runtime-store instances and verifies restoration while keeping raw XPUB/descriptor secrets out of the device-bound runtime cache.

#### Non-blocking XPUB saves
- Saving an XPUB/descriptor no longer waits synchronously for the full Fulcrum gap scan and initial poll inside the HTTP request.
- The encrypted watch configuration is persisted first and the request returns promptly; HD gap discovery and initial wallet synchronization continue as a Home Assistant background task.
- A newer save supersedes/cancels an older pending scan so stale discovery results cannot overwrite the newest watch configuration.
- The UI reports that the address scan is running in the background instead of timing out with “Home Assistant not reachable”.

#### Release structure and validation
- The stable frontend layout introduced in v0.21.0.11 remains permanent: `index.html`, `panel.js`, `static/app.js`, `static/style.css` and `static/performance-math.js` are overwritten in place and cache-busted with `?v=0.21.0.12`.
- **No legacy frontend files need to be deleted from GitHub for v0.21.0.12.**
- Home Assistant custom integration: **v0.21.0.12**.
- Tor Gateway remains **v0.21.0.3**.
- Final repository suite: **502 tests + 8 subtests**, plus Python compile, JavaScript syntax, JSON/SBOM and release-integrity checks.

### Deutsch

Dieses Wartungsrelease baut auf **v0.21.0.11** auf und härtet Sats Sentinel für echte XPUB/YPUB/ZPUB- und Descriptor-Wallets: korrekte getrennte Gap-Limits, Neustart-Persistenz, nicht-blockierendes Speichern, konsistente Bestände und vollständige TX-Abdeckung aller aktiven Adressen.

#### XPUB-/Descriptor-Gap-Erkennung
- `receive_count` ist ein echtes **Receive-Gap-Limit** und keine Obergrenze für die insgesamt überwachten Receive-Adressen. Sentinel behält alle benutzten Receive-Adressen und stoppt erst nach der eingestellten Zahl aufeinanderfolgender unbenutzter Adressen hinter dem benutzten Bereich.
- `change_count` verwendet auf dem Change-Branch **dieselbe unabhängige Gap-Limit-Logik**. Receive und Change werden niemals zu einem gemeinsamen Limit zusammengefasst.
- Beispiel mit Gap 2: fünf benutzte Receive-Adressen ergeben die aktiven Indizes 0–6; drei benutzte Change-Adressen ergeben die aktiven Indizes 0–4.
- Die vollständige Sentinel-Aktivierung bei Start/Reload und beim globalen Speichern verwendet dieselbe HD-Gap-Erkennung wie das Speichern eines einzelnen Watch-Ziels. Ein bereits erkanntes XPUB-/Descriptor-Wallet kann nicht mehr auf die nackten Werte `Receive N + Change N` zurückfallen.
- Ein gerätegebunden verschlüsselter Standby-Pool enthält **ausschließlich konkrete vorab abgeleitete Adressen**, damit der aktive Gap auch bei gesperrtem Haupttresor nach vorne wandern kann. Rohe XPUB-/Descriptor-Geheimnisse bleiben außerhalb des Runtime-Caches.
- XPUB-/Descriptor-Watch-Karten zeigen die tatsächlich aktive Aufteilung `Receive … · Change …`.

#### Bestand, UTXOs und Transaktionshistorie
- Der leichte 15-Sekunden-Statusrefresh liefert datenschutzfreundliche Aggregate pro Watch-Eintrag, damit Bestand, abgeleitete Adressen und UTXO-Zahl auch ohne geöffnete Transaktionshistorie sichtbar bleiben.
- Aktueller Wallet-Bestand, UTXO-Summen und historische TX-Erkennung verwenden **denselben aktiven Satz aus benutzten Adressen + Gap**; inaktive verschlüsselte Standby-Adressen werden ausgeschlossen.
- Der **Bestand** auf der Watch-Karte übernimmt jetzt den bereits maßgeblichen **Aktuellen Wallet-Bestand** aus der Transaktionsübersicht, sobald diese Daten vorhanden sind. Dadurch können beide Anzeigen nicht mehr durch getrennte Frontend-Berechnungen auseinanderlaufen.
- Nach dem Laden der Transaktionsübersicht wird die Watch-Karte sofort mit diesem maßgeblichen Bestand aktualisiert.
- Transaktionszahlen werden anhand der echten Bitcoin-TXID dedupliziert: Eine Bitcoin-Transaktion, die mehrere eigene Wallet-Adressen berührt, zählt einmal.
- Konkrete abgeleitete Adressen werden vom leichten Status-Endpunkt weiterhin nicht ausgegeben.

#### Neustart-Persistenz und Fulcrum-Einstellungen
- Fulcrum-/Electrum-Verbindungsdaten und der verschlüsselte Runtime-Zustand der konkreten abgeleiteten Adressen werden nach einem Home-Assistant-Neustart wiederhergestellt, statt still auf Standardwerte zurückzufallen.
- Nach dem Entsperren des Haupttresors wird die gespeicherte Sats-Sentinel-Konfiguration erneut aus dem passwortgeschützten Tresor aktiviert. Gespeicherte Adressen, XPUB/YPUB/ZPUB-Ziele, Descriptoren, Labels und Gap-Limits sind damit wieder der maßgebliche Stand.
- Beim Speichern eines Watch-Ziels werden geänderte Sentinel-/Fulcrum-Einstellungen zuerst dauerhaft gespeichert, damit ein neu eingetragener Host/Port/TLS-Stand nicht verloren geht.
- Neustart-Regressionstests verwenden frische Runtime-Store-Instanzen und prüfen die Wiederherstellung, während rohe XPUB-/Descriptor-Geheimnisse weiterhin aus dem gerätegebundenen Runtime-Cache herausbleiben.

#### Nicht-blockierendes XPUB-Speichern
- Beim Speichern eines XPUBs/Descriptors wird nicht mehr synchron im HTTP-Request auf den vollständigen Fulcrum-Gap-Scan und den ersten Poll gewartet.
- Die verschlüsselte Watch-Konfiguration wird zuerst dauerhaft gespeichert und der Request kehrt zügig zurück; HD-Gap-Erkennung und erste Wallet-Synchronisierung laufen anschließend als Home-Assistant-Hintergrundtask weiter.
- Ein neuerer Speichervorgang ersetzt/bricht einen älteren noch laufenden Scan ab, damit veraltete Ergebnisse keinen neueren Watch-Stand überschreiben können.
- Die Oberfläche meldet den laufenden Adressscan im Hintergrund, statt mit „Home Assistant nicht erreichbar“ in einen Timeout zu laufen.

#### Release-Struktur und Prüfung
- Die mit v0.21.0.11 eingeführte stabile Frontend-Struktur bleibt dauerhaft bestehen: `index.html`, `panel.js`, `static/app.js`, `static/style.css` und `static/performance-math.js` werden nur überschrieben und mit `?v=0.21.0.12` cache-gebustet.
- **Für v0.21.0.12 müssen bei GitHub keine alten Frontend-Dateien gelöscht werden.**
- Home-Assistant-Custom-Integration: **v0.21.0.12**.
- Tor Gateway bleibt **v0.21.0.3**.
- Finale Repository-Suite: **502 Tests + 8 Subtests**, zusätzlich Python-Compile, JavaScript-Syntax, JSON/SBOM und Release-Integritätsprüfungen.

## v0.21.0.11 — 2026-08-16: causal bottom confirmations, multi-cycle markers & collapsible Sats Sentinel

### English

This release builds on **v0.21.0.10** and fixes the historical bottom-confirmation association without loosening the backtested default thresholds. It also finalizes the multi-cycle marker UX, modular-model field help, collapsible Sats Sentinel layout and stable frontend release structure.

#### Historical market assessment
- `10 years` and `Max` now use the **best causal raw score per 4-year window** instead of a single global best value. The true bucket maximum is calculated before chart sampling and its date is always retained in the displayed series.
- Best values are drawn as **small star markers only** so the chart is no longer covered by large marker areas. A compact legend below the historical chart lists date and raw score for every star.
- The same marker set is used in the overview **Bitcoin price + market assessment** chart.
- Desktop users can hover a star and touch devices can tap it to open the marker popup.
- **Bottom confirmation is now associated causally after the stress/best-score day.** Each 4-year marker independently scans forward only inside the configured `turning_zone_memory_days` window and only with data available as of each candidate day. This fixes legitimate bottoms whose rebound/divergence/trend confirmation arrived days after the highest score.
- Marker popup/legend data now includes the actual confirmation date and lag in days. Historical score reconstruction itself remains look-ahead-free.
- The modular model editor now provides an explanation for every configurable field, including what the parameter controls and the practical effect of increasing or decreasing it. Weight help explicitly explains that a higher weight increases influence rather than automatically increasing the final score.

#### Sats Sentinel UI
- The six top-level Sats Sentinel cards/sections are now independently collapsible: status, journal, test lab, monitor settings, watch targets and privacy.
- The open/collapsed state is persisted in browser storage **per portfolio**, so the chosen layout returns after reloads and portfolio switches on the same device/browser.
- Sensible defaults keep the status, journal and watch-target sections open while test lab, settings and privacy start collapsed.

#### Frontend release layout
- Frontend delivery uses only stable canonical files: `index.html`, `panel.js`, `static/app.js`, `static/style.css` and `static/performance-math.js`.
- Cache invalidation is handled with `?v=0.21.0.11`; no new release/hash-named frontend bundles are created.
- `.gitignore` blocks the legacy `*-v*.js/css/html` patterns so future releases do not require manual frontend-file deletion.
- When upgrading the GitHub repository from the old layout, the existing legacy hash/version files should be removed **once**; subsequent releases overwrite only the stable files.

#### Versions and QA
- Home Assistant custom integration: **v0.21.0.11**.
- Tor Gateway remains **v0.21.0.3**.
- Final regression count is recorded in `RELEASE-QC-v0.21.0.11.md`.

### Deutsch

Dieses Release baut auf **v0.21.0.10** auf und korrigiert die Zuordnung der historischen Bodenbestätigung, ohne die backgetesteten Standard-Schwellen künstlich zu lockern. Zusätzlich werden die Multi-Zyklus-Marker, die Feldhilfen des modularen Modells, das einklappbare Sats-Sentinel-Layout und die stabile Frontend-Release-Struktur fertiggestellt.

#### Historische Markteinschätzung
- `10 Jahre` und `Max` verwenden jetzt den **besten kausalen Rohscore je 4-Jahres-Fenster** statt nur eines globalen Bestwerts. Das echte Maximum jedes Fensters wird vor dem Chart-Sampling bestimmt und sein Datum bleibt im dargestellten Datensatz erhalten.
- Die Bestwerte erscheinen im Chart nur noch als **kleine Sterne**, damit keine große Markierungsfläche den Verlauf verdeckt. Unter dem Historical-Chart listet eine kompakte Legende Datum und Rohscore aller Sterne.
- Dieselben Marker werden im Startseitenchart **Bitcoin-Kurs + Markteinschätzung** verwendet.
- Am PC öffnet sich das Popup beim Überfahren des Sterns mit der Maus, auf Touch-Geräten per Antippen.
- **Die Bodenbestätigung wird jetzt kausal nach dem Stress-/Bestscore-Tag zugeordnet.** Jeder 4-Jahres-Marker prüft unabhängig nur innerhalb des eingestellten `turning_zone_memory_days`-Fensters die Folgetage und berechnet jeden Kandidaten ausschließlich mit den bis dahin verfügbaren Daten. Damit werden echte Wendepunkte erfasst, deren Rebound-/Divergenz-/Trendbestätigung erst einige Tage nach dem höchsten Score eintraf.
- Popup und Legende können das tatsächliche Bestätigungsdatum sowie die Verzögerung in Tagen anzeigen. Die historische Score-Berechnung selbst bleibt vollständig frei von Look-ahead.
- Im modularen Modell besitzt jetzt jedes einstellbare Feld eine Erklärung dazu, was der Parameter steuert und welche praktische Wirkung ein höherer oder niedrigerer Wert hat. Bei Gewichten wird ausdrücklich erklärt, dass ein höheres Gewicht den Einfluss erhöht und nicht automatisch den Endscore nach oben verschiebt.

#### Sats-Sentinel-Oberfläche
- Die sechs Hauptkarten/-bereiche von Sats Sentinel sind jetzt einzeln ein- und ausklappbar: Status, Journal, Testlabor, Überwachungseinstellungen, Watch-Ziele und Datenschutz.
- Der offene/eingeklappte Zustand wird **pro Portfolio** im Browser gespeichert und nach Neuladen oder Portfolio-Wechsel auf demselben Gerät/Browser wiederhergestellt.
- Sinnvolle Standardansicht: Status, Journal und Watch-Ziele offen; Testlabor, Einstellungen und Datenschutz eingeklappt.

#### Frontend-Release-Struktur
- Das Frontend verwendet nur noch die stabilen kanonischen Dateien `index.html`, `panel.js`, `static/app.js`, `static/style.css` und `static/performance-math.js`.
- Cache-Busting erfolgt über `?v=0.21.0.11`; neue versions-/hashbasierte Frontend-Bundles werden nicht mehr erzeugt.
- `.gitignore` blockiert die alten `*-v*.js/css/html`-Muster, damit bei künftigen Releases kein manuelles Löschen alter Frontend-Dateien mehr nötig ist.
- Beim einmaligen Wechsel des GitHub-Repositories von der alten Struktur werden die bereits vorhandenen Legacy-Dateien **ein einziges Mal** gelöscht. Danach werden nur noch die stabilen Dateien überschrieben.

#### Versionen und QA
- Home-Assistant-Custom-Integration: **v0.21.0.11**.
- Tor Gateway bleibt **v0.21.0.3**.
- Die endgültige Testanzahl steht in `RELEASE-QC-v0.21.0.11.md`.

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
- XPUB/YPUB/ZPUB monitor type is now recovered defensively in both frontend and backend before address validation. Copy/paste whitespace inside long extended public keys is stripped before validation, fixing the misleading `Bitcoin address is missing or too long` path even for line-wrapped keys. Validation errors now identify the affected monitor and effective type.
- Added an on-demand per-watch **historical transaction overview** with configurable 5/10/25/50/100 TX depth. Historical rows never create retroactive alerts; transactions that were actually detected after Sentinel setup are highlighted with a dedicated Sentinel marker.
- Watch cards now show the current balance across their concrete derived addresses. The transaction overview shows wallet-relative incoming/outgoing amount plus whole-transaction input sum, output sum and fee where all prevouts are available.
- Removing a watch entry now also permanently deletes all journal rows for that monitor from the encrypted Sentinel cache, including derived-address activity for XPUB/descriptor monitors.

#### Adaptive market assessment
- Added a modular **0–100 market assessment** based only on public historical Bitcoin price data. It is explicitly an additional assessment, not a buy signal, bottom/top declaration, forecast, probability or investment recommendation.
- Added adaptive volatility/reference windows, long-term valuation, drawdown, historical price position, deviation, momentum/RSI, cycle models, Mayer Multiple, ATH drawdown, 200-day distance, power-law ratio and configurable weights/thresholds.
- Added independent bottom/top zone and confirmation diagnostics with configurable turning-point weights and memory/separation parameters.
- Added a standard Home Assistant market-assessment sensor with raw decimal score precision.
- Added causal historical score reconstruction: each historical point uses only information available at that date, preventing look-ahead bias.
- The historical market chart now marks the **true highest causal raw score inside the selected range**. The best point is calculated before chart sampling and is retained even on `Max`; if the turning-point diagnostics on that day also satisfy the configured bottom-zone + confirmation gates, the marker carries the corresponding bottoming context.
- Added a dedicated historical score chart with fixed 0–100 axis, crosshair, date/score axis badges, optional BTC-price overlay, independent right-side price axis, linear/log price scaling and adjustable BTC-overlay opacity.
- Frontend delivery now uses stable canonical filenames (`index.html`, `panel.js`, `app.js`, `style.css`, `performance-math.js`) with release-version query cache busting. Future releases no longer require deleting old hash/version-named frontend files.
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
- Final local release suite: **479 tests + 8 subtests passed**.
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
- Der XPUB/YPUB/ZPUB-Typ wird jetzt defensiv sowohl im Frontend als auch im Backend vor der Adressprüfung erkannt. Copy/Paste-Leerzeichen und Zeilenumbrüche in langen Extended Public Keys werden vor der Prüfung entfernt. Damit ist der irreführende Pfad `Bitcoin address is missing or too long` auch bei umgebrochenen Keys behoben. Validierungsfehler nennen den betroffenen Monitor und den erkannten Typ.
- Neue bedarfsgeladene **historische Transaktionsübersicht pro Watch-Eintrag** mit einstellbaren 5/10/25/50/100 TX. Rückwirkend geladene Historie erzeugt niemals Alarme; Transaktionen, die Sentinel nach dem Einrichten tatsächlich erkannt hat, werden mit einem eigenen Sentinel-Marker hervorgehoben.
- Watch-Karten zeigen den aktuellen Bestand über ihre konkreten abgeleiteten Adressen. In der TX-Übersicht werden Wallet-Ein-/Ausgang sowie die Summe aller Transaktions-Inputs, aller Outputs und – sofern alle Prevouts verfügbar sind – die Fee angezeigt.
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
- Finale lokale Release-Suite: **479 Tests + 8 Subtests bestanden**.
- Python-Compile, JavaScript-Syntax, Frontend-Asset-Integrität, Quellenregeln, TLS-Pinning, Journal-Löschung, kausale Historie/No-Look-Ahead und Chart-Overlay-Regressionen sind grün.
- Home-Assistant-Custom-Integration: **v0.21.0.10**.
- Tor Gateway bleibt **v0.21.0.3**.

## v0.21.0.9 — 2026-08-14: Revolut X, manual bookings & network fees

### English

#### Revolut X CSV
- Added a dedicated parser for `Symbol`, `Type`, `Quantity`, `Price`, `Value`, `Fees`, `Date`.
- `BTC`/`XBT` rows are imported; other assets are skipped.
- `Buy` becomes a purchase and `Sell` a sale; `Quantity` is BTC and `Fees` is a separate fiat fee.
- `Value` remains the gross trade value before fees: purchase total = `Value + Fees`, sale net proceeds = `Value - Fees`.
- Supports dates such as `21 Jan 2026, 21:21:21` and month-first AM/PM formats; if `Price` is missing it is reconstructed from `Value / Quantity`.

#### Manual bookings & FIFO
- Added **Income** as a valued BTC inflow that creates FIFO cost basis like a purchase while remaining a separate booking type.
- **Expense** can now be entered manually and realizes profit/loss through the same per-portfolio FIFO logic as a sale while remaining semantically separate.
- Booking type can be changed during editing. The full FIFO chain is atomically revalidated afterwards and new/larger oversells remain blocked.
- Added separate overview totals for sales, expenses, income and transaction fees plus total realized profit/loss.
- Renamed **“Fiat secured”** to **“Purchasing power secured”**; income intentionally does not count as fiat-funded purchasing.

#### On-chain and Lightning transaction fees
- Added standalone **Transaction fee** bookings with network `On-Chain` or `Lightning` and amount in BTC/sats.
- The fee reduces the actual stack and consumes the corresponding FIFO lots without inventing sale proceeds.
- Historical BTC price at booking time is used to display the fiat value of the network fee.
- Existing imported `fee_btc` values reduce the stack additionally only when explicitly marked stack-effective, avoiding double deduction for legacy/net imports.
- Total-fee analytics include explicit fiat fees plus fiat values of recorded BTC/sats fees; pure network fees do not distort trading-volume fee ratios.

#### Historical plausibility check
- Manual purchases, income, sales and expenses are compared non-blockingly with the historical BTC price at the booking timestamp.
- From **10%** deviation a warning shows entered price, reference price and percentage difference.
- Old bookings never fall back to today's live price. If no historical reference is available, the check is skipped.

#### Performance & ranges
- New order: **1 day · week-to-date · 1 week · month-to-date · 30 days · 90 days · YTD · 1 year · 3 years · 5 years · 10 years · since first purchase · Max**.
- `week-to-date` starts Monday 00:00; `1 week` is rolling seven days; `month-to-date` starts at the first day of the month 00:00.
- XIRR remains the money-weighted personal return of the **selected range**, annualized.
- TWR remains cash-flow neutral: additional purchases/income do not artificially increase return; transaction fees remain real performance costs.
- CAGR is described more clearly as the average annualized Bitcoin market-price development and separated from personal XIRR/TWR.

#### Compatibility & tests
- Home Assistant integration: **v0.21.0.9**.
- Tor Gateway remains **v0.21.0.3**.
- Added targeted regressions for Revolut X, historical reference prices, income, expense/FIFO and network fees.
- Final local suite: **373 tests + 8 subtests passed**, plus JavaScript syntax, Python compile, JSON/YAML and version-consistency checks.

### Deutsch

#### Revolut X CSV
- Neuer eigener Parser für `Symbol`, `Type`, `Quantity`, `Price`, `Value`, `Fees`, `Date`.
- `BTC`/`XBT` wird übernommen; andere Assets werden übersprungen.
- `Buy` wird Kauf, `Sell` wird Verkauf; `Quantity` ist BTC und `Fees` eine separate Fiatgebühr.
- `Value` bleibt der Brutto-Handelswert vor Gebühren: Kauf-Gesamtbetrag = `Value + Fees`, Verkaufs-Nettoerlös = `Value - Fees`.
- Unterstützt u. a. `21 Jan 2026, 21:21:21` sowie Monat-zuerst mit AM/PM; fehlt `Price`, wird er aus `Value / Quantity` rekonstruiert.

#### Manuelle Buchungen & FIFO
- Neue Buchungsart **Einnahme**: bewerteter BTC-Zugang mit FIFO-Einstand wie bei einem Kauf, aber separat ausgewiesen.
- **Ausgabe** ist nun auch manuell auswählbar und realisiert Gewinn/Verlust über dieselbe depotweise FIFO-Logik wie ein Verkauf, bleibt aber semantisch getrennt.
- Die Buchungsart kann beim Bearbeiten geändert werden. Danach wird die vollständige FIFO-Kette atomar neu validiert; ein neu erzeugter/größerer Oversell wird weiterhin verhindert.
- Übersicht ergänzt um getrennte Summen für Verkäufe, Ausgaben, Einnahmen und Transaktionsgebühren sowie den gesamten realisierten Gewinn/Verlust.
- **„Fiat in Sicherheit gebracht“** wurde in **„Kaufkraft in Sicherheit gebracht“** umbenannt; Einnahmen zählen dort bewusst nicht als Fiat-Kauf.

#### On-Chain- und Lightning-Transaktionsgebühren
- Neue eigenständige Buchungsart **Transaktionsgebühr** mit Netzwerk `On-Chain` oder `Lightning` und Betrag in BTC/Sats.
- Die Gebühr mindert den tatsächlichen Stack und verbraucht die entsprechenden FIFO-Lots, ohne einen fiktiven Verkaufserlös zu erzeugen.
- Der historische BTC-Kurs am Buchungszeitpunkt dient zur Anzeige des Fiat-Gegenwerts der Gebühr.
- Bestehende importierte `fee_btc`-Werte reduzieren den Stack nur zusätzlich, wenn sie ausdrücklich als stack-wirksam markiert sind; dadurch werden Legacy-/Nettoimporte nicht doppelt belastet.
- Gebührenanalyse: Gesamte Gebühren enthalten explizite Fiatgebühren plus Fiat-Gegenwerte erfasster BTC-/Sats-Gebühren; reine Netzwerkgebühren verzerren keine Handelsvolumenquote.

#### Historische Plausibilitätsprüfung
- Manuelle Käufe, Einnahmen, Verkäufe und Ausgaben werden nicht blockierend mit dem historischen BTC-Kurs des Buchungszeitpunkts verglichen.
- Ab **10 %** Abweichung erscheint eine Warnung mit eingegebenem Kurs, Referenzkurs und prozentualer Abweichung.
- Für alte Buchungen wird niemals der heutige Live-Kurs als Ersatz benutzt. Ist kein historischer Referenzkurs vorhanden, wird die Prüfung nur übersprungen.

#### Performance & Zeiträume
- Neue Reihenfolge: **1 Tag · seit Wochenbeginn · 1 Woche · seit Monatsbeginn · 30 Tage · 90 Tage · YTD · 1 Jahr · 3 Jahre · 5 Jahre · 10 Jahre · seit erstem Kauf · Max**.
- `seit Wochenbeginn` startet Montag 00:00; `1 Woche` ist rollierend sieben Tage; `seit Monatsbeginn` startet am Monatsersten 00:00.
- XIRR bleibt die geldgewichtete persönliche Rendite des **gewählten Zeitraums**, auf ein Jahr hochgerechnet.
- TWR bleibt cashflow-neutral: zusätzliche Käufe/Einnahmen erhöhen die Rendite nicht künstlich; Transaktionsgebühren bleiben echte Performancekosten.
- CAGR wird klarer als durchschnittliche annualisierte Entwicklung des Bitcoin-Marktpreises beschrieben und von persönlicher XIRR/TWR abgegrenzt.

#### Kompatibilität & Tests
- Home-Assistant-Integration: **v0.21.0.9**.
- Tor Gateway: weiterhin **v0.21.0.3**.
- Neue gezielte Regressionstests für Revolut X, historische Referenzkurse, Einnahmen, Ausgaben/FIFO und Netzwerkgebühren.
- Finale lokale Testsuite: **373 Tests + 8 Subtests bestanden**; zusätzlich JavaScript-Syntax, Python-Compile, JSON/YAML und Versionskonsistenz geprüft.

## v0.21.0.8 — 2026-08-12: Peach Bitcoin CSV Import

### English

#### Peach Bitcoin
- Added a dedicated Peach Bitcoin CSV parser for `Date`, `Trade ID`, `Type`, `Amount`, `Price`, `Bitcoin Price`, `Currency` and `Premium`.
- Peach `Amount` is interpreted exclusively as an integer satoshi amount; 100,000 sats becomes exactly 0.001 BTC.
- `Price` remains the actual total fiat amount paid or received.
- `Premium` is treated as a percentage. For purchases, the premium contained in `Bitcoin Price` is removed with `Bitcoin Price / (1 + Premium/100)`; the difference to paid `Price` is shown as a fiat fee without increasing FIFO cost basis twice.
- `Trade ID` provides stable import identity while raw source IDs are still not stored in the ledger unless needed.
- Sales are supported; actual fiat proceeds remain authoritative and a positive premium is not blindly booked as an extra sale fee.

#### Documentation
- README made fully bilingual in German and English.
- Peach Bitcoin documented in the import overview and `CSV-IMPORT.md`.

#### Tests and release split
- Five targeted Peach regressions cover sats conversion, premium/fee calculation, Trade-ID duplicates, missing premium and sale handling.
- **Home Assistant integration:** v0.21.0.8.
- **Tor Gateway:** remains v0.21.0.3.

### Deutsch

#### Peach Bitcoin
- Neuer eigener Peach-Bitcoin-CSV-Parser für die Spalten `Date`, `Trade ID`, `Type`, `Amount`, `Price`, `Bitcoin Price`, `Currency` und `Premium`.
- `Amount` wird bei Peach ausschließlich als Satoshi-Ganzzahl interpretiert; 100.000 sats werden exakt zu 0,001 BTC.
- `Price` bleibt der tatsächlich gezahlte bzw. erhaltene Fiat-Gesamtbetrag.
- `Premium` wird als Prozentwert behandelt. Bei Käufen wird der in `Bitcoin Price` enthaltene Aufschlag mit `Bitcoin Price / (1 + Premium/100)` entfernt; die Differenz zum gezahlten `Price` wird als Fiatgebühr ausgewiesen, ohne den FIFO-Einstand doppelt zu erhöhen.
- `Trade ID` dient als stabile Import-Identität; Roh-IDs werden weiterhin nicht ungefragt im Ledger gespeichert.
- Verkäufe werden unterstützt; bei Verkäufen bleibt der tatsächliche Fiat-Erlös maßgeblich und es wird kein positiver Premiumwert blind als zusätzliche Gebühr gebucht.

#### Dokumentation
- README vollständig zweisprachig Deutsch/Englisch.
- Peach Bitcoin in der Importübersicht und in `CSV-IMPORT.md` dokumentiert.

#### Tests und Release-Aufteilung
- Fünf gezielte Peach-Regressionstests: Sats-Umrechnung, Premium-/Gebührenrechnung, Trade-ID-Dubletten, fehlendes Premium und Verkauf.
- **Home-Assistant-Integration:** v0.21.0.8.
- **Tor Gateway:** bleibt v0.21.0.3.

## v0.21.0.7 — 2026-08-11: Bitpanda CSV & Fee Hotfix

### English

#### Bitpanda import
- Added a dedicated Bitpanda Transaction Report parser detected through `Venue: Bitpanda`, `Reported by Bitpanda GmbH` and the characteristic header layout.
- The existing BTC/XBT normalizer remains the Bitcoin-only boundary. Trades in other assets and fiat-only deposits are ignored.
- `buy` is processed as purchase and `sell` as sale; `In/Out` is supplemental and does not determine booking type.
- `Transaction ID` is the primary stable import identity. Raw IDs are not stored in the ledger and are only hashed locally.
- Physical CSV line numbers remain intact even with Bitpanda metadata rows so import errors point to the actual file row.

#### Withdrawal and fee logic
- BTC `withdrawal` remains a transfer and does not create a FIFO sale.
- An explicit Bitpanda withdrawal fee in BTC is assigned to the purchase batch accumulated since the previous BTC withdrawal.
- Shared BTC fees are distributed proportionally by gross BTC to whole satoshis; the final purchase receives the exact remainder so the total equals the exported BTC fee exactly.
- Network fees reduce the real stack and remain as `fee_btc`; they are not artificially converted into fiat fees.
- Trading fees/premiums already contained in the Bitpanda execution price are stored separately as `included_fee`. They count in fee analytics but do not increase FIFO cost basis twice.
- If the CSV provides an explicit fiat trading fee it is used as an included fee. If derivable only from `Amount Fiat`, gross BTC and market price, the difference is marked estimated. If it cannot be reconstructed, the 0.99% BTC premium is used only as an editable analytics estimate.

#### Import preview and checks
- Import preview and persistence support included trading fees and their estimate flag.
- Bitpanda validation uses the original trade BTC before a later withdrawal fee, preventing large on-chain fees from creating false purchase deviations.
- Missing Bitpanda `Fee` values (`-`) are allowed and no longer invalidate otherwise complete purchase/sale rows.
- Export and dashboard fee metrics include `included_fee` without double-counting cost basis.

#### HACS / Home Assistant
- Added a shared `Validate` workflow using the HACS Action and Hassfest.
- Updated to `actions/checkout@v5`.
- Manifest uses `@21Koblenz` as `codeowners`, HACS/Hassfest-compliant key ordering and `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)`.
- **Tor Gateway remains v0.21.0.3**.

#### Tests
- Bitpanda regressions cover Buy/Sell, BTC/XBT filtering, altcoin exclusion, deposits, BTC withdrawals, multiple purchases per withdrawal batch, satoshi-exact fee allocation, physical line numbers, ID-based duplicates and included trading fees.
- Final suite: **354 tests + 8 subtests passed**; JavaScript syntax, Python compile, JSON parsing and version consistency also passed.

### Deutsch

#### Bitpanda-Import
- Neuer eigener Bitpanda-Parser für Transaction Reports mit Erkennung über `Venue: Bitpanda`, `Reported by Bitpanda GmbH` und die charakteristische Header-Struktur.
- Der vorhandene BTC/XBT-Normalisierer bleibt die zentrale Bitcoin-only-Grenze. Käufe und Verkäufe anderer Assets sowie reine Fiat-Deposits werden ignoriert.
- `buy` wird als Kauf und `sell` als Verkauf verarbeitet; `In/Out` ist nur Zusatzinformation und bestimmt nicht die Buchungsart.
- `Transaction ID` wird als primäre stabile Import-Identität verwendet. Roh-IDs werden weiterhin nicht im Ledger gespeichert, sondern nur lokal gehasht.
- Physische CSV-Zeilennummern bleiben auch bei Bitpanda-Metadatenzeilen erhalten, damit Importfehler auf die tatsächliche Datei verweisen.

#### Withdrawal- und Gebührenlogik
- BTC-`withdrawal` bleibt ein Transfer und erzeugt keinen FIFO-Verkauf.
- Eine explizite Bitpanda-Withdrawal-Fee in BTC wird dem seit dem vorherigen BTC-Withdrawal aufgebauten Kauf-Batch zugeordnet.
- Gemeinsame BTC-Fees werden proportional nach Brutto-BTC auf ganze Satoshis verteilt; der letzte Kauf erhält den exakten Rest, sodass die Summe exakt der exportierten BTC-Fee entspricht.
- Die Netzwerkfee reduziert den tatsächlichen Stack und bleibt als `fee_btc` erhalten; sie wird nicht künstlich in eine Fiat-Fee umgerechnet.
- Im Bitpanda-Ausführungspreis enthaltene Handelsgebühren/Prämien werden als separates `included_fee` gespeichert. Sie zählen in der Gebührenanalyse, verändern aber den FIFO-Einstand nicht ein zweites Mal.
- Liefert die CSV eine explizite Fiat-Handelsgebühr, wird diese als enthaltene Gebühr übernommen. Ist sie nur aus `Amount Fiat`, Brutto-BTC und Marktpreis ableitbar, wird die Differenz als geschätzt markiert. Ist sie aus dem CSV nicht rekonstruierbar, wird die 0,99-%-BTC-Prämie ausschließlich als editierbare Analytics-Schätzung verwendet.

#### Importvorschau und Kontrolle
- Importvorschau und Speicherung unterstützen enthaltene Handelsgebühren einschließlich Schätzkennzeichen.
- Die Rechenkontrolle verwendet für Bitpanda den ursprünglichen Trade-BTC-Betrag vor einer späteren Withdrawal-Fee; hohe On-Chain-Gebühren erzeugen dadurch keine falsche Kaufabweichung.
- Fehlende Bitpanda-`Fee`-Werte (`-`) sind zulässig und machen eine ansonsten vollständige Kauf-/Verkaufszeile nicht ungültig.
- Export und Dashboard-Gebührenmetriken berücksichtigen `included_fee`, ohne die Kostenbasis doppelt zu belasten.

#### HACS / Home Assistant
- Gemeinsamer `Validate`-Workflow mit HACS Action und Hassfest.
- `actions/checkout@v5`.
- Manifest mit `@21Koblenz` als `codeowners`, HACS/Hassfest-konformer Schlüsselreihenfolge und `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)`.
- **Tor Gateway bleibt v0.21.0.3**.

#### Tests
- Bitpanda-Regressionen decken Buy/Sell, BTC/XBT-Filter, Altcoin-Ausschluss, Deposits, BTC-Withdrawals, mehrere Käufe pro Withdrawal-Batch, Satoshi-genaue Fee-Verteilung, physische Zeilennummern, ID-basierte Dubletten und enthaltene Handelsgebühren ab.
- Finale Testsuite: **354 Tests + 8 Subtests bestanden**; JavaScript-Syntaxprüfung, Python-Compile-Check, JSON-Parsing und Versionskonsistenz ebenfalls erfolgreich.

## v0.21.0.6 — 2026-08-11: Calculation, Privacy & Large-Ledger Performance Audit

### English

#### Calculation and FIFO
- Sales **and valued expenses** are fully processed as FIFO disposals; Wavespace/card payments appear correctly in the FIFO disposal overview.
- FIFO disposals additionally show **average purchase price up to that point** and a separate average-price P/L comparison. Each disposal row exposes FIFO profit/return and average-price profit/return separately; the summary also shows historical comparison price, comparison cost basis and absolute/relative result. The comparison is BTC-weighted across all purchases in the same fiat currency up to the disposal timestamp including purchase fees; it is explicitly not a FIFO/tax value and never changes lot assignment.
- Partially consumed purchase lots keep their exact remainder; the next sale/expense consumes the remainder of the oldest still-open lot first.
- Cost basis including proportional purchase fees and proportional disposal fees was rechecked against independent randomized references.
- Larger disposals spanning several purchase lots evaluate every lot at its own historical basis; total basis is the sum of the actually consumed lot portions.
- Same-timestamp bookings consistently use the same UTC tie ordering: BTC inflow before BTC outflow.
- Add/Edit/Delete/Bulk Import validate atomically and prevent new or larger oversells.
- Drawdown edge cases fixed: a low at zero equals -100%; a repeated equal ATH resets `days since ATH`.
- XIRR rejects mixed-fiat cash flows without FX data instead of assuming a nonexistent conversion.
- Age buckets use 365.2425 days/year; the configurable holding-period rule remains a separate exact-day rule.
- New or edited bookings more than five minutes in the future are rejected.

#### Metrics and charts
- Added BTC CAGR since the first valued booking with clear separation from TWR and XIRR.
- Added stacking velocity for 30 days, 365 days and since inception.
- Separated realized, unrealized and total profit/loss.
- Added net fiat invested.
- Added current/max drawdown, days since last high and longest completed recovery duration.
- Added holding-period block with above/below holding rule, next 30/90 days, weighted stack age, oldest open lot and age distribution.
- Added volume-weighted purchase and disposal fee ratios; disposals include sales and valued expenses.
- BTC/on-chain fees are shown as sats only when an actual BTC fee is present or can be reconstructed exactly; unknown legacy values are not guessed.
- Added cash-flow-neutral HODL benchmark using the same external inflows/outflows as the real strategy.
- Left and right chart Y axes can independently use linear or logarithmic scaling.

#### Large-ledger performance
- Fixed Home Assistant Core timeout issues after large CSV imports and when subsequently opening/navigating the vault.
- `bulk_import` reuses the FIFO cache already calculated for oversell validation instead of immediately repeating the full FIFO run.
- FIFO uses a local lot cursor per calculation and does not rescan fully consumed lots for every later disposal. Every new calculation still starts from a fully chronological sort, so older trades inserted later correctly change FIFO allocation.
- Historical daily states are built in one chronological pass instead of recalculating FIFO for every price day.
- Historical price lookup uses prepared series and binary search; TWR, XIRR, chart series and performance values are reused per dashboard snapshot.
- XIRR normalizes/sorts cash flows only once per calculation.
- Intraday FIFO uses running sums and local lot pointers.
- Heavy overview calculations run after the visible chart in a browser idle phase and are discarded on tab changes.
- Dashboard sections are lazy-loaded; settings/security do not require a full ledger payload.
- Ledger/FIFO indexes reduce repeated linear browser lookups.
- Confirmed CSV import timeout was also raised to 300 seconds; the actual fix is the performance work above.

#### Privacy and security
- CSV duplicate checking runs completely in Home Assistant Core; existing `import_ref_hash` values are no longer loaded into the browser.
- The Core duplicate endpoint returns only boolean duplicate flags and is batch/rate limited.
- Dashboard, chart, FIFO and ledger use minimized payloads/allow-lists; notes, provider IDs and internal import/BTC-fee metadata are transferred only where required.
- Authenticated panel responses use `Cache-Control: no-store, private`, `Pragma: no-cache`, same-origin/no-referrer hardening and `X-Content-Type-Options: nosniff`.
- Restrictive CSP blocks direct network connections from the tracker frontend.
- Stale lazy responses can no longer overwrite newer dashboard state.
- Non-owners continue to receive redacted connection information.
- The encryption model (Argon2id, AES-256-GCM, HKDF-SHA-512/envelope keying) was rechecked in a code/data-flow audit; this is not an external penetration test.

#### CSV/FIFO UI and compatibility
- `FIFO SALES / Verkaufsübersicht` renamed to **FIFO DISPOSALS / FIFO-Abgänge**.
- Sale and expense are shown as disposal type; the headline count represents real disposal bookings instead of individual lot matches.
- ID-based duplicate detection from v0.21.0.4/v0.21.0.5 remains active.
- Frontend cache busting: `v021006-733b783d`.
- **Tor Gateway remains v0.21.0.3**; v0.21.0.6 changes only the custom integration.

#### Audit and tests
- Added calculation/privacy/security code audit: `AUDIT-v0.21.0.6.md`.
- Calculation details documented in `MATH-AUDIT.md`.
- Final suite: **351 tests + 8 subtests**; JavaScript numeric and syntax checks passed.

### Deutsch

#### Berechnung und FIFO

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

#### Kennzahlen und Charts

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

#### Large-Ledger-Performance

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

#### Datenschutz, Privatsphäre und Sicherheit

- CSV-Dublettenprüfung findet vollständig in Home Assistant Core statt; bestehende `import_ref_hash`-Werte werden nicht mehr in den Browser geladen.
- Der Core-Dubletten-Endpunkt liefert nur boolesche Dubletten-Flags und ist mengenbegrenzt/rate-limitiert.
- Dashboard, Chart, FIFO und Ledger verwenden minimierte Payloads bzw. Allow-Lists; Notizen, Provider-IDs und interne Import-/BTC-Fee-Metadaten werden nur dort übertragen, wo sie tatsächlich benötigt werden.
- Authentifizierte Panel-Antworten verwenden `Cache-Control: no-store, private`, `Pragma: no-cache`, same-origin/no-referrer-Härtung und `X-Content-Type-Options: nosniff`.
- Die restriktive CSP blockiert direkte Netzwerkverbindungen des Tracker-Frontends.
- Veraltete Lazy-Responses können keinen neueren Dashboard-Zustand überschreiben.
- Nicht-Owner erhalten weiterhin redigierte Verbindungsinformationen.
- Verschlüsselungsmodell (Argon2id, AES-256-GCM, HKDF-SHA-512/Envelope-Keying) wurde im Code-/Datenfluss-Audit erneut geprüft; der Audit ist kein externer Penetrationstest.

#### CSV/FIFO-Oberfläche und Kompatibilität

- `FIFO SALES / Verkaufsübersicht` heißt jetzt **FIFO ABGÄNGE / FIFO-Abgänge**.
- Verkauf und Ausgabe werden als Art angezeigt; die Kopfzahl zählt echte Abgangsbuchungen statt einzelne Lot-Matches.
- ID-basierte Dublettenerkennung aus v0.21.0.4/v0.21.0.5 bleibt aktiv.
- Frontend Cache-Busting: `v021006-733b783d`.
- **Tor Gateway bleibt v0.21.0.3**; v0.21.0.6 betrifft ausschließlich die Custom Integration.

#### Audit und Tests

- Neuer Berechnungs-, Datenschutz-, Privatsphäre- und Security-Code-Audit: [`AUDIT-v0.21.0.6.md`](AUDIT-v0.21.0.6.md).
- Berechnungsdetails: [`MATH-AUDIT.md`](MATH-AUDIT.md).
- Finale Testsuite: **351 Tests + 8 Subtests**; JavaScript-Numerik- und Syntaxprüfungen bestanden.

## v0.21.0.5 — 2026-08-11: Bulk-Import Schema Hotfix

### English

- Fixed `extra keys not allowed @ data['transactions'][0]['import_ref_hash']` when confirming CSV imports.
- `import_ref_hash` is now allowed by the actual `bulk_import` transaction schema.
- The ID-based duplicate detection introduced in v0.21.0.4 for Kraken and other supported CSV sources can therefore be stored and evaluated server-side.
- Added regression coverage so the frontend payload and Home Assistant service schema cannot silently diverge again.
- Tor Gateway remains **v0.21.0.3**; no gateway change is required.

### Deutsch

- Behebt den Fehler `extra keys not allowed @ data['transactions'][0]['import_ref_hash']` beim Bestätigen von CSV-Imports.
- `import_ref_hash` ist jetzt im tatsächlichen `bulk_import`-Transaktionsschema erlaubt.
- Die in v0.21.0.4 eingeführte ID-basierte Dubletten-Erkennung für Kraken und andere unterstützte CSV-Quellen kann dadurch serverseitig gespeichert und ausgewertet werden.
- Regressionstest ergänzt, damit Frontend-Payload und Home-Assistant-Service-Schema künftig nicht mehr auseinanderlaufen.
- Tor Gateway bleibt auf **v0.21.0.3**; dort ist keine Änderung nötig.

## v0.21.0.4 — 2026-08-11: CSV Duplicate Identity Hotfix

### English

#### Duplicate detection
- CSV bookings with identical timestamp, BTC amount, price and fee are no longer automatically merged when the source provides different order/trade/transaction IDs.
- Kraken considers `txid` and `ordertxid` together. Multiple equal-size executions of the same order remain separate bookings as soon as at least one source ID differs.
- ID-based detection applies across supported providers whenever a stable order, trade, transaction or reference ID is available.
- Raw IDs are still not stored in the ledger by default; only a SHA-256 hash of source + source ID is persisted for duplicate detection.
- Sources without a unique ID keep using the previous value fingerprint of type, timestamp, portfolio, BTC amount, currency, price and fee.
- For legacy bookings imported before this hotfix without an ID hash, quantity-based backward compatibility counts existing identical old bookings once during the first re-import while additional equal-value rows with different IDs remain separate.

#### Release split
- **Home Assistant integration:** v0.21.0.4.
- **Tor Gateway:** remains v0.21.0.3 because the hotfix contains no network/gateway change, preventing an unnecessary gateway update.

#### Tests
- Added regressions for Kraken executions with identical trade values but different `txid`/`ordertxid`.
- Added regression for Coinfinity bookings with identical values and different order IDs.
- Existing CSV parser regressions remain green.

### Deutsch

#### Dublettenerkennung

- CSV-Buchungen mit identischem Zeitpunkt, BTC-Betrag, Kurs und Gebühr werden nicht mehr automatisch zusammengelegt, wenn die Quelle unterschiedliche Order-, Trade- oder Transaktions-IDs liefert.
- Kraken berücksichtigt `txid` und `ordertxid` gemeinsam. Mehrere gleich große Ausführungen derselben Order bleiben dadurch getrennte Buchungen, sobald sich mindestens eine Quell-ID unterscheidet.
- Die ID-basierte Erkennung gilt anbieterübergreifend für unterstützte CSV-Formate, soweit eine stabile Order-, Trade-, Transaktions- oder Referenz-ID vorhanden ist.
- Roh-IDs werden weiterhin nicht ungefragt im Ledger gespeichert. Für die Dublettenerkennung wird nur ein SHA-256-Hash aus Quelle und Quell-ID persistiert.
- Quellen ohne eindeutige ID verwenden weiterhin den bisherigen Werte-Fingerprint aus Typ, Zeitpunkt, Depot, BTC-Menge, Währung, Kurs und Gebühr.
- Für bereits vor diesem Hotfix importierte Buchungen ohne ID-Hash gibt es eine mengenbasierte Legacy-Abwärtskompatibilität: vorhandene identische Altbuchungen werden beim ersten erneuten Import einmalig angerechnet, weitere gleichwertige Zeilen mit unterschiedlichen IDs bleiben erhalten.

#### Release-Aufteilung

- **Home-Assistant-Integration:** v0.21.0.4.
- **Tor Gateway:** bleibt v0.21.0.3, da dieser Hotfix keine Netzwerk-/Gateway-Änderung enthält. Dadurch erscheint für diesen Release kein unnötiges Tor-Gateway-Update.

#### Tests

- Regressionstests für Kraken-Ausführungen mit identischen Handelswerten und unterschiedlichen `txid`/`ordertxid`.
- Regressionstest für Coinfinity-Buchungen mit identischen Werten und unterschiedlichen Order-IDs.
- Bestehende CSV-Parser-Regressionstests bleiben grün.

## v0.21.0.3 — 2026-08-10: CSV Import & Fee Accounting Hotfix

### English

#### Coinfinity
- Current Coinfinity `Amount Crypto` is parsed as a BTC decimal. Values such as `0.00020000 BTC` become exactly 20,000 sats; trailing zeros of integer satoshi values are no longer stripped.
- `Mining Fee Crypto` is interpreted as satoshis. Empty or zero means Lightning; a positive value marks an on-chain payout.
- `Amount EUR` remains the actual total transferred amount. Service fee and mining fee are deducted from it and are not added to the payment a second time.
- The actually received BTC amount from `Amount Crypto` stays unchanged. Effective price for cost basis is normalized so BTC value plus fees exactly reconciles to `Amount EUR`.
- Order ID, address, transaction ID and Lightning invoice remain optional preview fields and are not silently copied into ledger notes.

#### Sats and sale fees
- Shared BTC/sats display no longer strips trailing zeros from integer satoshi values, preventing 20,000 sats from becoming 2 sats.
- BTC→sats display is rounded to an integer satoshi value.
- When a sale fee is unambiguously denominated in BTC/sats it is treated as an additional BTC outflow. Fiat fee value remains separate so stack, net proceeds and FIFO use the same actual BTC outflow.
- This explicit BTC-fee handling applies to relevant sale paths for Kraken Ledger, Binance Trade, CoinTracking/Pocket and Wavespace; ambiguous generic fees are still not blindly treated as extra BTC outflow.

#### Wavespace
- BTC card/sale fees are deducted from the stack in addition to the main BTC amount. Example: 100,000 sats card payment + 371 sats fee = 100,371 sats BTC outflow.
- `payWaveLowValuePurchase`, `POSPurchase`, `card purchase` and `card payment` import as **Expense**.
- Valued Wavespace expenses continue to use sale-style reconciliation `BTC × price − fee = fiat expense` while remaining typed as **Expense** in the ledger.
- `ATMWithdrawal ... Card Authorization` remains a sale/cash withdrawal; normal `CURRENCY_SWAP` BTC→fiat remains a **Sale**.
- Card hints can still be taken from an associated `APPLICATION_FEE` row; merchant name, card fee and optional source details remain available.

#### Export and tests
- CSV export treats valued expenses like sales for fiat reconciliation and subtracts the stored fee from gross value.
- Coinfinity regressions use the real current schema with BTC in `Amount Crypto` and sats in `Mining Fee Crypto`.
- Added regressions for trailing-zero sats, Lightning/on-chain detection, BTC sale fees and Wavespace card payments as expenses.

### Deutsch

#### Coinfinity

- `Amount Crypto` wird beim aktuellen Coinfinity-Report als BTC-Dezimalwert gelesen. Werte wie `0.00020000 BTC` ergeben exakt 20.000 sats; nachgestellte Nullen einer Sats-Ganzzahl werden nicht mehr abgeschnitten.
- `Mining Fee Crypto` wird als Satoshi-Betrag interpretiert. Leer oder 0 bedeutet Lightning; ein positiver Wert kennzeichnet eine On-Chain-Auszahlung.
- `Amount EUR` bleibt der tatsächlich überwiesene Gesamtbetrag. Service Fee und Mining Fee werden davon abgezogen und nicht ein zweites Mal auf den Zahlbetrag aufgeschlagen.
- Der tatsächlich erhaltene BTC-Betrag aus `Amount Crypto` bleibt unverändert. Für die Kostenbasis wird der effektive Kurs so normalisiert, dass BTC-Wert plus Gebühren exakt wieder `Amount EUR` ergibt.
- Order-ID, Adresse, Transaktions-ID und Lightning-Invoice bleiben optionale Vorschaufelder und landen nicht ungefragt in der Buchungsnotiz.

#### Sats und Gebühren bei Verkäufen

- Die gemeinsame BTC/Sats-Anzeige entfernt keine nachgestellten Nullen mehr aus ganzzahligen Satoshi-Werten. Aus 20.000 sats kann dadurch nicht mehr fälschlich 2 sats werden.
- BTC→Sats wird für die Anzeige auf einen ganzzahligen Satoshi-Wert gerundet.
- Wird eine Verkaufsgebühr eindeutig in BTC/Sats ausgewiesen, zählt sie als zusätzlicher BTC-Abgang. Der Fiat-Gegenwert der Fee bleibt separat erhalten, sodass Stack, Nettoerlös und FIFO dieselbe tatsächlich abgegangene BTC-Menge verwenden.
- Diese eindeutige BTC-Fee-Behandlung gilt für die entsprechenden Verkaufspfade von Kraken Ledger, Binance Trade, CoinTracking/Pocket und Wavespace. Unklare generische Gebühren werden weiterhin nicht blind als zusätzlicher BTC-Abgang interpretiert.

#### Wavespace

- BTC-Karten- und Verkaufsgebühren werden zusätzlich zur eigentlichen BTC-Menge vom Stack abgezogen. Beispiel: 100.000 sats Kartenumsatz + 371 sats Fee = 100.371 sats BTC-Abgang.
- `payWaveLowValuePurchase`, `POSPurchase`, `card purchase` und `card payment` werden als Buchungsart **Ausgabe** importiert.
- Bewertete Wavespace-Ausgaben verwenden für die Kontrollrechnung weiterhin die Verkaufslogik `BTC × Kurs − Fee = Fiat-Ausgabe`, bleiben im Buchungsbuch aber als **Ausgabe** gekennzeichnet.
- `ATMWithdrawal ... Card Authorization` bleibt eine Verkauf-/Bargeldabhebungsbuchung; ein normaler `CURRENCY_SWAP` BTC→Fiat bleibt ebenfalls **Verkauf**.
- Kartenhinweise können weiterhin aus einer zugeordneten `APPLICATION_FEE`-Zeile übernommen werden; Händlername, Kartenfee und optional aktivierbare Quelldaten bleiben erhalten.

#### Export und Tests

- CSV-Export behandelt bewertete Ausgaben beim Fiat-Kontrollbetrag wie Verkäufe und zieht die gespeicherte Fee vom Bruttowert ab.
- Coinfinity-Regressionstests verwenden das reale aktuelle Schema mit BTC in `Amount Crypto` und Sats in `Mining Fee Crypto`.
- Regressionstests decken Sats mit nachgestellten Nullen, Lightning/On-Chain-Erkennung, BTC-Verkaufsfees sowie Wavespace-Kartenzahlungen als Ausgaben ab.

## v0.21.0.2 — 2026-08-10: Mathematical Audit Hotfix

### English

#### Charts and performance
- TWR was fully recalculated: external inflows/outflows split periods at their real booking time and subperiod returns are linked geometrically.
- Purchase and sale fees act as performance costs; a full withdrawal no longer incorrectly creates -100% TWR.
- XIRR/XNPV switched to the standard 365-day convention with whole payment days; ambiguous IRR cases are detected instead of arbitrarily selecting one solution.
- XIRR search range was widened for very short periods so strongly annualized one-/multi-day cases do not unnecessarily return unavailable.
- Maximum drawdown is calculated from the complete analysis series instead of the downsampled long-range display series.
- Long-range downsampling retains the real observation day of each price instead of moving values artificially to bucket end.
- Daily prices and daily FIFO snapshots are consistently treated as end-of-day states.
- Intraday cost basis, realized profit and known BTC are replayed after every individual booking instead of only using final daily state.

#### FIFO, fees and timestamps
- FIFO sorting uses actual UTC instants instead of lexicographic ISO strings.
- New and edited bookings are stored canonically as UTC timestamps; legacy migrations also sort by real instant.
- Historical daily snapshots use real UTC timestamps and a new chart-cache schema so old cached values are rebuilt.
- For partially resolved/oversold sales, the sale fee is proportionally allocated to the unresolved portion of net proceeds as well.
- FIFO sale overviews count BTC amount and match count only within the displayed fiat currency.

#### DCA, P/L and sensors
- “Best/Worst purchase” uses effective cost basis per BTC including purchase fees.
- Personal stacking years start at the first matching purchase and evaluate calendar boundaries in UTC.
- Removed the misleading percentage metric “profit / cumulative purchases”; cumulative purchase spend remains only as a clearly labeled reference amount.
- Average open purchase price and unrealized-profit percentage return unavailable rather than mathematically incorrect zeros when there is no known open cost basis.
- Historical average purchase prices no longer write artificial zero values when there is no known open balance.

#### Tests
- Added numerical golden tests for TWR, full withdrawal, fees, 365-day XIRR, same-day payments, multiple XIRR roots and drawdown.
- Added regressions for UTC FIFO, identical timestamps, daily snapshots, DCA, multi-currency, intraday FIFO and display/analysis separation.

### Deutsch

#### Charts und Performance

- TWR vollständig neu berechnet: externe Zu- und Abflüsse werden an ihrem tatsächlichen Buchungszeitpunkt getrennt und Teilperioden geometrisch verknüpft.
- Kauf- und Verkaufsgebühren wirken als Performancekosten; eine vollständige Auszahlung erzeugt nicht mehr fälschlich −100 % TWR.
- XIRR/XNPV auf die übliche 365-Tage-Konvention mit ganzen Zahlungstagen umgestellt; mehrdeutige IRR-Fälle werden erkannt statt willkürlich auf eine Lösung reduziert.
- XIRR-Suchraum für sehr kurze Zeiträume erweitert, damit stark annualisierte Tages-/Mehrtagesszenarien nicht unnötig als „nicht verfügbar“ enden.
- Maximaler Drawdown wird aus der vollständigen verfügbaren Analyse-Reihe berechnet und nicht mehr aus der für die Anzeige verdichteten Langzeitreihe.
- Langzeit-Downsampling behält den tatsächlichen Beobachtungstag eines Kurses bei; Werte werden nicht mehr künstlich ans Bucket-Ende verschoben.
- Tageskurse und tägliche FIFO-Snapshots werden einheitlich als Tagesendzustände behandelt.
- Intraday-Einstand, realisierter Gewinn und bekannte BTC werden nach jeder einzelnen Buchung neu ausgespielt statt nur mit dem finalen Tageszustand.

#### FIFO, Gebühren und Zeitstempel

- FIFO-Sortierung verwendet echte UTC-Zeitpunkte statt lexikographischer ISO-Strings.
- Neue und bearbeitete Buchungen werden kanonisch als UTC-Zeitstempel gespeichert; Legacy-Migrationen sortieren ebenfalls nach dem realen Zeitpunkt.
- Historische Tages-Snapshots verwenden echte UTC-Zeitpunkte und einen neuen Chart-Cache-Schema-Stand, damit alte Cachewerte neu aufgebaut werden.
- Bei teilweise aufgelösten/überverkauften Verkäufen wird die Verkaufsgebühr proportional auch dem unaufgelösten Anteil des Nettoerlöses zugeordnet.
- FIFO-Verkaufsübersichten zählen BTC-Menge und Match-Anzahl nur innerhalb der angezeigten Fiatwährung.

#### DCA, Gewinn/Verlust und Sensoren

- „Bester/Schlechtester Kauf“ verwendet den effektiven Einstand je BTC inklusive Kaufgebühren.
- Persönliche Sparjahre beginnen beim ersten passenden Kauf und rechnen Kalendergrenzen in UTC.
- Die missverständliche Prozentkennzahl „Gewinn / kumulierte Käufe“ wurde entfernt; kumulierte Kaufaufwendungen werden nur noch als klar bezeichnete Bezugsgröße angezeigt.
- Durchschnittlicher offener Kaufpreis und Buchgewinn-Prozent liefern ohne offenen bekannten Einstand „nicht verfügbar“ statt mathematisch falscher 0-Werte.
- Historische Durchschnittskaufpreise schreiben ohne bekannten offenen Bestand keinen künstlichen Nullwert mehr.

#### Tests

- Numerische Golden-Tests für TWR, vollständige Auszahlung, Gebühren, XIRR-365-Tage, gleiche Zahlungstage, mehrdeutige XIRR-Wurzeln und Drawdown ergänzt.
- Regressionsprüfungen für UTC-FIFO, identische Zeitstempel, Tages-Snapshots, DCA, Multiwährung, Intraday-FIFO und Display-/Analyse-Trennung ergänzt.

## v0.21.0.1 — 2026-08-09: History Hotfix

### English

- Historical BTC daily data is no longer considered complete merely because it starts early enough.
- Gaps are filled through downstream Tor fallback sources while already available local values are preserved.
- Density, gap, start-range and end-range checks prevent incomplete `Max` histories from being accepted as complete.
- Tor Gateway workflow became version-independent and is no longer hard-coded to v0.21.0.0.

### Deutsch

- Historische BTC-Tagesdaten werden nicht mehr allein anhand eines frühen Startdatums als vollständig behandelt.
- Lücken werden über nachgelagerte Tor-Fallback-Quellen gefüllt; bereits vorhandene lokale Werte bleiben erhalten.
- Dichte-, Gap-, Start- und Endbereichsprüfungen verhindern unvollständige „Max“-Historien.
- Tor-Gateway-Workflow ist versionsunabhängig und nicht mehr auf v0.21.0.0 fest verdrahtet.

## v0.21.0.0 — 2026-08-09: Initial Public Release

### English

#### Portfolio, FIFO and analytics
- Bitcoin-only portfolio and stack tracking with multiple portfolios.
- Purchases, sales, fees, notes and per-portfolio FIFO assignment.
- Sale overview with FIFO cost basis, sale proceeds, profit/loss and return.
- Bitcoin price, stack, portfolio value and profit/loss charts with multiple ranges and overlays.
- TWR, XIRR, DCA and drawdown analytics.
- Targets, milestones, halving and Bitcoin network markers.

#### Import and data portability
- CSV import with editable preview and plausibility checks for supported exchanges and brokers.
- Encrypted portable `.bstbackup` backups for purchases/sales, portfolios, targets and history.
- Network, Tor, access-control and encryption settings are not restored from portable backups.

#### Home Assistant and mobile
- Native Home Assistant sidebar panel **Bitcoin Stack**.
- Access through the authenticated Home Assistant user identity.
- Desktop and mobile layouts including the Home Assistant Companion App.
- Paging in booking and sale lists jumps to the top of the respective list.

#### Tor and fail closed
- Dedicated Tor Gateway with nftables default-drop killswitch.
- Public price and history sources exclusively through Tor.
- Local private node targets may be accessed directly inside the private network.
- Automatic Supervisor-internal discovery of the GitHub-installed Tor Gateway plus compatibility with local development installations.
- No public DNS/clearnet fallback when gateway resolution fails.

#### Security
- Argon2id-based password derivation and AES-256-GCM for the protected vault.
- Limited panel/iframe RPC channel and restrictive Content Security Policy.
- Fail-closed network path for public data sources.
- Size limits, access controls and hardened backup/restore boundaries.
- Release metadata, SBOM and reproducible integrity checks in the repository.

#### License
- Public restart under **AGPL-3.0-only**.

### Deutsch

#### Portfolio, FIFO und Auswertungen

- Bitcoin-only Portfolio- und Stack-Tracking mit mehreren Depots.
- Käufe, Verkäufe, Gebühren, Notizen und depotweise FIFO-Zuordnung.
- Verkaufsübersicht mit FIFO-Einstand, Verkaufserlös, Gewinn/Verlust und Rendite.
- Bitcoin-Kurs-, Stack-, Portfoliowert- und Gewinn/Verlust-Charts mit mehreren Zeiträumen und Overlays.
- TWR-, XIRR-, DCA- und Drawdown-Auswertungen.
- Ziele, Milestones, Halving- und Bitcoin-Netzwerk-Markierungen.

#### Import und Datenportabilität

- CSV-Import mit bearbeitbarer Vorschau und Plausibilitätsprüfung für unterstützte Börsen und Broker.
- Verschlüsselte portable `.bstbackup`-Backups für Käufe/Verkäufe, Depots, Ziele und Historie.
- Netzwerk-, Tor-, Zugriffs- und Verschlüsselungseinstellungen werden nicht aus portablen Backups wiederhergestellt.

#### Home Assistant und mobile Nutzung

- Natives Home-Assistant-Seitenleistenpanel **Bitcoin Stack**.
- Zugriff über die authentifizierte Home-Assistant-Benutzeridentität.
- Desktop- und mobile Darstellung einschließlich Home-Assistant-Companion-App.
- Seitenwechsel in Buchungs- und Verkaufslisten springen an den Anfang der jeweiligen Liste.

#### Tor und Fail Closed

- Eigenes Tor Gateway mit nftables-Default-Drop-Killswitch.
- Öffentliche Kurs- und Historienquellen ausschließlich über Tor.
- Lokale private Node-Ziele können direkt im privaten Netzwerk angesprochen werden.
- Automatische Supervisor-interne Erkennung des GitHub-installierten Tor Gateways und Kompatibilität mit lokalen Entwicklungsinstallationen.
- Kein öffentlicher DNS-/Clearnet-Fallback bei Fehlern der Gateway-Auflösung.

#### Sicherheit

- Argon2id-basierte Passwortableitung und AES-256-GCM für den geschützten Tresor.
- Begrenzter Panel-/iframe-RPC-Kanal und restriktive Content Security Policy.
- Fail-closed Netzwerkpfad für öffentliche Datenquellen.
- Größenlimits, Zugriffskontrollen und gehärtete Backup-/Restore-Grenzen.
- Release-Metadaten, SBOM und reproduzierbare Integritätsprüfungen im Repository.

#### Lizenz

- Öffentlicher Neustart unter **AGPL-3.0-only**.
