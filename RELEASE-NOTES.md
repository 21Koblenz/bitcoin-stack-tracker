# Bitcoin Stack Tracker v0.21.0.13 — Sats Sentinel Accuracy, QR & Home Assistant Performance

## English

v0.21.0.13 consolidates the post-v0.21.0.12 RC development line through RC20 and adds a final stability/performance pass for Home Assistant. The release focuses on correct HD-wallet discovery, locked-vault Sats Sentinel management, QR scanning, stale frontend state, bounded background work and substantially cheaper market-assessment updates.

### Sats Sentinel / HD wallets
- **Fixed false `0 BTC · Receive 2 · Change 2 · 0 UTXO` results for real XPUB wallets.** Existing small-gap configurations now get a 20-address discovery bootstrap before Sentinel concludes that a branch is unused. New HD monitors default to Receive 20 / Change 20.
- Plain `xpub` is treated as script-type ambiguous. Auto mode checks historical activity across native SegWit, nested SegWit, Taproot and legacy candidates instead of assuming legacy from the serialization prefix.
- XPUB auto-detection is bounded to one script family at a time, at most 40 history calls per family for the 20+20 bootstrap, with cooperative yields between batches.
- Existing HD discovery semantics remain intact: every historically used Receive/Change address stays active, followed by the configured consecutive-unused reserve on each branch.
- The RC line adds Taproot single-key support (`tr()` / P2TR), standard Receive/Change multipath descriptor handling and explicit XPUB address-format selection when Auto is not desired.
- Fulcrum/electrs polling was reduced from broad rescans to bounded batches: lightweight status and baseline work use 20-address batches; background reconciliation is limited to small slices and normally runs only once per hour.
- Normal Sentinel polling no longer rewrites the encrypted runtime store every cycle; unchanged runtime state is coalesced to a bounded persistence cadence while activity/configuration changes still persist immediately.
- Sats Sentinel's activity journal is now hard-bounded to the newest **5,000** entries to prevent unbounded resident-memory/storage growth.

### Locked-vault watch-only monitoring
- The post-v0.21.0.12 RC line adds a separate device-bound AES-256-GCM Sats Sentinel runtime vault containing the **public watch-only material** required for 24/7 monitoring while the main portfolio vault is locked: address/XPUB/descriptor, derived addresses and connection metadata.
- This runtime vault never stores seeds, private keys, xprv/private extended keys, signing keys or other spend-capable material.
- The locked frontend now hides the entire Sentinel wallet/address/balance/source card by default and does not request its management payload. An unlocked per-browser/per-device option can explicitly show it. Monitoring, journal updates and configured alerts continue regardless of that display preference.
- If the local display option is enabled, existing Sats Sentinel targets can still be edited or removed while the portfolio vault is locked; changes are reconciled back to the password-protected portfolio vault after unlock.
- Editing labels, alerts or source settings preserves already discovered HD coverage instead of collapsing a wallet back to the seed gap.
- Sentinel endpoint/source settings are persisted independently from the larger runtime cache so a runtime-cache migration cannot silently erase the selected Fulcrum/electrs endpoint.

### Home Assistant stability and performance
- **Fixed the repeated vault timer exception** `AttributeError: 'datetime.datetime' object has no attribute 'data'`. The expiry worker now receives only the bound `HomeAssistant` object, and global timers cancel stale registrations before being recreated.
- The market-assessment model no longer reconstructs years of historical scores on Home Assistant's event loop or on every live-price change.
- Added a shared executor-backed current-assessment cache. The **current** score is recalculated at most once every five minutes from the newest available live quote; dashboard, endpoint, HA sensor and multiple panel clients share that result.
- Added a content-addressed **persistent historical score cache** in Home Assistant storage. The expensive causal daily score series survives restarts and is reused for all chart ranges until the model version, currency, model parameters or stored historical daily price data actually changes. Intraday live quotes do not invalidate the history cache. After automatic or manual durable-history synchronization, an unchanged signature remains a persistent hit; a newly added or corrected daily value rebuilds the causal score generation once in the executor and immediately persists the new cache generation.
- Fixed the `Bitcoin price + market assessment` overlay race that could show only the price chart while an older history request was still in flight. Range requests are deduplicated independently and stale responses cannot block the currently selected range.
- Short chart ranges now combine the causal daily series with **real persisted intraday assessment snapshots** from the already scheduled five-minute current-score run. Overview cadence is **1 hour for 1 day, 6 hours for week-to-date/1 week, and 12 hours for month-to-date/30 days**. There is no interpolation and no additional score calculation; the lightweight public snapshot store retains up to 45 days and is resampled only for display. A small causal pre-roll remains as the left-edge anchor when no older intraday observation exists.
- The HA market-assessment sensor writes state only when a new assessment exists and exposes a compact automation-oriented attribute set rather than the full nested model result.
- Frontend assessment polling is 5 minutes. Live-price UI polling remains 30 seconds, but quote ticks no longer force an early score calculation; the next five-minute assessment uses the newest quote. Wallet status polling is 30 seconds and network status 60 seconds.
- Tor status has a shared 30-second Core cache. The halving ticker no longer forces a fresh Tor/network check every minute.
- Wallet manager startup defensively cancels an older timer before registering a new one; assessment background tasks are cancelled on entity/integration unload.

### QR scanner and frontend state
- **Fixed Home Assistant Companion QR scanning.** The bridge now follows the Home Assistant external-bus contract: capability is checked with `config/get`, scanner startup is acknowledged separately, and `bar_code/scan_result` / abort events are handled by message type rather than by reusing the original scan command ID.
- The QR handshake timeout is increased to 3 seconds and sends an immediate probing state, removing the previous parent/iframe timeout race. Browser-camera fallback remains available.
- Wallet cards remain collapsed by default on desktop and mobile. The collapse storage key is bumped to v5 so stale production-browser state is reset once.
- The public frontend build stays at `0.21.0.13`; an internal cache revision (`r=4`) forces browsers/Companion to discard earlier v0.21.0.13 intermediate assets while stable filenames remain in place.

### Privacy and security
- Native panel RPC remains Home-Assistant-authenticated and owner checks protect Sats Sentinel management paths.
- Sensitive HTTP responses use `Cache-Control: no-store, private`; the native UI CSP remains fail-closed (`default-src 'none'`, `connect-src 'none'`).
- Public network routes remain fail closed through the configured Tor policy; direct Electrum is restricted to private/local targets, while public/onion routing follows the existing Tor/TLS policy.
- Notification URLs reject embedded credentials; normal public notification endpoints require HTTPS.
- No `eval`, `exec`, `os.system` or `popen` execution paths were found in the release audit.
- The v0.21.0.12 privacy wording has been corrected: public watch-only XPUB/descriptor material may be present inside the separate device-bound encrypted Sentinel runtime vault for locked monitoring. The locked UI does not expose it by default. **No spend-capable secret is stored there.**

### Validation
The uploaded RC20 custom-component archive does not contain the repository's full upstream test suite, so the earlier v0.21.0.12 result of 502 tests + 8 subtests is **not** claimed as rerun for this build. For v0.21.0.13, the release candidate passed:
- **68/68** static release/security checks
- **7/7** functional/performance checks
- **6/6** current-market-runtime behavior checks
- **12/12** persistent historical-market-cache / overlay / daily-warm checks
- **11/11** intraday snapshot-store checks
- **7/7** short-overlay sampling checks
- Python parsing for all 28 Python modules
- JavaScript syntax checks for `panel.js`, `app.js` and `performance-math.js`
- JSON parsing/version consistency checks

Measured on the included benchmark harness with 5,000 synthetic daily history points:
- one uncached market-assessment calculation: **~0.83 s average**, **~6.00 MiB peak temporary allocation**
- compact HA sensor attributes: **885 bytes vs 7,988 bytes** in the old full-dump representation (**~88.9% reduction**)
- XPUB regression case: saved Gap 2 + first used Receive address at index 5 correctly resolves and discovers Receive indexes 0–7
- official BIP84 native-SegWit and BIP86 Taproot account-0/receive-0 vectors derive exactly

Custom Integration: **v0.21.0.13**  
Tor Gateway: **v0.21.0.3 unchanged**

### Upgrade requirement
After replacing the integration files, perform a **full Home Assistant Core restart**. Do not rely only on reloading the integration: an older Python callback/panel module can remain alive in the running process. Then hard-reload the browser frontend; in the Companion App, fully close/reopen the app if the old panel is still visible.

---

## Deutsch

v0.21.0.13 bündelt die Entwicklung nach v0.21.0.12 bis einschließlich RC20 und ergänzt einen abschließenden Stabilitäts-/Performance-Pass für Home Assistant. Im Mittelpunkt stehen korrekte HD-Wallet-Erkennung, Sats-Sentinel-Verwaltung bei gesperrtem Tresor, QR-Scanning, veralteter Frontend-Zustand, begrenzte Hintergrundarbeit und deutlich günstigere Markteinschätzungs-Updates.

### Sats Sentinel / HD-Wallets
- **Fehlerhafte Ergebnisse wie `0 BTC · Receive 2 · Change 2 · 0 UTXO` bei real belegten XPUB-Wallets behoben.** Bestehende Konfigurationen mit kleinem Gap erhalten vor der Entscheidung „unbenutzt“ jetzt einen Discovery-Bootstrap über 20 Adressen. Neue HD-Watches starten standardmäßig mit Receive 20 / Change 20.
- Ein nackter `xpub` gilt als Script-Typ-mehrdeutig. Auto prüft historische Aktivität für Native SegWit, Nested SegWit, Taproot und Legacy, statt aus dem xpub-Präfix automatisch Legacy abzuleiten.
- Die XPUB-Autoerkennung arbeitet begrenzt: jeweils eine Script-Familie, maximal 40 History-Abfragen pro Familie für den 20+20-Bootstrap, mit kooperativem Yield zwischen den Batches.
- Die bestehende HD-Gap-Logik bleibt erhalten: Jede historisch benutzte Receive-/Change-Adresse bleibt aktiv; dahinter folgt pro Branch die eingestellte Zahl aufeinanderfolgender unbenutzter Reserveadressen.
- Die RC-Linie ergänzt Taproot-Single-Key-Unterstützung (`tr()` / P2TR), Standard-Receive/Change-Multipath-Descriptoren und eine explizite XPUB-Adressformatwahl, falls Auto nicht gewünscht ist.
- Fulcrum/electrs-Polling wurde von breiten Rescans auf begrenzte Batches umgestellt: Status/Baseline verwenden 20er-Batches; Hintergrund-Reconcile verarbeitet kleine Teilmengen und läuft normalerweise nur einmal pro Stunde.
- Normales Sentinel-Polling schreibt den verschlüsselten Runtime-Store nicht mehr in jedem Zyklus neu; unveränderte Runtime-Daten werden zeitlich zusammengefasst, während Aktivität und Konfigurationsänderungen weiterhin sofort persistiert werden.
- Das Sats-Sentinel-Aktivitätsjournal ist jetzt hart auf die neuesten **5.000** Einträge begrenzt, damit RAM-/Storage-Wachstum nicht unbegrenzt fortschreitet.

### Watch-only-Verwaltung bei gesperrtem Tresor
- Die RC-Linie nach v0.21.0.12 ergänzt einen separaten gerätegebundenen AES-256-GCM-Sats-Sentinel-Runtime-Tresor mit dem für die 24/7-Überwachung bei gesperrtem Haupttresor nötigen **öffentlichen Watch-only-Material**: Adresse/XPUB/Descriptor, abgeleitete Adressen und Verbindungsmetadaten.
- Die gesperrte UI blendet die komplette Sentinel-Wallet-/Adress-/Bestands-/Quellenkarte standardmäßig aus und fordert deren Management-Payload nicht an. Eine lokale Anzeigeoption pro Browser/Gerät kann die Watch-only-Karte im entsperrten Sentinel-Bereich bewusst freigeben; Überwachung, Journal und konfigurierte Alarme laufen unabhängig von dieser Anzeigeoption weiter.
- Dieser Runtime-Tresor speichert niemals Seeds, Private Keys, xprv/private Extended Keys, Signierschlüssel oder anderes Material, mit dem Bitcoin ausgegeben werden können.
- Bestehende Sats-Sentinel-Ziele können bei gesperrtem Portfolio-Tresor bearbeitet oder gelöscht werden; nach dem Entsperren werden Änderungen wieder mit dem passwortgeschützten Portfolio-Tresor abgeglichen.
- Änderungen an Namen, Alarmen oder Quellen behalten bereits gefundene HD-Abdeckung bei und lassen die Wallet nicht auf den anfänglichen Seed-Gap zurückfallen.
- Sentinel-Endpoint-/Quelleneinstellungen werden unabhängig vom größeren Runtime-Cache persistiert, damit eine Cache-Migration nicht stillschweigend den gewählten Fulcrum-/electrs-Endpunkt löscht.

### Home-Assistant-Stabilität und Performance
- **Wiederkehrende Vault-Timer-Exception behoben:** `AttributeError: 'datetime.datetime' object has no attribute 'data'`. Der Expiry-Worker bekommt nur noch das gebundene `HomeAssistant`-Objekt; globale Timer entfernen alte Registrierungen vor dem Neuaufbau.
- Das Markteinschätzungsmodell rekonstruiert nicht mehr bei jeder Live-Kursänderung jahrelange historische Scores im Home-Assistant-Event-Loop.
- Neuer gemeinsamer Executor-Cache für die aktuelle Markteinschätzung. Der **aktuelle** Score wird höchstens alle fünf Minuten mit dem dann neuesten Live-Kurs berechnet; Dashboard, Endpoint, HA-Sensor und mehrere Panel-Clients teilen dieses Ergebnis.
- Neuer in Home Assistant persistierter, inhaltsadressierter **History-Score-Cache**. Die teure kausale Tages-Score-Serie überlebt Neustarts und wird für alle Chart-Zeiträume wiederverwendet, bis sich Modellversion, Währung, Modellparameter oder gespeicherte historische Tageskurse wirklich ändern. Intraday-Livekurse invalidieren die Historie nicht. Nach automatischer/manueller Tageshistorien-Synchronisation bleibt eine unveränderte Signatur ein Cache-Hit; ein neuer oder korrigierter Tageswert baut die kausale Score-Generation einmal im Executor neu und persistiert sie sofort.
- Race im Overlay `Bitcoin-Kurs + Markteinschätzung` behoben, bei dem während eines alten laufenden History-Requests nur der Kurschart sichtbar bleiben konnte. Requests werden pro Zeitraum dedupliziert; veraltete Antworten blockieren den aktuell gewählten Zeitraum nicht mehr.
- Kurze Chart-Zeiträume kombinieren die kausale Tages-Serie jetzt mit **echten persistenten Intraday-Snapshots** aus der ohnehin höchstens alle fünf Minuten laufenden Current-Score-Berechnung. Die Übersicht nutzt **1 Stunde für Heute, 6 Stunden für Seit Wochenbeginn/1 Woche und 12 Stunden für Seit Monatsbeginn/30 Tage**. Es gibt weder Interpolation noch zusätzliche Score-Berechnungen; der kleine öffentliche Snapshot-Store hält bis zu 45 Tage und wird nur für die Anzeige verdichtet. Ein kleiner kausaler Vorlauf bleibt als linker Anker erhalten, solange noch keine ältere Intraday-Beobachtung vorhanden ist.
- Der HA-Markteinschätzungs-Sensor schreibt nur noch bei einer neuen Berechnung einen State und liefert einen kompakten automationstauglichen Attributsatz statt des vollständigen verschachtelten Modellergebnisses.
- Die Markteinschätzung läuft im 5-Minuten-Takt. Der Live-Kurs wird im UI weiterhin alle 30 Sekunden aktualisiert, erzwingt aber keine vorzeitige Score-Berechnung; der nächste 5-Minuten-Lauf verwendet den neuesten Kurs. Wallet-Status: 30 Sekunden, Netzwerkstatus: 60 Sekunden.
- Tor-Status besitzt einen gemeinsamen 30-Sekunden-Core-Cache. Der Halving-Ticker erzwingt nicht mehr jede Minute einen frischen Tor-/Netzwerkcheck.
- Beim Start entfernt der Wallet-Manager defensiv einen älteren Timer; Markteinschätzungs-Tasks werden beim Entfernen der Entity bzw. Entladen der Integration abgebrochen.

### QR-Scanner und Frontend-Zustand
- **Home-Assistant-Companion-QR-Scanning korrigiert.** Die Bridge folgt jetzt dem External-Bus-Vertrag: Fähigkeit via `config/get`, separater Startstatus und Verarbeitung von `bar_code/scan_result`/Abbruch anhand des Nachrichtentyps statt anhand der ursprünglichen Scan-Command-ID.
- QR-Handshake-Timeout auf 3 Sekunden erhöht und sofortiger „probing“-Status ergänzt; damit entfällt das bisherige Parent/Iframe-Timeout-Rennen. Browser-Kamera-Fallback bleibt erhalten.
- Wallet-Karten sind auf Desktop und Mobil weiterhin standardmäßig eingeklappt. Der Collapse-Storage-Key wurde auf v5 erhöht, damit ein veralteter Zustand im Produktiv-Browser einmalig verworfen wird.
- Der öffentliche Frontend-Build bleibt `0.21.0.13`; eine interne Cache-Revision (`r=4`) zwingt Browser/Companion dazu, frühere v0.21.0.13-Zwischenassets zu verwerfen, während die stabilen Dateinamen erhalten bleiben.

### Datenschutz und Sicherheit
- Native Panel-RPC bleibt über Home Assistant authentifiziert; Owner-Prüfungen schützen die Sats-Sentinel-Verwaltung.
- Sensible HTTP-Antworten verwenden `Cache-Control: no-store, private`; die native UI-CSP bleibt fail closed (`default-src 'none'`, `connect-src 'none'`).
- Öffentliche Netzwerkpfade bleiben über die konfigurierte Tor-Policy fail closed; direkte Electrum-Verbindungen sind auf private/lokale Ziele beschränkt, öffentliche/Onion-Ziele folgen der bestehenden Tor-/TLS-Policy.
- Notification-URLs lehnen eingebettete Zugangsdaten ab; normale öffentliche Notification-Endpunkte benötigen HTTPS.
- Im Release-Audit wurden keine `eval`-, `exec`-, `os.system`- oder `popen`-Ausführungspfade gefunden.
- Die Datenschutzbeschreibung aus v0.21.0.12 wurde korrigiert: Öffentliches Watch-only-XPUB-/Descriptor-Material kann für Locked-Verwaltung im separat gerätegebunden verschlüsselten Sentinel-Runtime-Tresor liegen. **Spend-fähige Geheimnisse werden dort nicht gespeichert.**

### Prüfung
Das hochgeladene RC20-Custom-Component-Archiv enthält nicht die vollständige Upstream-Testsuite des Repositories. Deshalb wird das frühere Ergebnis „502 Tests + 8 Subtests“ für diesen Build **nicht** als erneut ausgeführt ausgegeben. Für v0.21.0.13 wurden bestanden:
- **68/68** statische Release-/Security-Checks
- **7/7** Funktions-/Performance-Checks
- **6/6** Current-Market-Runtime-Verhaltenstests
- **12/12** persistente History-Market-Cache-/Overlay-/Daily-Warm-Checks
- **11/11** Intraday-Snapshot-Store-Checks
- **7/7** Kurzzeit-Overlay-Sampling-Checks
- Python-Parsing für alle 28 Python-Module
- JavaScript-Syntax für `panel.js`, `app.js` und `performance-math.js`
- JSON-/Versionskonsistenzprüfungen

Messung mit dem beigefügten Benchmark-Harness und 5.000 synthetischen Tagespunkten:
- eine ungecachte Markteinschätzungsberechnung: **~0,83 s im Mittel**, **~6,00 MiB temporäre Peak-Allokation**
- kompakte HA-Sensorattribute: **885 Bytes statt 7.988 Bytes** beim alten Full-Dump (**~88,9 % weniger**)
- XPUB-Regression: gespeicherter Gap 2 + erste benutzte Receive-Adresse auf Index 5 wird korrekt erkannt und aktiviert Receive 0–7

Custom Integration: **v0.21.0.13**  
Tor Gateway: **v0.21.0.3 unverändert**

### Wichtig beim Update
Nach dem Kopieren der Integrationsdateien **Home Assistant Core vollständig neu starten**. Ein bloßes Reload der Integration reicht für diesen Fix nicht zuverlässig, weil ein alter Python-Callback bzw. ein altes Panel-Modul im laufenden Prozess weiterleben kann. Danach Browser hart neu laden; in der Companion App die App vollständig schließen/neu öffnen, falls dort noch das alte Panel sichtbar ist.
