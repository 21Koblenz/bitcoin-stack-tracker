# Bitcoin Stack Tracker v0.21.0.13 — Sats Sentinel Accuracy, Privacy & HA Performance

## Deutsch

v0.21.0.13 bündelt die RC-Entwicklung nach v0.21.0.12 bis RC20 und enthält den finalen Stabilitäts-, Privacy- und Performance-Pass für Home Assistant.

### Highlights
- **XPUB-False-Zero behoben:** Kleine bestehende Gap-Konfigurationen erhalten einen 20-Adressen-Discovery-Bootstrap; neue HD-Watches starten mit Receive 20 / Change 20. Ein nacktes `xpub` wird anhand echter Historie als Native SegWit, Nested SegWit, Taproot oder Legacy erkannt.
- **Locked Sentinel standardmäßig komplett verborgen:** Bei gesperrtem Haupttresor werden Wallets, Adressen, Bestand und Abfragequelle nicht gerendert und vom Frontend auch nicht periodisch abgefragt. Im entsperrten Sentinel-Bereich kann die Anzeige lokal pro Browser/Gerät ausdrücklich aktiviert werden. **Core-Überwachung und alle aktivierten Benachrichtigungen laufen unabhängig davon weiter.**
- **Markteinschätzungs-Sensor auf 5 Minuten begrenzt:** `sensor.bitcoin_bitcoin_stack_markteinschatzung`, API und Dashboard teilen sich dieselbe rechenintensive Berechnung. Der Live-Kurs kann weiter im 30-Sekunden-Takt erscheinen, erzwingt aber keine Score-Neuberechnung. Spätestens beim nächsten 5-Minuten-Lauf wird der dann neueste Kurs verwendet.
- **Persistenter Historical-Score-Cache:** Die kausale Tages-Score-Serie überlebt Home-Assistant-Neustarts und wird nur bei geänderter Modellversion, Währung, Modellparametern oder gespeicherten historischen Tageskursen neu aufgebaut. Intraday-Live-Ticks lassen sie unangetastet.
- **Neuer/korrigierter Tageswert wird sauber übernommen:** Nach automatischer oder manueller History-Synchronisation ändert ein neuer bzw. korrigierter gespeicherter Tageskurs die Content-Signatur. Die Serie wird einmal im Executor neu berechnet und die neue Generation sofort persistent gespeichert.
- **Dichtere echte Kurzzeit-Markteinschätzung:** Die ohnehin höchstens alle fünf Minuten berechnete Current-Markteinschätzung wird als kleiner öffentlicher Intraday-Verlauf gespeichert. **Heute = 1 h, Seit Wochenbeginn/1 Woche = 6 h, Seit Monatsbeginn/30 Tage = 12 h.** Keine Interpolation, keine zusätzlichen Modellberechnungen; bis zu 45 Tage echte Intraday-Snapshots bleiben erhalten. Der kausale Vorlauf bleibt als Fallback-Anker bestehen.
- **Overlay-Race behoben:** Ein langsamer Request eines alten Zeitraums kann die aktuelle Ansicht nicht mehr mit nur dem Kurschart zurücklassen.
- **HA-Timer-Crash behoben:** Kein `AttributeError: 'datetime.datetime' object has no attribute 'data'` mehr im Vault-Expiry-Task.
- **Companion-QR repariert:** `bar_code/scan_result` wird anhand des External-Bus-Nachrichtentyps verarbeitet; der 3-Sekunden-Handshake beseitigt das Parent/Iframe-Timeout-Rennen.
- **Weniger Dauerlast:** Executor-/Request-Coalescing, kompaktere Sensorattribute, begrenzte Electrum/Fulcrum-Batches, Tor-Status-Cache, weniger erzwungene Polls und ein auf 5.000 Einträge begrenztes Sentinel-Journal.
- **Same-Version-Cache-Bust:** Release bleibt `0.21.0.13`, interne Frontend-Revision ist `r=4`, damit frühere v0.21.0.13-Zwischenassets nicht im Browser/Companion hängen bleiben.

### Prüfung
- **68/68** statische Release-/Security-Checks
- **7/7** Funktions-/Performance-Checks
- **6/6** Current-Market-Runtime-Verhaltenstests
- **12/12** persistente Historical-Cache-/Overlay-/Daily-Warm-Checks
- **11/11** Intraday-Snapshot-Store-Checks
- **7/7** Kurzzeit-Overlay-Sampling-Checks
- **111/111 dedizierte lokale Checks insgesamt**
- Python: **28/28** Module parsebar; JavaScript-/JSON-/Versionschecks grün
- 5.000-Tage-Harness: ca. **0,82 s** ungecachte Market-Berechnung, ca. **6,00 MiB** temporäre Peak-Allokation
- Sensorattribute im Harness: **885 B statt 7.988 B** (~**88,9 %** kleiner)
- BIP84- und BIP86-HD-Testvektoren sowie XPUB-Gap-Regression bestanden

> Das hochgeladene RC20-Custom-Component-Archiv enthält nicht die vollständige Repository-Testsuite. Die früheren 502 Tests + 8 Subtests aus v0.21.0.12 werden deshalb für diesen Build **nicht** als erneut ausgeführt ausgegeben.

### Update
1. Den kompletten Ordner `custom_components/bitcoin_stack_tracker/` ersetzen.
2. **Home Assistant Core vollständig neu starten.**
3. Browser hart neu laden bzw. Companion App vollständig schließen und neu öffnen.
4. Beim gesperrten Tresor prüfen: Sentinel-Karte bleibt standardmäßig vollständig verborgen; Benachrichtigungen/Überwachung laufen weiter.
5. `Bitcoin-Kurs + Markteinschätzung` mit **Tag**, **Seit Wochenbeginn** und **1 Woche** prüfen.

Custom Integration: **v0.21.0.13**  
Tor Gateway: **v0.21.0.3 unverändert**

---

## English

v0.21.0.13 consolidates the post-v0.21.0.12 RC line through RC20 and adds the final Home Assistant stability, privacy and performance pass.

### Highlights
- **XPUB false-zero fixed:** existing small-gap configs receive a 20-address discovery bootstrap; new HD watches default to Receive 20 / Change 20. Plain `xpub` Auto mode resolves native SegWit, nested SegWit, Taproot or legacy from actual history.
- **Locked Sentinel hidden by default:** while the main vault is locked, wallet/address/balance/source data is neither rendered nor periodically requested by the frontend. An unlocked per-browser/per-device preference can explicitly show it. **Core monitoring and all enabled alerts continue independently.**
- **Current market score bounded to five minutes:** `sensor.bitcoin_bitcoin_stack_markteinschatzung`, API and dashboard share one expensive calculation. The live price can continue updating every 30 seconds without forcing a new score; the next five-minute calculation uses the newest available quote.
- **Persistent historical-score cache:** the causal daily score series survives Home Assistant restarts and rebuilds only when model version, currency, model settings or stored historical daily prices change. Intraday live ticks do not invalidate it.
- **New/corrected daily values are incorporated:** after automatic/manual durable-history synchronization, a changed stored daily value changes the content signature, triggers one executor rebuild and immediately persists the new generation.
- **Denser real short-range assessment:** the already bounded five-minute current assessment is stored as a lightweight public intraday series. **1 day = 1 h, week-to-date/1 week = 6 h, month-to-date/30 days = 12 h.** No interpolation and no extra model runs; up to 45 days of genuine intraday snapshots are retained. The causal pre-roll remains as a fallback anchor.
- **Overlay race fixed:** a slow request for an old range can no longer leave the current range showing price only.
- **HA timer crash fixed:** no more `AttributeError: 'datetime.datetime' object has no attribute 'data'` from the vault-expiry task.
- **Companion QR fixed:** `bar_code/scan_result` is handled by External Bus message type; a three-second handshake removes the parent/iframe timeout race.
- **Lower background load:** executor/request coalescing, compact sensor attributes, bounded Electrum/Fulcrum batches, shared Tor-status caching, fewer forced polls and a 5,000-row Sentinel journal cap.
- **Same-version cache bust:** the public release stays `0.21.0.13` while internal frontend revision `r=4` invalidates earlier v0.21.0.13 intermediate browser assets.

### Validation
- **68/68** static release/security checks
- **7/7** functional/performance checks
- **6/6** current-market-runtime behavior checks
- **12/12** persistent historical-cache/overlay/daily-warm checks
- **11/11** intraday snapshot-store checks
- **7/7** short-overlay sampling checks
- **111/111 dedicated local checks total**
- Python **28/28** modules parse; JavaScript/JSON/version checks pass
- 5,000-day harness: about **0.82 s** uncached market calculation, about **6.00 MiB** temporary peak allocation
- Sensor attributes: **885 B vs 7,988 B** (~**88.9%** smaller)
- BIP84/BIP86 HD vectors and XPUB gap regression pass

> The uploaded RC20 custom-component archive does not include the repository's complete upstream test suite, so the earlier v0.21.0.12 result of 502 tests + 8 subtests is **not** claimed as rerun for this build.

### Upgrade
1. Replace the complete `custom_components/bitcoin_stack_tracker/` directory.
2. **Fully restart Home Assistant Core.**
3. Hard-reload the browser or fully close/reopen the Companion App.
4. With the vault locked, verify that the Sentinel card is hidden by default while monitoring/notifications keep running.
5. Verify `Price + market assessment` on **1 day**, **week-to-date** and **1 week**.

Custom Integration: **v0.21.0.13**  
Tor Gateway: **v0.21.0.3 unchanged**
