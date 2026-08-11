# Bitcoin Stack Tracker v0.21.0.7

## App- und Funktionsübersicht

**Bitcoin Stack Tracker** ist ein lokaler Bitcoin-only Portfolio- und Stack-Tracker für Home Assistant mit getrenntem Tor Gateway für öffentliche Datenquellen.

### Kernfunktionen

- mehrere Depots und Gesamtdepot
- Käufe, Verkäufe, Ausgaben, Gebühren, Notizen und depotweises FIFO
- CSV-Import mit bearbeitbarer Vorschau und ID-basierter Dubletten-Erkennung
- direkte Importer u. a. für Kraken, Coinbase, Binance, Bitpanda, Coinfinity, Pocket Bitcoin und Wavespace
- historische Kurs-, Stack-, Portfolio-, Einstands- und Gewinn/Verlust-Charts
- TWR, XIRR, BTC-CAGR, DCA, Drawdown und cashflow-neutraler HODL-Benchmark
- Haltezeit-Regel, gewichtetes Stack-Alter, Altersverteilung und FIFO-Abgänge
- Stacking-Geschwindigkeit, Netto-Fiat-Investment und Gebührenquoten
- getrennte Linear/Log-Skalen für linke und rechte Chart-Achse
- verschlüsselte portable `.bstbackup`-Backups
- Privacy-/Diskretmodus, BTC/Sats und fiatfreie Ansicht
- Deutsch/Englisch sowie Desktop-/Smartphone-Ansicht
- natives Home-Assistant-Seitenleistenpanel

### Datenschutz und Netzwerk

- Portfolio- und Buchungsdaten bleiben lokal in Home Assistant.
- CSV-Dublettenabgleiche bleiben in Core; bestehende Import-Hashes werden nicht in den Browser geladen.
- Öffentliche Kurs- und Historienabfragen laufen über das getrennte Tor Gateway.
- Lokale private Node-Ziele dürfen direkt im LAN angesprochen werden.
- Das Gateway hat keinen Zugriff auf Portfolio, Tresorpasswort oder Home-Assistant-API-Token.

---

## Änderungen in v0.21.0.7

### Bitpanda Transaction Report

- Neuer eigener Bitpanda-CSV-Parser.
- Erkennung über Bitpanda-Metadaten und die Spalten `Transaction ID`, `Timestamp`, `Transaction Type`, `Amount Fiat`, `Amount Asset`, `Asset`, `Asset market price`, `Fee` und `Fee asset`.
- Ausschließlich Bitcoin wird verarbeitet; BTC/XBT-Varianten laufen über den bestehenden zentralen Bitcoin-Normalisierer. Altcoins und reine Fiatbewegungen werden ignoriert.
- `buy` → Kauf, `sell` → Verkauf. `deposit` und `withdrawal` werden nicht als Handel gespeichert.
- `Transaction ID` ist die primäre Dublettenidentität; unterschiedliche IDs bleiben getrennt, selbst wenn Zeitpunkt und Beträge identisch sind.

### Bitpanda Withdrawal-Fees

- BTC-Withdrawals bleiben Transfers und erzeugen keinen FIFO-Abgang.
- Eine explizite BTC-Withdrawal-/Netzwerkfee wird auf alle seit dem vorherigen BTC-Withdrawal angesammelten BTC-Käufe verteilt.
- Die Verteilung erfolgt proportional auf ganze Satoshis und summiert sich exakt zur exportierten Fee.
- Die BTC-Fee reduziert den Stack und bleibt als BTC/Sats-Gebühr erhalten; es findet keine künstliche Fiat-Konvertierung statt.

### Enthaltene Bitpanda-Handelsgebühren

- Handelsgebühren/Prämien, die bereits im Bitpanda-Ausführungspreis stecken, werden getrennt als **enthaltene Handelsgebühr** geführt.
- Diese Gebühr fließt in **Gesamte Gebühren** und die **Kauf-/Verkaufsgebührenquote** im Dashboard ein.
- Sie wird nicht noch einmal auf die FIFO-Kostenbasis aufgeschlagen.
- Eine explizit im CSV ausgewiesene Fiat-Handelsgebühr wird direkt übernommen.
- Kann eine enthaltene Gebühr nur aus den CSV-Werten abgeleitet werden, wird sie als Schätzung markiert.
- Wenn der historische Aufschlag aus dem Export nicht rekonstruierbar ist, dient 0,99 % ausschließlich als **editierbare Analytics-Schätzung**; diese Schätzung beeinflusst weder FIFO noch die Import-Plausibilitätsprüfung.

### Importkontrolle und Bedienung

- Bitpanda-Kontrollrechnungen verwenden den ursprünglichen Brutto-Trade vor späteren BTC-Withdrawal-Fees.
- Fehlende Fee-Felder (`-`) sind zulässig.
- Tatsächliche physische CSV-Zeilennummern werden auch bei vorangestellten Bitpanda-Metadaten korrekt angezeigt.
- Enthaltene Handelsgebühren sind in der Importvorschau sichtbar und editierbar.
- CSV-Export erhält die enthaltene Gebühr und deren Schätzkennzeichen.

### HACS / Repository-Qualität

- HACS Validation und Hassfest laufen gemeinsam im `Validate`-Workflow.
- Manifest ist nach Home-Assistant-Konvention sortiert und enthält `@21Koblenz` als Codeowner.
- Die Integration deklariert explizit das Config-Entry-only-Schema.
- Der erfolgreiche CI-Workflow ist die Grundlage für die geplante HACS-Default-Aufnahme; dieser Release selbst behauptet keine bereits erfolgte Aufnahme.

### Kompatibilität

- Custom Integration: **v0.21.0.7**
- Tor Gateway: weiterhin **v0.21.0.3**
- Mindestversion laut `hacs.json`: Home Assistant **2026.7.0**
- Frontend Cache-Busting: `021007-050b734c`

### Qualitätssicherung

Der grundlegende Berechnungs-, Datenschutz- und Security-Audit aus v0.21.0.6 bleibt bestehen. v0.21.0.7 konzentriert sich auf CSV-Import, Gebührenmodell und Repository-/HACS-Konformität und ergänzt dafür gezielte Regressionstests.

Finale Testsuite: **354 Tests + 8 Subtests bestanden**; JavaScript-Syntaxprüfung, Python-Compile-Check, JSON-Parsing und Versionskonsistenz ebenfalls erfolgreich.

**Full Changelog:** [`v0.21.0.6...v0.21.0.7`](https://github.com/21Koblenz/bitcoin-stack-tracker/compare/v0.21.0.6...v0.21.0.7)
