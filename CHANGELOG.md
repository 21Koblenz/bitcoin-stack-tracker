# Changelog

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
