# Bitcoin Stack Tracker v0.21.0.10 — Release Notes

[English](#english) · [Deutsch](#deutsch)

<a id="english"></a>
## English

v0.21.0.10 is the feature release after v0.21.0.9. It introduces **Sats Sentinel** and the adaptive/historical **market assessment** while keeping public network traffic on the existing Tor fail-closed architecture.

### Highlights

- Sats Sentinel watch-only monitoring for addresses, XPUB/YPUB/ZPUB and descriptors.
- Explicit Sentinel source selection: Automatic, Fulcrum/Electrum, electrs/Electrum, own Mempool, or configured public Mempool over Tor.
- Strict fail-closed behavior for explicitly selected sources; no silent provider fallback.
- Fulcrum/electrs Electrum scripthash queries, TLS and SHA-256 pinning for self-signed certificates.
- Encrypted movement journal, sender/direction/recipient view, thresholds/categories/notes, notifications and test modes.
- Removing a watch entry permanently removes its associated journal rows.
- Adaptive 0–100 market assessment with configurable weights, turning-point/bottom/top diagnostics and a decimal HA sensor.
- Causal historical reconstruction without look-ahead bias.
- Historical market chart with BTC-price overlay, crosshair, opacity, linear/log price axis and causal EMA smoothing.
- Overview **Bitcoin price + market assessment** overlay uses the same smoothing and fixes the previous flat-line rendering by aligning causal score samples to the actual BTC timeline.
- Source-specific live-price cadence and real chart-range refreshes while public traffic remains Tor-only.

### Privacy boundary

Sentinel never accepts seeds or private keys. XPUB/descriptors stay in encrypted vault configuration; the device-bound runtime cache contains only concrete derived monitoring material. Explicitly selected own sources never fall back to public providers. Market-assessment data is public market data and stays separated from portfolio privacy state.

### Versions and QA

- Home Assistant custom integration: **v0.21.0.10**
- Tor Gateway: **v0.21.0.3** unchanged
- **457 tests + 8 subtests passed**

<a id="deutsch"></a>
## Deutsch

v0.21.0.10 ist das Feature-Release nach v0.21.0.9. Es ergänzt **Sats Sentinel** und die adaptive/historische **Markteinschätzung**, während öffentliche Netzwerkverbindungen weiter die bestehende Tor-Fail-Closed-Architektur verwenden.

### Highlights

- Sats-Sentinel-Watch-only-Überwachung für Adressen, XPUB/YPUB/ZPUB und Descriptoren.
- Explizite Sentinel-Quellenwahl: Automatisch, Fulcrum/Electrum, electrs/Electrum, eigene Mempool-Instanz oder konfigurierte öffentliche Mempool-Instanz über Tor.
- Striktes Fail Closed bei explizit gewählten Quellen; kein heimlicher Provider-Fallback.
- Fulcrum/electrs per Electrum-Scripthash, TLS und SHA-256-Pinning für selbstsignierte Zertifikate.
- Verschlüsseltes Bewegungsjournal, Sender/Richtung/Empfänger, Schwellen/Kategorien/Notizen, Benachrichtigungen und Testmodi.
- Das Entfernen eines Watch-Eintrags löscht die zugehörigen Journal-Zeilen dauerhaft.
- Adaptive 0–100-Markteinschätzung mit einstellbaren Gewichten, Wendepunkt-/Boden-/Top-Diagnostik und dezimalem HA-Sensor.
- Kausale historische Rekonstruktion ohne Look-ahead-Bias.
- Markt-Historienchart mit BTC-Preis-Overlay, Fadenkreuz, Deckkraft, linear/log Preisachse und kausaler EMA-Glättung.
- Startseiten-Overlay **Bitcoin-Kurs + Markteinschätzung** übernimmt dieselbe Glättung und behebt die frühere Seitwärtslinie durch kausale Ausrichtung der Score-Stützpunkte an der tatsächlichen BTC-Zeitachse.
- Quellenabhängige Live-Kurs-Frequenz und echte Chart-Zeitraum-Refreshes bei weiterhin Tor-only geroutetem öffentlichem Verkehr.

### Privacy-Grenze

Sentinel akzeptiert niemals Seeds oder Private Keys. XPUB/Descriptor bleiben in der verschlüsselten Tresorkonfiguration; der gerätegebundene Runtime-Cache enthält nur konkrete abgeleitete Monitoring-Daten. Explizit gewählte eigene Quellen fallen niemals auf öffentliche Provider zurück. Die Markteinschätzung verarbeitet öffentliche Marktdaten und bleibt von privaten Portfoliodaten getrennt.

### Versionen und QA

- Home-Assistant-Custom-Integration: **v0.21.0.10**
- Tor Gateway: **v0.21.0.3** unverändert
- **457 Tests + 8 Subtests bestanden**
