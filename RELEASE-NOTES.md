# Bitcoin Stack Tracker v0.21.0.9 — Updated release build

[English](#english) · [Deutsch](#deutsch)

> This build intentionally keeps the semantic version **v0.21.0.9** and replaces/extends the artifacts originally published under the same version on 2026-08-14.

---

<a id="english"></a>
## English

### Highlights

- **Sats Sentinel**: privacy-first watch-only monitoring for single/multiple Bitcoin addresses, XPUB/YPUB/ZPUB and descriptors.
- Selectable Sentinel source: **Automatic · Fulcrum/Electrum · electrs/Electrum · own Mempool · configured public Mempool over Tor**.
- Strict **fail-closed** behavior for explicitly selected sources. No silent provider or clearnet fallback.
- Fulcrum/electrs support through Electrum scripthash calls with LAN/Tor routing, TLS and SHA-256 certificate pinning for self-signed servers.
- Encrypted movement journal with sender → direction → recipient flow, thresholds, categories, notes, paging and Mempool explorer links.
- Deleting a Sentinel watch entry also permanently purges its journal history from the encrypted runtime cache.
- Sentinel configuration refresh no longer overwrites unsaved fields; save and source-test actions now return visible feedback.
- New adaptive **0–100 market assessment** with configurable weights, thresholds, volatility/cycle adaptation, bottom/top zones and confirmation diagnostics.
- Causal historical market-assessment reconstruction without look-ahead bias.
- Taller historical score chart with crosshair, axis badges, BTC-price overlay, configurable opacity and linear/log price axis.
- Optional **causal EMA smoothing**: Off / 3 / 5 / 7 / 14 / 30 points. Default is **EMA 5**. Smoothing is display-only and never changes the raw score or Home Assistant sensor.
- **Restore defaults** resets the market-history display to 3 years, EMA 5, BTC overlay on, 55% price opacity and logarithmic price axis.
- Overview chart adds **Bitcoin price + market assessment** and automatically uses the same smoothing setting.
- Overview market overlay no longer forward-fills one daily score into every intraday candle; causal score samples are aligned to the price timeline and the score axis auto-scales to the visible range so changes remain readable.
- Faster live-price/chart refresh behavior while public network traffic remains Tor-only.

### Sats Sentinel source policy

An explicitly selected own source is authoritative:

- Fulcrum selected + Fulcrum unavailable → Sentinel offline/partial.
- electrs selected + electrs unavailable → Sentinel offline/partial.
- own Mempool selected + own Mempool unavailable → Sentinel offline/partial.
- **No automatic fallback to a public provider.**

`Automatic` selects the best configured source, but public Mempool is considered only when no own source exists. Local/private endpoints may be direct LAN connections; `.onion` and public endpoints use Tor with remote DNS.

### Privacy

Sats Sentinel never accepts private keys or seeds and cannot sign or spend. XPUB/descriptors remain in the encrypted vault configuration; the device-bound runtime cache contains only concrete derived addresses/scripts. Public market-assessment data remains separate from private portfolio data.

### Quality assurance

- **457 tests + 8 subtests passed**
- Python compile, JavaScript syntax, JSON/YAML and version consistency checked
- Dedicated regressions cover fail-closed source selection, TLS pinning, journal purge, causal market history/smoothing and the overview overlay

### Compatibility

- Home Assistant custom integration: **v0.21.0.9**
- Bitcoin Stack Tracker Tor Gateway: **v0.21.0.3** unchanged

### Publishing note for the unchanged version number

GitHub already contains a `v0.21.0.9` tag/release. If immutable releases are **not** enabled, publish this replacement by recreating/updating the release and recreating the `v0.21.0.9` tag at the new release commit. If GitHub Immutable Releases are enabled for the repository, GitHub does not allow a deleted immutable release tag name to be reused, so keeping the exact tag would not be technically possible. Existing HACS installations already reporting `0.21.0.9` may need HACS **Redownload** because the semantic version did not increase.

---

<a id="deutsch"></a>
## Deutsch

### Highlights

- **Sats Sentinel**: Privacy-first Watch-only-Überwachung für einzelne/mehrere Bitcoin-Adressen, XPUB/YPUB/ZPUB und Descriptoren.
- Einstellbare Sentinel-Abfragequelle: **Automatisch · Fulcrum/Electrum · electrs/Electrum · eigene Mempool-Instanz · konfigurierte öffentliche Mempool-Instanz über Tor**.
- Striktes **Fail Closed** bei explizit ausgewählten Quellen. Kein heimlicher Provider- oder Clearnet-Fallback.
- Fulcrum/electrs über Electrum-Scripthash-Abfragen mit LAN-/Tor-Routing, TLS und SHA-256-Zertifikat-Pinning für selbstsignierte Server.
- Verschlüsseltes Bewegungsjournal mit Sender → Richtung → Empfänger, Schwellen, Kategorien, Notizen, Pagination und Mempool-Explorer-Links.
- Das Entfernen eines Sentinel-Watch-Eintrags löscht auch dessen Journal-Historie dauerhaft aus dem verschlüsselten Runtime-Cache.
- Der Sentinel-Statusrefresh überschreibt keine ungespeicherten Felder mehr; Speichern und Quellen-Test geben sichtbares Feedback.
- Neue adaptive **0–100-Markteinschätzung** mit einstellbaren Gewichten, Schwellen, Volatilitäts-/Zyklusanpassung sowie Boden-/Top-Zonen und Bestätigungsdiagnostik.
- Kausale historische Rekonstruktion der Markteinschätzung ohne Look-ahead-Bias.
- Höherer Historical-Score-Chart mit Fadenkreuz, Achsenwerten, BTC-Preis-Overlay, einstellbarer Deckkraft und linearer/logarithmischer Preisachse.
- Optionale **kausale EMA-Glättung**: Aus / 3 / 5 / 7 / 14 / 30 Punkte. Standard ist **EMA 5**. Die Glättung ist rein visuell und verändert weder Rohscore noch Home-Assistant-Sensor.
- **Standard wiederherstellen** setzt die Chartdarstellung auf 3 Jahre, EMA 5, BTC-Overlay an, 55 % Preis-Deckkraft und logarithmische Preisachse zurück.
- Auf der Startseite gibt es **Bitcoin-Kurs + Markteinschätzung**; dort wird automatisch dieselbe Glättung verwendet.
- Der Startseiten-Overlay füllt einen Tagesscore nicht mehr in jedes Intraday-Kursintervall vorwärts auf. Kausale Score-Stützpunkte werden direkt auf die Kurszeitachse gelegt; die Scoreachse skaliert auf den sichtbaren Bereich, damit Veränderungen nicht als Seitwärtsstrich verschwinden.
- Schnellere Live-Kurs-/Chart-Aktualisierung bei weiterhin Tor-only geroutetem öffentlichen Netzwerkverkehr.

### Sats-Sentinel-Quellenregel

Eine explizit gewählte eigene Quelle ist verbindlich:

- Fulcrum gewählt + Fulcrum nicht erreichbar → Sentinel offline/teilweise.
- electrs gewählt + electrs nicht erreichbar → Sentinel offline/teilweise.
- eigene Mempool-Instanz gewählt + nicht erreichbar → Sentinel offline/teilweise.
- **Kein automatischer Wechsel auf einen öffentlichen Provider.**

`Automatisch` wählt die beste konfigurierte Quelle; eine öffentliche Mempool-Quelle wird nur berücksichtigt, wenn keine eigene Quelle vorhanden ist. Lokale/private Ziele dürfen direkt im LAN angesprochen werden; `.onion`- und öffentliche Ziele laufen über Tor mit Remote-DNS.

### Datenschutz

Sats Sentinel akzeptiert niemals Private Keys oder Seeds und kann nicht signieren oder ausgeben. XPUB/Descriptor bleiben in der verschlüsselten Tresorkonfiguration; der gerätegebundene Runtime-Cache enthält nur konkrete abgeleitete Adressen/Scripts. Öffentliche Markteinschätzungsdaten bleiben von privaten Portfoliodaten getrennt.

### Qualitätssicherung

- **457 Tests + 8 Subtests bestanden**
- Python-Compile, JavaScript-Syntax, JSON/YAML und Versionskonsistenz geprüft
- Eigene Regressionstests für Fail-Closed-Quellenwahl, TLS-Pinning, Journal-Löschung, kausale Markthistorie/Glättung und Startseiten-Overlay

### Kompatibilität

- Home-Assistant-Custom-Integration: **v0.21.0.9**
- Bitcoin Stack Tracker Tor Gateway: **v0.21.0.3** unverändert

### Hinweis zur unveränderten Versionsnummer

Auf GitHub existiert bereits ein Tag/Release `v0.21.0.9`. Wenn **Immutable Releases nicht aktiviert** sind, kann das Release ersetzt und der Tag `v0.21.0.9` auf dem neuen Release-Commit neu erstellt werden. Sind GitHub Immutable Releases für das Repository aktiviert, darf der Name eines gelöschten immutable Release-Tags nicht erneut verwendet werden; dann wäre das Festhalten am identischen Tag technisch nicht möglich. Bereits installierte HACS-Instanzen mit `0.21.0.9` können wegen der unveränderten semantischen Version **Neu herunterladen / Redownload** benötigen.
