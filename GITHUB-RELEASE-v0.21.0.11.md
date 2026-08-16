# Bitcoin Stack Tracker v0.21.0.11 — Causal Market Markers & Compact Sats Sentinel

[English](#english) · [Deutsch](#deutsch)

---

<a id="english"></a>
## English

v0.21.0.11 builds on **v0.21.0.10** and focuses on the historical market-assessment markers, model explainability, Sats Sentinel layout and frontend release maintenance.

### Market assessment

- `10 years` and `Max` now use the **true highest causal raw score per 4-year window** instead of a single global best value.
- Best values are shown as **small star markers only**. The historical chart keeps a compact date/score legend below the chart, and the same stars are shown in the overview Bitcoin-price + market-assessment chart.
- Desktop: hover a star for details. Touch devices: tap a star.
- **Bottom confirmation can now arrive after the best-score day.** Each marker independently scans only the configured `turning_zone_memory_days` window forward and evaluates every candidate strictly with data available as of that candidate date. The marker keeps its original score date; the popup can show the later confirmation date and lag.
- This fixes the association logic without loosening the default bottom-zone or confirmation thresholds and without introducing look-ahead into the historical score.
- Every configurable field in the modular model now explains what it controls and what increasing/decreasing it changes. Weight fields explicitly explain that more weight means more influence, not an automatic score increase.

### Sats Sentinel

- The six main sections are independently collapsible: status, journal, test lab, monitor settings, watch targets and privacy.
- The open/collapsed layout is persisted **per portfolio** in browser storage and restored after reloads or portfolio switches on the same browser/device.
- Defaults keep status, journal and watch targets open; test lab, settings and privacy start collapsed.

### Frontend release maintenance

- Stable canonical frontend filenames are now the permanent release layout: `index.html`, `panel.js`, `app.js`, `style.css`, `performance-math.js`.
- Cache busting uses `?v=0.21.0.11` rather than generating new hash/version filenames.
- The legacy version/hash files in the existing v0.21.0.10 repository must be deleted **once** during this upgrade. `.gitignore` blocks those patterns afterwards, so future releases only overwrite the stable files.

### Validation

- **485 tests + 8 subtests passed**
- Python compile passed
- JavaScript syntax passed
- JSON/SBOM parsing passed
- Performance-math numeric JavaScript test passed

Home Assistant custom integration: **v0.21.0.11**  
Tor Gateway: **v0.21.0.3** unchanged

See [`CHANGELOG.md`](CHANGELOG.md), [`RELEASE-NOTES.md`](RELEASE-NOTES.md), [`PUBLISHING.md`](PUBLISHING.md) and [`RELEASE-QC-v0.21.0.11.md`](RELEASE-QC-v0.21.0.11.md).

---

<a id="deutsch"></a>
## Deutsch

v0.21.0.11 baut auf **v0.21.0.10** auf und konzentriert sich auf die historischen Marker der Markteinschätzung, verständlichere Modellparameter, ein kompakteres Sats-Sentinel-Layout und eine wartungsfreundliche Frontend-Release-Struktur.

### Markteinschätzung

- `10 Jahre` und `Max` verwenden jetzt den **tatsächlich höchsten kausalen Rohscore je 4-Jahres-Fenster** statt nur eines globalen Bestwerts.
- Die Bestwerte erscheinen nur als **kleine Sterne**. Unter dem Historical-Chart bleibt eine kompakte Datum-/Score-Legende sichtbar; dieselben Sterne werden im Startseitenchart Bitcoin-Kurs + Markteinschätzung angezeigt.
- Desktop: Maus über den Stern. Touch-Gerät: Stern antippen.
- **Die Bodenbestätigung darf jetzt nach dem Bestscore-Tag eintreffen.** Jeder Marker durchsucht unabhängig nur das konfigurierte `turning_zone_memory_days`-Fenster nach vorne und bewertet jeden Kandidaten strikt mit den bis zu diesem Kandidatentag verfügbaren Daten. Der Stern behält sein ursprüngliches Score-Datum; das Popup kann das spätere Bestätigungsdatum und die Verzögerung anzeigen.
- Damit wird die Zuordnungslogik korrigiert, ohne die Default-Schwellen für Boden-Zone/Bestätigung zu lockern und ohne Look-ahead in den historischen Score einzubauen.
- Jedes einstellbare Feld im modularen Modell erklärt jetzt, was es steuert und was Erhöhen/Verringern praktisch verändert. Bei Gewichten wird ausdrücklich erklärt: mehr Gewicht bedeutet mehr Einfluss, nicht automatisch einen höheren Score.

### Sats Sentinel

- Die sechs Hauptbereiche lassen sich unabhängig einklappen: Status, Journal, Testlabor, Überwachungseinstellungen, Watch-Ziele und Datenschutz.
- Der offene/eingeklappte Zustand wird **pro Portfolio** im Browser gespeichert und nach Neuladen oder Portfolio-Wechsel auf demselben Browser/Gerät wiederhergestellt.
- Standard: Status, Journal und Watch-Ziele offen; Testlabor, Einstellungen und Datenschutz eingeklappt.

### Frontend-Release-Pflege

- Dauerhaft stabile Frontend-Dateinamen: `index.html`, `panel.js`, `app.js`, `style.css`, `performance-math.js`.
- Cache-Busting erfolgt über `?v=0.21.0.11` statt über neue Hash-/Versionsdateien.
- Die vorhandenen Legacy-Dateien im v0.21.0.10-Repository werden bei diesem Upgrade **einmalig** gelöscht. `.gitignore` blockiert diese Muster danach; künftige Releases überschreiben nur noch die stabilen Dateien.

### Prüfung

- **485 Tests + 8 Subtests bestanden**
- Python-Compile bestanden
- JavaScript-Syntax bestanden
- JSON-/SBOM-Parsing bestanden
- Performance-Math-Numeriktest in JavaScript bestanden

Home-Assistant-Custom-Integration: **v0.21.0.11**  
Tor Gateway: **v0.21.0.3** unverändert

Details: [`CHANGELOG.md`](CHANGELOG.md), [`RELEASE-NOTES.md`](RELEASE-NOTES.md), [`PUBLISHING.md`](PUBLISHING.md) und [`RELEASE-QC-v0.21.0.11.md`](RELEASE-QC-v0.21.0.11.md).
