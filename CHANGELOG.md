# Changelog

## v0.21.0.8 — Peach Bitcoin CSV Import

### Peach Bitcoin
- Neuer eigener Peach-Bitcoin-CSV-Parser für die Spalten `Date`, `Trade ID`, `Type`, `Amount`, `Price`, `Bitcoin Price`, `Currency` und `Premium`.
- `Amount` wird bei Peach ausschließlich als Satoshi-Ganzzahl interpretiert; 100.000 sats werden exakt zu 0,001 BTC.
- `Price` bleibt der tatsächlich gezahlte bzw. erhaltene Fiat-Gesamtbetrag.
- `Premium` wird als Prozentwert behandelt. Bei Käufen wird der in `Bitcoin Price` enthaltene Aufschlag mit `Bitcoin Price / (1 + Premium/100)` entfernt; die Differenz zum gezahlten `Price` wird als Fiatgebühr ausgewiesen, ohne den FIFO-Einstand doppelt zu erhöhen.
- `Trade ID` dient als stabile Import-Identität; Roh-IDs werden weiterhin nicht ungefragt im Ledger gespeichert.
- Verkäufe werden unterstützt; bei Verkäufen bleibt der tatsächliche Fiat-Erlös maßgeblich und es wird kein positiver Premiumwert blind als zusätzliche Gebühr gebucht.

### Dokumentation
- README vollständig zweisprachig Deutsch/Englisch.
- Peach Bitcoin in der Importübersicht und in `CSV-IMPORT.md` dokumentiert.

### Tests und Release-Aufteilung
- Fünf gezielte Peach-Regressionstests: Sats-Umrechnung, Premium-/Gebührenrechnung, Trade-ID-Dubletten, fehlendes Premium und Verkauf.
- **Home-Assistant-Integration:** v0.21.0.8.
- **Tor Gateway:** bleibt v0.21.0.3.

## v0.21.0.7 — Bitpanda CSV & Fee Hotfix

### Bitpanda-Import
- Neuer eigener Bitpanda-Parser für Transaction Reports mit Erkennung über `Venue: Bitpanda`, `Reported by Bitpanda GmbH` und die charakteristische Header-Struktur.
- Der vorhandene BTC/XBT-Normalisierer bleibt die zentrale Bitcoin-only-Grenze. Käufe und Verkäufe anderer Assets sowie reine Fiat-Deposits werden ignoriert.
- `buy` wird als Kauf und `sell` als Verkauf verarbeitet; `In/Out` ist nur Zusatzinformation und bestimmt nicht die Buchungsart.
- `Transaction ID` wird als primäre stabile Import-Identität verwendet. Roh-IDs werden weiterhin nicht im Ledger gespeichert, sondern nur lokal gehasht.
- Physische CSV-Zeilennummern bleiben auch bei Bitpanda-Metadatenzeilen erhalten, damit Importfehler auf die tatsächliche Datei verweisen.

### Withdrawal- und Gebührenlogik
- BTC-`withdrawal` bleibt ein Transfer und erzeugt keinen FIFO-Verkauf.
- Eine explizite Bitpanda-Withdrawal-Fee in BTC wird dem seit dem vorherigen BTC-Withdrawal aufgebauten Kauf-Batch zugeordnet.
- Gemeinsame BTC-Fees werden proportional nach Brutto-BTC auf ganze Satoshis verteilt; der letzte Kauf erhält den exakten Rest, sodass die Summe exakt der exportierten BTC-Fee entspricht.
- Die Netzwerkfee reduziert den tatsächlichen Stack und bleibt als `fee_btc` erhalten; sie wird nicht künstlich in eine Fiat-Fee umgerechnet.
- Im Bitpanda-Ausführungspreis enthaltene Handelsgebühren/Prämien werden als separates `included_fee` gespeichert. Sie zählen in der Gebührenanalyse, verändern aber den FIFO-Einstand nicht ein zweites Mal.
- Liefert die CSV eine explizite Fiat-Handelsgebühr, wird diese als enthaltene Gebühr übernommen. Ist sie nur aus `Amount Fiat`, Brutto-BTC und Marktpreis ableitbar, wird die Differenz als geschätzt markiert. Ist sie aus dem CSV nicht rekonstruierbar, wird die 0,99-%-BTC-Prämie ausschließlich als editierbare Analytics-Schätzung verwendet.

### Importvorschau und Kontrolle
- Importvorschau und Speicherung unterstützen enthaltene Handelsgebühren einschließlich Schätzkennzeichen.
- Die Rechenkontrolle verwendet für Bitpanda den ursprünglichen Trade-BTC-Betrag vor einer späteren Withdrawal-Fee; hohe On-Chain-Gebühren erzeugen dadurch keine falsche Kaufabweichung.
- Fehlende Bitpanda-`Fee`-Werte (`-`) sind zulässig und machen eine ansonsten vollständige Kauf-/Verkaufszeile nicht ungültig.
- Export und Dashboard-Gebührenmetriken berücksichtigen `included_fee`, ohne die Kostenbasis doppelt zu belasten.

### HACS / Home Assistant
- Gemeinsamer `Validate`-Workflow mit HACS Action und Hassfest.
- `actions/checkout@v5`.
- Manifest mit `@21Koblenz` als `codeowners`, HACS/Hassfest-konformer Schlüsselreihenfolge und `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)`.
- **Tor Gateway bleibt v0.21.0.3**.

### Tests
- Bitpanda-Regressionen decken Buy/Sell, BTC/XBT-Filter, Altcoin-Ausschluss, Deposits, BTC-Withdrawals, mehrere Käufe pro Withdrawal-Batch, Satoshi-genaue Fee-Verteilung, physische Zeilennummern, ID-basierte Dubletten und enthaltene Handelsgebühren ab.
- Finale Testsuite: **354 Tests + 8 Subtests bestanden**; JavaScript-Syntaxprüfung, Python-Compile-Check, JSON-Parsing und Versionskonsistenz ebenfalls erfolgreich.

## v0.21.0.6 — Calculation, Privacy & Large-Ledger Performance Audit

### Berechnung und FIFO

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

### Kennzahlen und Charts

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

### Large-Ledger-Performance

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

### Datenschutz, Privatsphäre und Sicherheit

- CSV-Dublettenprüfung findet vollständig in Home Assistant Core statt; bestehende `import_ref_hash`-Werte werden nicht mehr in den Browser geladen.
- Der Core-Dubletten-Endpunkt liefert nur boolesche Dubletten-Flags und ist mengenbegrenzt/rate-limitiert.
- Dashboard, Chart, FIFO und Ledger verwenden minimierte Payloads bzw. Allow-Lists; Notizen, Provider-IDs und interne Import-/BTC-Fee-Metadaten werden nur dort übertragen, wo sie tatsächlich benötigt werden.
- Authentifizierte Panel-Antworten verwenden `Cache-Control: no-store, private`, `Pragma: no-cache`, same-origin/no-referrer-Härtung und `X-Content-Type-Options: nosniff`.
- Die restriktive CSP blockiert direkte Netzwerkverbindungen des Tracker-Frontends.
- Veraltete Lazy-Responses können keinen neueren Dashboard-Zustand überschreiben.
- Nicht-Owner erhalten weiterhin redigierte Verbindungsinformationen.
- Verschlüsselungsmodell (Argon2id, AES-256-GCM, HKDF-SHA-512/Envelope-Keying) wurde im Code-/Datenfluss-Audit erneut geprüft; der Audit ist kein externer Penetrationstest.

### CSV/FIFO-Oberfläche und Kompatibilität

- `FIFO SALES / Verkaufsübersicht` heißt jetzt **FIFO ABGÄNGE / FIFO-Abgänge**.
- Verkauf und Ausgabe werden als Art angezeigt; die Kopfzahl zählt echte Abgangsbuchungen statt einzelne Lot-Matches.
- ID-basierte Dublettenerkennung aus v0.21.0.4/v0.21.0.5 bleibt aktiv.
- Frontend Cache-Busting: `v021006-733b783d`.
- **Tor Gateway bleibt v0.21.0.3**; v0.21.0.6 betrifft ausschließlich die Custom Integration.

### Audit und Tests

- Neuer Berechnungs-, Datenschutz-, Privatsphäre- und Security-Code-Audit: [`AUDIT-v0.21.0.6.md`](AUDIT-v0.21.0.6.md).
- Berechnungsdetails: [`MATH-AUDIT.md`](MATH-AUDIT.md).
- Finale Testsuite: **351 Tests + 8 Subtests**; JavaScript-Numerik- und Syntaxprüfungen bestanden.

## v0.21.0.5 — Bulk-Import-Schema Hotfix

- Behebt den Fehler `extra keys not allowed @ data['transactions'][0]['import_ref_hash']` beim Bestätigen von CSV-Imports.
- `import_ref_hash` ist jetzt im tatsächlichen `bulk_import`-Transaktionsschema erlaubt.
- Die in v0.21.0.4 eingeführte ID-basierte Dubletten-Erkennung für Kraken und andere unterstützte CSV-Quellen kann dadurch serverseitig gespeichert und ausgewertet werden.
- Regressionstest ergänzt, damit Frontend-Payload und Home-Assistant-Service-Schema künftig nicht mehr auseinanderlaufen.
- Tor Gateway bleibt auf **v0.21.0.3**; dort ist keine Änderung nötig.

## v0.21.0.4 — CSV Duplicate Identity Hotfix

### Dublettenerkennung

- CSV-Buchungen mit identischem Zeitpunkt, BTC-Betrag, Kurs und Gebühr werden nicht mehr automatisch zusammengelegt, wenn die Quelle unterschiedliche Order-, Trade- oder Transaktions-IDs liefert.
- Kraken berücksichtigt `txid` und `ordertxid` gemeinsam. Mehrere gleich große Ausführungen derselben Order bleiben dadurch getrennte Buchungen, sobald sich mindestens eine Quell-ID unterscheidet.
- Die ID-basierte Erkennung gilt anbieterübergreifend für unterstützte CSV-Formate, soweit eine stabile Order-, Trade-, Transaktions- oder Referenz-ID vorhanden ist.
- Roh-IDs werden weiterhin nicht ungefragt im Ledger gespeichert. Für die Dublettenerkennung wird nur ein SHA-256-Hash aus Quelle und Quell-ID persistiert.
- Quellen ohne eindeutige ID verwenden weiterhin den bisherigen Werte-Fingerprint aus Typ, Zeitpunkt, Depot, BTC-Menge, Währung, Kurs und Gebühr.
- Für bereits vor diesem Hotfix importierte Buchungen ohne ID-Hash gibt es eine mengenbasierte Legacy-Abwärtskompatibilität: vorhandene identische Altbuchungen werden beim ersten erneuten Import einmalig angerechnet, weitere gleichwertige Zeilen mit unterschiedlichen IDs bleiben erhalten.

### Release-Aufteilung

- **Home-Assistant-Integration:** v0.21.0.4.
- **Tor Gateway:** bleibt v0.21.0.3, da dieser Hotfix keine Netzwerk-/Gateway-Änderung enthält. Dadurch erscheint für diesen Release kein unnötiges Tor-Gateway-Update.

### Tests

- Regressionstests für Kraken-Ausführungen mit identischen Handelswerten und unterschiedlichen `txid`/`ordertxid`.
- Regressionstest für Coinfinity-Buchungen mit identischen Werten und unterschiedlichen Order-IDs.
- Bestehende CSV-Parser-Regressionstests bleiben grün.

## v0.21.0.3 — CSV Import & Fee Accounting Hotfix

### Coinfinity

- `Amount Crypto` wird beim aktuellen Coinfinity-Report als BTC-Dezimalwert gelesen. Werte wie `0.00020000 BTC` ergeben exakt 20.000 sats; nachgestellte Nullen einer Sats-Ganzzahl werden nicht mehr abgeschnitten.
- `Mining Fee Crypto` wird als Satoshi-Betrag interpretiert. Leer oder 0 bedeutet Lightning; ein positiver Wert kennzeichnet eine On-Chain-Auszahlung.
- `Amount EUR` bleibt der tatsächlich überwiesene Gesamtbetrag. Service Fee und Mining Fee werden davon abgezogen und nicht ein zweites Mal auf den Zahlbetrag aufgeschlagen.
- Der tatsächlich erhaltene BTC-Betrag aus `Amount Crypto` bleibt unverändert. Für die Kostenbasis wird der effektive Kurs so normalisiert, dass BTC-Wert plus Gebühren exakt wieder `Amount EUR` ergibt.
- Order-ID, Adresse, Transaktions-ID und Lightning-Invoice bleiben optionale Vorschaufelder und landen nicht ungefragt in der Buchungsnotiz.

### Sats und Gebühren bei Verkäufen

- Die gemeinsame BTC/Sats-Anzeige entfernt keine nachgestellten Nullen mehr aus ganzzahligen Satoshi-Werten. Aus 20.000 sats kann dadurch nicht mehr fälschlich 2 sats werden.
- BTC→Sats wird für die Anzeige auf einen ganzzahligen Satoshi-Wert gerundet.
- Wird eine Verkaufsgebühr eindeutig in BTC/Sats ausgewiesen, zählt sie als zusätzlicher BTC-Abgang. Der Fiat-Gegenwert der Fee bleibt separat erhalten, sodass Stack, Nettoerlös und FIFO dieselbe tatsächlich abgegangene BTC-Menge verwenden.
- Diese eindeutige BTC-Fee-Behandlung gilt für die entsprechenden Verkaufspfade von Kraken Ledger, Binance Trade, CoinTracking/Pocket und Wavespace. Unklare generische Gebühren werden weiterhin nicht blind als zusätzlicher BTC-Abgang interpretiert.

### Wavespace

- BTC-Karten- und Verkaufsgebühren werden zusätzlich zur eigentlichen BTC-Menge vom Stack abgezogen. Beispiel: 100.000 sats Kartenumsatz + 371 sats Fee = 100.371 sats BTC-Abgang.
- `payWaveLowValuePurchase`, `POSPurchase`, `card purchase` und `card payment` werden als Buchungsart **Ausgabe** importiert.
- Bewertete Wavespace-Ausgaben verwenden für die Kontrollrechnung weiterhin die Verkaufslogik `BTC × Kurs − Fee = Fiat-Ausgabe`, bleiben im Buchungsbuch aber als **Ausgabe** gekennzeichnet.
- `ATMWithdrawal ... Card Authorization` bleibt eine Verkauf-/Bargeldabhebungsbuchung; ein normaler `CURRENCY_SWAP` BTC→Fiat bleibt ebenfalls **Verkauf**.
- Kartenhinweise können weiterhin aus einer zugeordneten `APPLICATION_FEE`-Zeile übernommen werden; Händlername, Kartenfee und optional aktivierbare Quelldaten bleiben erhalten.

### Export und Tests

- CSV-Export behandelt bewertete Ausgaben beim Fiat-Kontrollbetrag wie Verkäufe und zieht die gespeicherte Fee vom Bruttowert ab.
- Coinfinity-Regressionstests verwenden das reale aktuelle Schema mit BTC in `Amount Crypto` und Sats in `Mining Fee Crypto`.
- Regressionstests decken Sats mit nachgestellten Nullen, Lightning/On-Chain-Erkennung, BTC-Verkaufsfees sowie Wavespace-Kartenzahlungen als Ausgaben ab.

## v0.21.0.2 — Mathematical Audit Hotfix

### Charts und Performance

- TWR vollständig neu berechnet: externe Zu- und Abflüsse werden an ihrem tatsächlichen Buchungszeitpunkt getrennt und Teilperioden geometrisch verknüpft.
- Kauf- und Verkaufsgebühren wirken als Performancekosten; eine vollständige Auszahlung erzeugt nicht mehr fälschlich −100 % TWR.
- XIRR/XNPV auf die übliche 365-Tage-Konvention mit ganzen Zahlungstagen umgestellt; mehrdeutige IRR-Fälle werden erkannt statt willkürlich auf eine Lösung reduziert.
- XIRR-Suchraum für sehr kurze Zeiträume erweitert, damit stark annualisierte Tages-/Mehrtagesszenarien nicht unnötig als „nicht verfügbar“ enden.
- Maximaler Drawdown wird aus der vollständigen verfügbaren Analyse-Reihe berechnet und nicht mehr aus der für die Anzeige verdichteten Langzeitreihe.
- Langzeit-Downsampling behält den tatsächlichen Beobachtungstag eines Kurses bei; Werte werden nicht mehr künstlich ans Bucket-Ende verschoben.
- Tageskurse und tägliche FIFO-Snapshots werden einheitlich als Tagesendzustände behandelt.
- Intraday-Einstand, realisierter Gewinn und bekannte BTC werden nach jeder einzelnen Buchung neu ausgespielt statt nur mit dem finalen Tageszustand.

### FIFO, Gebühren und Zeitstempel

- FIFO-Sortierung verwendet echte UTC-Zeitpunkte statt lexikographischer ISO-Strings.
- Neue und bearbeitete Buchungen werden kanonisch als UTC-Zeitstempel gespeichert; Legacy-Migrationen sortieren ebenfalls nach dem realen Zeitpunkt.
- Historische Tages-Snapshots verwenden echte UTC-Zeitpunkte und einen neuen Chart-Cache-Schema-Stand, damit alte Cachewerte neu aufgebaut werden.
- Bei teilweise aufgelösten/überverkauften Verkäufen wird die Verkaufsgebühr proportional auch dem unaufgelösten Anteil des Nettoerlöses zugeordnet.
- FIFO-Verkaufsübersichten zählen BTC-Menge und Match-Anzahl nur innerhalb der angezeigten Fiatwährung.

### DCA, Gewinn/Verlust und Sensoren

- „Bester/Schlechtester Kauf“ verwendet den effektiven Einstand je BTC inklusive Kaufgebühren.
- Persönliche Sparjahre beginnen beim ersten passenden Kauf und rechnen Kalendergrenzen in UTC.
- Die missverständliche Prozentkennzahl „Gewinn / kumulierte Käufe“ wurde entfernt; kumulierte Kaufaufwendungen werden nur noch als klar bezeichnete Bezugsgröße angezeigt.
- Durchschnittlicher offener Kaufpreis und Buchgewinn-Prozent liefern ohne offenen bekannten Einstand „nicht verfügbar“ statt mathematisch falscher 0-Werte.
- Historische Durchschnittskaufpreise schreiben ohne bekannten offenen Bestand keinen künstlichen Nullwert mehr.

### Tests

- Numerische Golden-Tests für TWR, vollständige Auszahlung, Gebühren, XIRR-365-Tage, gleiche Zahlungstage, mehrdeutige XIRR-Wurzeln und Drawdown ergänzt.
- Regressionsprüfungen für UTC-FIFO, identische Zeitstempel, Tages-Snapshots, DCA, Multiwährung, Intraday-FIFO und Display-/Analyse-Trennung ergänzt.

## v0.21.0.1 — History Hotfix

- Historische BTC-Tagesdaten werden nicht mehr allein anhand eines frühen Startdatums als vollständig behandelt.
- Lücken werden über nachgelagerte Tor-Fallback-Quellen gefüllt; bereits vorhandene lokale Werte bleiben erhalten.
- Dichte-, Gap-, Start- und Endbereichsprüfungen verhindern unvollständige „Max“-Historien.
- Tor-Gateway-Workflow ist versionsunabhängig und nicht mehr auf v0.21.0.0 fest verdrahtet.

## v0.21.0.0 — Initial Public Release

### Portfolio, FIFO und Auswertungen

- Bitcoin-only Portfolio- und Stack-Tracking mit mehreren Depots.
- Käufe, Verkäufe, Gebühren, Notizen und depotweise FIFO-Zuordnung.
- Verkaufsübersicht mit FIFO-Einstand, Verkaufserlös, Gewinn/Verlust und Rendite.
- Bitcoin-Kurs-, Stack-, Portfoliowert- und Gewinn/Verlust-Charts mit mehreren Zeiträumen und Overlays.
- TWR-, XIRR-, DCA- und Drawdown-Auswertungen.
- Ziele, Milestones, Halving- und Bitcoin-Netzwerk-Markierungen.

### Import und Datenportabilität

- CSV-Import mit bearbeitbarer Vorschau und Plausibilitätsprüfung für unterstützte Börsen und Broker.
- Verschlüsselte portable `.bstbackup`-Backups für Käufe/Verkäufe, Depots, Ziele und Historie.
- Netzwerk-, Tor-, Zugriffs- und Verschlüsselungseinstellungen werden nicht aus portablen Backups wiederhergestellt.

### Home Assistant und mobile Nutzung

- Natives Home-Assistant-Seitenleistenpanel **Bitcoin Stack**.
- Zugriff über die authentifizierte Home-Assistant-Benutzeridentität.
- Desktop- und mobile Darstellung einschließlich Home-Assistant-Companion-App.
- Seitenwechsel in Buchungs- und Verkaufslisten springen an den Anfang der jeweiligen Liste.

### Tor und Fail Closed

- Eigenes Tor Gateway mit nftables-Default-Drop-Killswitch.
- Öffentliche Kurs- und Historienquellen ausschließlich über Tor.
- Lokale private Node-Ziele können direkt im privaten Netzwerk angesprochen werden.
- Automatische Supervisor-interne Erkennung des GitHub-installierten Tor Gateways und Kompatibilität mit lokalen Entwicklungsinstallationen.
- Kein öffentlicher DNS-/Clearnet-Fallback bei Fehlern der Gateway-Auflösung.

### Sicherheit

- Argon2id-basierte Passwortableitung und AES-256-GCM für den geschützten Tresor.
- Begrenzter Panel-/iframe-RPC-Kanal und restriktive Content Security Policy.
- Fail-closed Netzwerkpfad für öffentliche Datenquellen.
- Größenlimits, Zugriffskontrollen und gehärtete Backup-/Restore-Grenzen.
- Release-Metadaten, SBOM und reproduzierbare Integritätsprüfungen im Repository.

### Lizenz

- Öffentlicher Neustart unter **AGPL-3.0-only**.
