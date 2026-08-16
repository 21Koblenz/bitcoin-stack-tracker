# Bitcoin Stack Tracker v0.21.0.11 — Release Notes

[English](#english) · [Deutsch](#deutsch)

---

<a id="english"></a>
## English

v0.21.0.11 builds on **v0.21.0.10**.

### Historical market assessment

`10 years` and `Max` now select the true highest causal raw score independently in every 4-year window. The chart draws only a small star for each value, retains all marker dates even when the visible series is sampled, and lists date/score in a compact legend. The overview chart reuses the same markers. Hover/tap opens details.

Bottom confirmation is no longer incorrectly tied to the exact maximum-score day. For every marker, the backend searches forward only within the configured `turning_zone_memory_days` period. Every candidate is calculated strictly as of that date, so later rebound/divergence/trend evidence can confirm the earlier stress point without changing the historical score or introducing future data. A 4-year marker is always evaluated independently, but it is only labelled **Bottom confirmed** when the configured gates are actually met.

The modular model editor now gives every configurable field a purpose/effect explanation, including the effect of increasing and decreasing values.

### Sats Sentinel layout

Status, journal, test lab, monitor settings, watch targets and privacy are now independently collapsible. The layout is saved per portfolio in browser storage and restored on the same browser/device.

### Stable frontend files

The frontend now permanently uses `index.html`, `panel.js`, `static/app.js`, `static/style.css` and `static/performance-math.js`. Cache invalidation uses the release version in the query string. Existing legacy version/hash files from v0.21.0.10 are a **one-time cleanup**; future releases do not require deleting frontend files.

### Validation

**485 tests + 8 subtests passed**, plus Python compile, JavaScript syntax, JSON parsing and the separate performance-math numeric test.

- Custom Integration: **v0.21.0.11**
- Tor Gateway: **v0.21.0.3** unchanged

---

<a id="deutsch"></a>
## Deutsch

v0.21.0.11 baut auf **v0.21.0.10** auf.

### Historische Markteinschätzung

`10 Jahre` und `Max` bestimmen jetzt in jedem 4-Jahres-Fenster unabhängig den tatsächlich höchsten kausalen Rohscore. Im Chart wird dafür nur ein kleiner Stern gezeichnet; die Marker-Tage bleiben auch beim Sampling der sichtbaren Daten erhalten und Datum/Score stehen zusätzlich in einer kompakten Legende. Der Startseitenchart verwendet dieselben Marker. Hover/Antippen öffnet Details.

Die Bodenbestätigung ist nicht mehr fälschlich an den exakten Tag des maximalen Scores gebunden. Für jeden Marker sucht das Backend ausschließlich innerhalb des eingestellten `turning_zone_memory_days`-Zeitraums nach vorne. Jeder Kandidat wird strikt mit dem Wissensstand dieses Tages berechnet. So können spätere Rebound-/Divergenz-/Trend-Signale den früheren Stresspunkt bestätigen, ohne den historischen Score zu verändern oder zukünftige Daten einzubauen. Jeder 4-Jahres-Marker wird unabhängig geprüft; **Boden bestätigt** erscheint aber weiterhin nur, wenn die konfigurierten Bedingungen wirklich erfüllt wurden.

Der Editor des modularen Modells erklärt jetzt bei jedem einstellbaren Feld Zweck und Wirkung einschließlich der Auswirkung von Erhöhen und Verringern.

### Sats-Sentinel-Layout

Status, Journal, Testlabor, Überwachungseinstellungen, Watch-Ziele und Datenschutz sind jetzt unabhängig einklappbar. Die Ansicht wird pro Portfolio im Browser gespeichert und auf demselben Browser/Gerät wiederhergestellt.

### Stabile Frontend-Dateien

Das Frontend verwendet dauerhaft `index.html`, `panel.js`, `static/app.js`, `static/style.css` und `static/performance-math.js`. Die Cache-Invalidierung läuft über die Release-Version im Query-String. Die alten Versions-/Hash-Dateien aus v0.21.0.10 werden **einmalig** entfernt; künftige Releases brauchen kein Löschen von Frontend-Dateien mehr.

### Prüfung

**485 Tests + 8 Subtests bestanden**, zusätzlich Python-Compile, JavaScript-Syntax, JSON-Parsing und der separate Performance-Math-Numeriktest.

- Custom Integration: **v0.21.0.11**
- Tor Gateway: **v0.21.0.3** unverändert
