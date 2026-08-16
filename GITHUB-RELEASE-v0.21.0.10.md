# Bitcoin Stack Tracker v0.21.0.10 — Sats Sentinel & Adaptive Market Assessment

[English](#english) · [Deutsch](#deutsch)

---

<a id="english"></a>
## English

### Sats Sentinel

- Privacy-first 24/7 watch-only monitoring for Bitcoin addresses, address groups, XPUB/YPUB/ZPUB and descriptors.
- Query source can be selected explicitly: **Automatic, Fulcrum/Electrum, electrs/Electrum, own Mempool, configured public Mempool over Tor**.
- Explicit own-source selection is strictly **fail closed**: source down means Sentinel offline/partial, never silent fallback to a public provider.
- Local/private endpoints can run directly over LAN; `.onion` and public endpoints use Tor with remote DNS.
- Fulcrum/electrs use direct Electrum scripthash balance/history/UTXO calls.
- TLS supports normal CA validation and exact **SHA-256 certificate pinning** for self-signed Fulcrum certificates.
- Encrypted device-bound runtime cache; XPUB/descriptor secrets stay out of runtime state.
- Movement journal with sender → direction → recipient, categories, notes, thresholds, paging/page size, counterparties and configured Mempool address/TXID links.
- Home Assistant events, persistent notifications, multiple `notify.*`, self-hosted ntfy and webhooks with discreet/normal/detailed payload levels.
- Notification test, simulated in/out tests and live arbitrary-TXID source test without changing balances/baselines.
- Removing a watch entry permanently removes that monitor's encrypted journal history as well.
- Status-only refresh no longer overwrites unsaved form input; save and source-test actions provide immediate visible feedback.

### Adaptive market assessment

- Modular public-data-only **0–100 score** with adaptive volatility/reference windows and configurable valuation, drawdown, price-position/deviation, momentum/RSI, cycle and turning-point components.
- Includes Mayer Multiple, ATH drawdown, 200-day distance, power-law ratio, bottom/top zones and confirmation diagnostics.
- Explicitly **not a buy signal, forecast or investment recommendation**.
- Standard Home Assistant sensor with decimal raw score.
- Causal historical reconstruction with no look-ahead bias.
- Taller historical chart with crosshair, date/score axis badges and optional BTC-price overlay.
- BTC overlay has its own right price axis, linear/log mode and adjustable opacity.
- Optional causal **EMA smoothing: Off / 3 / 5 / 7 / 14 / 30**, default EMA 5. Display-only; raw score and HA sensor remain unchanged.
- **Restore defaults** resets the market-history display settings.
- Overview chart adds **Bitcoin price + market assessment** and automatically uses the same smoothing setting.
- Flat overview line fixed: daily/current score samples are aligned causally to the BTC timeline instead of forward-filled through every intraday candle; the overview score axis auto-scales to visible values.

### Live price, history and privacy

- Source-specific price refresh cadence and faster public-price lane while public traffic remains Tor-only.
- Current live quote is appended/replaced in charts instead of waiting for the next daily history write.
- Range changes perform appropriate real source refreshes: exact intraday candles for short windows, incremental daily-history sync for long windows.
- Sentinel source policy remains separate from price-source failover.
- Explorer links remain separate from the Sentinel blockchain source, so Fulcrum/electrs monitoring can still open TXIDs/addresses in a local Mempool UI.

### Compatibility & QA

- Custom Integration: **v0.21.0.10**
- Tor Gateway: **v0.21.0.3** unchanged
- **457 tests + 8 subtests passed**
- Python compile, JavaScript syntax, JSON/YAML, frontend asset/version consistency and release-integrity checks passed

---

<a id="deutsch"></a>
## Deutsch

### Sats Sentinel

- Privacy-first 24/7-Watch-only-Überwachung für Bitcoin-Adressen, Adressgruppen, XPUB/YPUB/ZPUB und Descriptoren.
- Abfragequelle explizit wählbar: **Automatisch, Fulcrum/Electrum, electrs/Electrum, eigene Mempool-Instanz, konfigurierte öffentliche Mempool-Instanz über Tor**.
- Explizit ausgewählte eigene Quellen arbeiten strikt **Fail Closed**: Quelle down = Sentinel offline/teilweise, niemals stiller Public-Fallback.
- Lokale/private Ziele dürfen direkt über LAN laufen; `.onion` und öffentliche Ziele über Tor mit Remote-DNS.
- Fulcrum/electrs werden direkt per Electrum-Scripthash für Balance/History/UTXOs abgefragt.
- TLS mit normaler CA-Prüfung oder exaktem **SHA-256-Zertifikat-Pinning** für selbstsignierte Fulcrum-Zertifikate.
- Verschlüsselter gerätegebundener Runtime-Cache; XPUB-/Descriptor-Geheimnisse bleiben außerhalb des Runtime-Zustands.
- Bewegungsjournal mit Sender → Richtung → Empfänger, Kategorien, Notizen, Schwellen, Pagination/Seitengröße, Gegenadressen und konfigurierten Mempool-Links für Adresse/TXID.
- Home-Assistant-Events, Persistent Notifications, mehrere `notify.*`, self-hosted ntfy und Webhooks mit diskreter/normaler/detaillierter Payload-Stufe.
- Benachrichtigungstest, simulierte Ein-/Ausgänge und Live-TXID-Quellentest ohne Veränderung von Balance/Baseline.
- Entfernen eines Watch-Eintrags löscht dessen verschlüsselte Journal-Historie dauerhaft mit.
- Reiner Statusrefresh überschreibt keine ungespeicherten Formulareingaben mehr; Speichern und Quellentest zeigen sofort sichtbares Feedback.

### Adaptive Markteinschätzung

- Modularer öffentlicher **0–100-Score** mit adaptiven Volatilitäts-/Referenzfenstern und einstellbaren Bewertungs-, Drawdown-, Preispositions-/Abweichungs-, Momentum-/RSI-, Zyklus- und Wendepunktkomponenten.
- Mayer Multiple, ATH-Drawdown, 200-Tage-Abstand, Power-Law-Verhältnis, Boden-/Top-Zonen und Bestätigungsdiagnostik.
- Ausdrücklich **kein Kaufsignal, Forecast oder Anlageempfehlung**.
- Standard-HA-Sensor mit dezimalem Rohscore.
- Kausale historische Rekonstruktion ohne Look-ahead-Bias.
- Höherer Historienchart mit Fadenkreuz, Datum-/Score-Achsenwerten und optionalem BTC-Preis-Overlay.
- BTC-Overlay mit eigener rechter Preisachse, linear/log und einstellbarer Deckkraft.
- Optionale kausale **EMA-Glättung: Aus / 3 / 5 / 7 / 14 / 30**, Standard EMA 5. Rein visuell; Rohscore und HA-Sensor bleiben unverändert.
- **Standard wiederherstellen** setzt die Darstellungsoptionen des Markthistorien-Charts zurück.
- Startseitenchart ergänzt **Bitcoin-Kurs + Markteinschätzung** und übernimmt automatisch dieselbe Glättung.
- Seitwärtslinie behoben: Tages-/Live-Score-Stützpunkte werden kausal an die BTC-Zeitachse gelegt statt durch jedes Intraday-Intervall vorwärts aufgefüllt; die Scoreachse der Startseite skaliert auf die sichtbaren Werte.

### Live-Kurs, Historie und Datenschutz

- Quellenabhängige Preisaktualisierung und schnellere Public-Price-Lane bei weiterhin Tor-only geroutetem öffentlichen Verkehr.
- Aktueller Live-Kurs wird in Charts ergänzt/ersetzt, ohne auf den nächsten täglichen Historieneintrag zu warten.
- Zeitraumwechsel führen passende echte Quellenupdates aus: exakte Intraday-Candles für kurze und inkrementelle Tageshistorie für lange Zeiträume.
- Sentinel-Quellenregeln bleiben strikt von Preisquellen-Failover getrennt.
- Explorer-Links bleiben von der Sentinel-Blockchainquelle getrennt: Fulcrum/electrs kann überwachen, während TXIDs/Adressen weiter in der lokalen Mempool-Oberfläche geöffnet werden.

### Kompatibilität & QA

- Custom Integration: **v0.21.0.10**
- Tor Gateway: **v0.21.0.3** unverändert
- **457 Tests + 8 Subtests bestanden**
- Python-Compile, JavaScript-Syntax, JSON/YAML, Frontend-Asset-/Versionskonsistenz und Release-Integritätsprüfung bestanden

---

Full details / Vollständige Details: [`CHANGELOG.md`](CHANGELOG.md) · [`RELEASE-NOTES.md`](RELEASE-NOTES.md)
