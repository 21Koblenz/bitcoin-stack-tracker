# Bitcoin Stack Tracker v0.21.0.9 — Sats Sentinel & Adaptive Market Assessment

[English](#english) · [Deutsch](#deutsch)

> **Updated v0.21.0.9 build.** The project intentionally keeps the same semantic version and replaces/extends the artifacts originally published on 2026-08-14.

---

<a id="english"></a>
## English

### New: Sats Sentinel

- Privacy-first watch-only monitoring for Bitcoin addresses, address groups, XPUB/YPUB/ZPUB and descriptors.
- Configurable source: **Automatic, Fulcrum/Electrum, electrs/Electrum, own Mempool, configured public Mempool over Tor**.
- Explicit own-source selections are strictly **fail closed**: source down means Sentinel offline/partial, never a silent public-provider fallback.
- Local/private Electrum/Mempool can run directly over LAN; `.onion` and public endpoints use Tor with remote DNS.
- Electrum scripthash balance/history/UTXO queries for Fulcrum/electrs.
- TLS with normal CA validation or exact **SHA-256 certificate pinning** for self-signed Fulcrum certificates.
- Encrypted device-bound runtime cache; XPUB/descriptor secrets are not stored there.
- Movement journal with sender → direction → recipient, categories, notes, thresholds, paging and configured Mempool explorer links.
- Home Assistant events, persistent notifications, multiple `notify.*` targets, self-hosted ntfy and webhooks.
- Test notifications, simulated inbound/outbound events and live TXID source tests without changing balances/baselines.
- Removing a watch entry also permanently removes that monitor's journal history.
- Status refresh no longer overwrites unsaved form input; save/source-test actions now show immediate success/error feedback.

### New: adaptive market assessment

- Modular public-data-only **0–100 score** with adaptive volatility/reference windows, valuation, drawdown, range/deviation, momentum/RSI and cycle components.
- Configurable weights, thresholds, bottom/top zones and confirmation diagnostics.
- Explicitly **not a buy signal, forecast or investment recommendation**.
- Standard Home Assistant sensor with raw decimal score.
- Causal historical reconstruction with no look-ahead bias.
- Taller history chart with crosshair, score/date axis badges and optional BTC-price overlay.
- BTC overlay has its own right price axis, linear/log mode and adjustable opacity.
- Optional causal **EMA smoothing: Off / 3 / 5 / 7 / 14 / 30**; default EMA 5. Display-only, raw score unchanged.
- **Restore defaults** resets 3-year range, EMA 5, BTC overlay on, 55% opacity and logarithmic price scale.
- Overview chart adds **Bitcoin price + market assessment** and automatically shares the same smoothing setting.
- Overview-score rendering fixed: no forward-filling one daily score through every intraday BTC candle; score samples are aligned directly to the price timeline and the right score axis auto-scales to visible values.

### Live price / history / privacy

- Source-specific price refresh cadence and faster public-price lane while public traffic remains Tor-only.
- Current live quote is appended/replaced in charts instead of waiting for the next daily history write.
- Range changes perform appropriate real source refreshes: exact intraday candles for short windows, incremental daily-history sync for long windows.
- Sentinel source policy stays separate from price-source failover.
- Explorer links remain separate from the Sentinel blockchain source, so Fulcrum/electrs monitoring can still open TXIDs/addresses in a local Mempool UI.

### Compatibility

- Custom Integration: **v0.21.0.9**
- Tor Gateway: **v0.21.0.3** unchanged

### Quality assurance

- **457 tests + 8 subtests passed**
- Python compile and JavaScript syntax checks passed
- Frontend asset/version consistency checked
- Sentinel fail-closed, TLS pinning, journal purge, causal history/smoothing and overview-overlay regressions covered

---

<a id="deutsch"></a>
## Deutsch

### Neu: Sats Sentinel

- Privacy-first Watch-only-Überwachung für Bitcoin-Adressen, Adressgruppen, XPUB/YPUB/ZPUB und Descriptoren.
- Einstellbare Quelle: **Automatisch, Fulcrum/Electrum, electrs/Electrum, eigene Mempool-Instanz, konfigurierte öffentliche Mempool-Instanz über Tor**.
- Explizit ausgewählte eigene Quellen arbeiten strikt **Fail Closed**: Quelle down = Sentinel offline/teilweise, niemals heimlicher Public-Fallback.
- Lokale/private Electrum-/Mempool-Ziele dürfen direkt durchs LAN; `.onion` und öffentliche Ziele laufen über Tor mit Remote-DNS.
- Electrum-Scripthash-Abfragen für Balance/History/UTXOs über Fulcrum/electrs.
- TLS mit normaler CA-Prüfung oder exaktem **SHA-256-Zertifikat-Pinning** für selbstsignierte Fulcrum-Zertifikate.
- Verschlüsselter gerätegebundener Runtime-Cache; XPUB-/Descriptor-Geheimnisse werden dort nicht gespeichert.
- Bewegungsjournal mit Sender → Richtung → Empfänger, Kategorien, Notizen, Schwellen, Pagination und konfigurierten Mempool-Explorer-Links.
- Home-Assistant-Events, Persistent Notifications, mehrere `notify.*`-Ziele, self-hosted ntfy und Webhooks.
- Benachrichtigungstests, simulierte Ein-/Ausgänge und Live-TXID-Quellentests ohne Änderung von Balance/Baseline.
- Das Entfernen eines Watch-Eintrags löscht zusätzlich dessen Journal-Historie dauerhaft.
- Statusrefresh überschreibt keine ungespeicherten Formulareingaben mehr; Speichern/Quellentest zeigen sofort Erfolg oder Fehler.

### Neu: adaptive Markteinschätzung

- Modularer öffentlicher **0–100-Score** mit adaptiven Volatilitäts-/Referenzfenstern, Bewertung, Drawdown, Range/Abweichung, Momentum/RSI und Zykluskomponenten.
- Einstellbare Gewichte, Schwellen, Boden-/Top-Zonen und Bestätigungsdiagnostik.
- Ausdrücklich **kein Kaufsignal, Forecast oder Anlageempfehlung**.
- Standard-Home-Assistant-Sensor mit dezimalem Rohscore.
- Kausale historische Rekonstruktion ohne Look-ahead-Bias.
- Höherer Historienchart mit Fadenkreuz, Score-/Datums-Achsenwerten und optionalem BTC-Preis-Overlay.
- BTC-Overlay mit eigener rechter Preisachse, linear/log und einstellbarer Deckkraft.
- Optionale kausale **EMA-Glättung: Aus / 3 / 5 / 7 / 14 / 30**; Standard EMA 5. Rein visuell, Rohscore unverändert.
- **Standard wiederherstellen** setzt 3 Jahre, EMA 5, BTC-Overlay an, 55 % Deckkraft und logarithmische Preisachse.
- Startseitenchart ergänzt **Bitcoin-Kurs + Markteinschätzung** und übernimmt automatisch dieselbe Glättung.
- Startseiten-Score korrigiert: ein Tagesscore wird nicht mehr in jedes Intraday-Kursintervall vorwärts aufgefüllt; Score-Stützpunkte werden direkt auf die Kurszeitachse gelegt und die rechte Scoreachse skaliert automatisch auf die sichtbaren Werte.

### Live-Kurs / Historie / Datenschutz

- Quellenabhängige Preisaktualisierung und schnellere Public-Price-Lane bei weiterhin Tor-only geroutetem öffentlichen Verkehr.
- Aktueller Live-Kurs wird im Chart ergänzt/ersetzt, ohne auf den nächsten täglichen Historieneintrag zu warten.
- Zeitraumwechsel führen passende echte Quellenupdates aus: exakte Intraday-Candles für kurze und inkrementelle Tageshistorie für lange Zeiträume.
- Sentinel-Quellenregeln bleiben strikt von Preisquellen-Failover getrennt.
- Explorer-Links bleiben von der Sentinel-Blockchainquelle getrennt: Fulcrum/electrs kann überwachen, während TXIDs/Adressen weiter in der lokalen Mempool-Oberfläche geöffnet werden.

### Kompatibilität

- Custom Integration: **v0.21.0.9**
- Tor Gateway: **v0.21.0.3** unverändert

### Qualitätssicherung

- **457 Tests + 8 Subtests bestanden**
- Python-Compile und JavaScript-Syntaxprüfungen bestanden
- Frontend-Asset-/Versionskonsistenz geprüft
- Sentinel Fail-Closed, TLS-Pinning, Journal-Löschung, kausale Historie/Glättung und Startseiten-Overlay durch Regressionstests abgedeckt

---

Full details / Vollständige Details: [`CHANGELOG.md`](CHANGELOG.md) · [`RELEASE-NOTES.md`](RELEASE-NOTES.md)
