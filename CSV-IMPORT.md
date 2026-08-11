# CSV-Import

Der CSV-Import befindet sich im Dashboard unter **Buchungen**. Er übernimmt Bitcoin-Käufe, Bitcoin-Verkäufe und ausdrücklich erkannte BTC-Ausgaben. Einzahlungen, Auszahlungen, interne Transfers, Altcoins und sonstige Kontobewegungen werden nicht automatisch als Kauf, Verkauf oder Ausgabe gespeichert.

## Ablauf

1. CSV-, TXT- oder ZIP-Datei auswählen und ein Zieldepot festlegen.
2. **CSV prüfen** öffnen.
3. Erkannte Zeilen kontrollieren und bei Bedarf Art, Datum, BTC-Menge, Währung, Kurs, Gebühr, Depot oder Notiz ändern.
4. Ungewünschte Zeilen abwählen oder entfernen.
5. Ausgewählte Buchungen gemeinsam bestätigen.

Vor der Bestätigung wird nichts in das Kaufbuch geschrieben. Der bestätigte Stapel wird vollständig geprüft und anschließend in einem Speichervorgang übernommen. Würde ein Verkauf den zu diesem Zeitpunkt vorhandenen Bestand im gewählten Depot überschreiten, wird der gesamte Stapel abgelehnt.

## Datenschutz und Dateilöschung

- Die hochgeladene Datei wird nur im Arbeitsspeicher der Dashboard-App gelesen.
- Es wird keine temporäre oder dauerhafte CSV-Datei im Add-on angelegt.
- Die Antwort an den Browser enthält nur normalisierte Vorschauwerte, nicht die ursprünglichen CSV-Zeilen.
- Nach dem Einlesen wird die Dateiauswahl im Browser geleert.
- Die Originaldatei auf dem Smartphone oder Computer kann eine Web-App technisch nicht löschen. Sie bleibt dort bestehen, bis sie vom Nutzer gelöscht wird.
- Im Kaufbuch landen nur bestätigte Felder für Kauf, Verkauf oder Ausgabe. Dateiname, vollständige Originalzeile und CSV-Inhalt werden nicht gespeichert.

## Direkt erkannte Formate

- Coinbase Transaction History
- Kraken Trades History
- Kraken Ledgers History
- Binance Trade History
- Binance Transaction History / Transaction Record
- Bitpanda Transaction Report
- CoinTracking Universal CSV
- Coinfinity „My Activities“ mit On-Chain- und Lightning-Auszahlungen

Beim aktuellen Coinfinity-Format ist `Amount Crypto` ein BTC-Dezimalwert. Die Sats-Anzeige wird daraus ausschließlich über `BTC × 100.000.000` berechnet; `0.00020000 BTC` entspricht daher exakt 20.000 sats. Nachgestellte Nullen einer ganzzahligen Sats-Anzeige werden nicht entfernt. `Mining Fee Crypto` ist dagegen ein Satoshi-Betrag: leer oder 0 bedeutet Lightning, ein positiver Wert kennzeichnet On-Chain. Als Fiatgebühr wird `Total Fee EUR` übernommen; fehlt dieser Wert, setzt sie sich aus `Mining Fee EUR` und `Service Fee EUR` zusammen. `Amount EUR` bleibt der tatsächlich überwiesene Gesamtbetrag. Service- und Mining-Fee sind Abzüge aus diesem Betrag und werden nicht noch einmal oben aufgeschlagen. Der tatsächlich erhaltene BTC-Betrag aus `Amount Crypto` bleibt unverändert; für die Kostenbasis wird der effektive Kurs bei Bedarf so normalisiert, dass BTC-Wert plus Fee exakt wieder `Amount EUR` ergibt.

Für Relai, Bittr/getbittr und Wavespace gibt es eine flexible Broker-Erkennung anhand des Dateinamens und üblicher Spaltenbezeichnungen. Pocket Bitcoin wird in zwei eigenen Varianten unterstützt: dem CoinTracking-kompatiblen Export (`Type, Buy Amount, Buy Cur., ...`) und dem nativen Pocket-Dashboard-Export (`type,date,reference,price.currency,...`). Beim CoinTracking-kompatiblen Pocket-Export ist eine Fiat-Gebühr bereits im `Sell Amount` enthalten: für den Ausführungskurs wird deshalb `Sell Amount - Fee Amount` verwendet, während die Gebühr separat erhalten bleibt. So entspricht der gesamte Einstand weiterhin exakt dem tatsächlich eingezahlten Fiatbetrag. Bei einer CoinTracking-`Withdrawal` ist der Wallet-Eingang `Sell Amount - Fee Amount`, wenn die Gebühr in BTC/Sats angegeben ist. Mehrere Käufe dürfen in einer einzigen Pocket-Auszahlung gebündelt werden: Der Parser sortiert Trade und Withdrawal chronologisch, sammelt alle noch nicht ausgezahlten Käufe seit der vorherigen Withdrawal und verteilt den Netto-Walletbetrag proportional nach BTC-Menge auf diesen Block. Dadurch funktionieren auch Auszahlungen nach Mitternacht (z. B. 01:55 oder 02:24 Uhr), ohne einen späteren Kauf nach der Auszahlung fälschlich einzubeziehen. Beim nativen Pocket-Dashboard-CSV ist dagegen `value.amount` bereits der Netto-Walletbetrag und wird nicht noch einmal um `fee.amount` reduziert. Werden dort mehrere Käufe in einer Withdrawal zusammen ausgezahlt, sammelt der Parser ebenfalls alle Käufe seit der vorherigen Withdrawal, auch über Mitternacht hinweg, und verteilt `value.amount` proportional nach Brutto-BTC auf diese Käufe. Der jeweilige Anteil der gemeinsamen Netzwerkgebühr ergibt sich aus der Differenz zwischen Brutto- und Netto-BTC und wird mit dem Kaufkurs des jeweiligen Trades in Fiat berücksichtigt. Bei Pocket erzeugt nur der eigentliche Trade/Kauf eine Buchung; Deposit und Withdrawal werden als Transfers behandelt. Andere Anbieter werden über den generischen Bitcoin-CSV-Parser erkannt, sofern die Datei verständliche Felder für Art, Datum, BTC-Menge sowie Fiatbetrag oder BTC-Kurs enthält.

Da Anbieter ihre Exportformate ändern können, ist die Vorschau immer verbindlich. Eine Zeile mit fehlenden oder widersprüchlichen Werten wird nicht automatisch ausgewählt und muss vor dem Import korrigiert werden.

## Bitpanda Transaction Report

Bitpanda wird über die charakteristischen Spalten und zusätzlich über Metadaten wie `Venue: Bitpanda` beziehungsweise `Reported by Bitpanda GmbH` erkannt. Der Dateiname ist dafür nicht maßgeblich.

- `Transaction Type = buy` mit BTC/XBT → Kauf
- `Transaction Type = sell` mit BTC/XBT → Verkauf
- `deposit` → keine Bitcoin-Buchung
- `withdrawal` → Transfer, kein Verkauf
- andere Assets als BTC/XBT → ignoriert

`Transaction ID` ist die primäre Import-Identität. Zwei Bitpanda-Zeilen mit gleichem Zeitpunkt und gleichen Beträgen bleiben getrennt, wenn ihre Transaction IDs unterschiedlich sind. Wie bei anderen Quellen wird die Roh-ID nicht im Ledger gespeichert; für die Dublettenprüfung wird nur ein lokaler SHA-256-Identitätswert persistiert.

### Bitpanda-Withdrawal-Fees

Eine BTC-Auszahlung schließt den seit der vorherigen BTC-Auszahlung aufgebauten Kauf-Batch. Ist `Fee asset = BTC`, wird die ausgewiesene BTC-Fee proportional nach Brutto-BTC auf die zugehörigen Käufe verteilt. Die Verteilung erfolgt auf ganze Satoshis; der letzte Kauf erhält den exakten Rest. Der Withdrawal selbst wird nicht als Verkauf gespeichert.

Die BTC-Withdrawal-Fee reduziert damit den tatsächlich verbleibenden Stack und bleibt als `fee_btc` erhalten. Sie wird nicht künstlich in eine Fiatgebühr umgerechnet.

### Im Preis enthaltene Bitpanda-Handelsgebühren

Bitpanda-Reports können bei `Fee` ein `-` enthalten, obwohl eine Handelsprämie bereits im Ausführungspreis steckt. Der Tracker führt solche Kosten getrennt als **enthaltene Handelsgebühr**:

- explizite Fiat-Fee im CSV → direkt als enthaltene Gebühr
- positive, aus `Amount Fiat`, ursprünglicher BTC-Menge und `Asset market price` ableitbare Differenz → als geschätzte enthaltene Gebühr
- aus dem CSV nicht rekonstruierbare historische Prämie → 0,99 % nur als editierbare Analytics-Schätzung

Diese enthaltene Gebühr wird im Gebühren-Dashboard berücksichtigt, aber nicht ein zweites Mal zur FIFO-Kostenbasis addiert. Eine reine Schätzung beeinflusst auch nicht die Rechenkontrolle des Kaufs.

Die Plausibilitätsprüfung verwendet bei Bitpanda stets die ursprüngliche BTC-Handelsmenge vor einer späteren Withdrawal-Fee. Dadurch können hohe On-Chain-Gebühren keinen ansonsten gültigen Kauf als widersprüchlich markieren.

## Dubletten und Gebühren

Wenn ein Anbieter eine Transaktions-, Order- oder Trade-ID liefert, hat diese Import-Identität Vorrang vor dem Wertevergleich. Zwei Ausführungen mit identischem Zeitpunkt, BTC-Menge, Kurs und Gebühr bleiben deshalb getrennte Buchungen, sobald sich mindestens eine vorhandene ID unterscheidet. Nur dieselbe Import-ID gilt dann als Dublette. Ohne verwertbare ID bleibt der bisherige Vergleich aus Art, Zeitpunkt, Depot, BTC-Menge, Währung, Kurs und Gebühr als Fallback aktiv. Für bereits vor v0.21.0.4 importierte Buchungen ohne Import-ID wird beim ersten erneuten Import die vorhandene Anzahl gleicher Altbuchungen berücksichtigt, damit keine bestehenden Datensätze verdoppelt werden. Dubletten werden standardmäßig abgewählt und beim Speichern nochmals serverseitig geprüft.

Gebühren werden im Kaufbuch in der jeweiligen Fiat- beziehungsweise Handelswährung geführt. Wenn ein anbieterspezifischer Parser bei einem Verkauf eindeutig eine zusätzliche Gebühr in BTC/Sats ausweist, wird diese BTC-Menge zusätzlich zum eigentlichen Verkauf vom Stack abgezogen und ihr Fiat-Gegenwert im Gebührenfeld geführt. Dadurch gilt weiterhin `Nettoerlös = gesamte abgegangene BTC × Kurs − Fee`. Diese Behandlung wird nur dort automatisch angewendet, wo die Gebührenwährung und die Bedeutung der Spalten eindeutig sind (unter anderem Kraken Ledger, Binance Trade, CoinTracking/Pocket und Wavespace). Bei unklaren generischen Coin-Gebühren bleibt die Zeile zur manuellen Kontrolle markiert, statt die BTC-Menge blind zu verändern.

## Grenzen

- maximal 10 MiB pro Upload
- maximal 5.000 Datenzeilen pro Import
- bei einer ZIP-Datei wird die erste enthaltene CSV- oder TXT-Datei verwendet
- ausschließlich BTC beziehungsweise XBT
- keine automatische Steuerklassifizierung externer Transaktionstypen

## Datenschutz beim Import

Wallet-Adressen, Blockchain-TXIDs, Memos und Lightning-Rechnungen werden standardmäßig nicht in die Buchungsnotiz übernommen. Sofern ein Parser diese Felder erkennt, können sie oberhalb der Vorschautabelle ausdrücklich einzeln aktiviert werden. Die Auswahl ist bei jedem Import zunächst leer. Für die Dublettenerkennung wird eine vorhandene Order-/Trade-/Transaktions-ID nicht im Klartext im Ledger gespeichert; gespeichert wird nur ein lokaler SHA-256-Identitätswert. Die Roh-ID bleibt weiterhin nur dann in der Notiz, wenn sie im Import ausdrücklich ausgewählt wird.

## Wavespace-Ereigniserkennung

Wavespace verwendet keine feste Anzahl von Zeilen pro Vorgang. Ein Kauf kann nur aus `BUY` und `WITHDRAWAL` bestehen oder zusätzlich `DEPOSIT`, `APPLICATION_FEE`, `NETWORK_FEE` und `TRANSACTION` enthalten. Unabhängige Einzahlungen und Auszahlungen können dazwischenstehen.

Der Import verwendet deshalb `Transaction Type` als Grundlage:

- `CURRENCY_SWAP` mit EUR/Fiat → BTC/XBT: Bitcoin-Kauf
- `CURRENCY_SWAP` mit BTC/XBT → EUR/Fiat: Bitcoin-Verkauf
- `CARD_AUTHORIZATION` mit BTC → Fiat: Kartenereignis; echte Karteneinkäufe werden als **Ausgabe**, ATM-Bargeldabhebungen als **Verkauf** geführt
- `APPLICATION_FEE`: nur bei passender Währung und zeitlicher Nähe als Trading-/Kartengebühr
- `NETWORK_FEE`: nur zusammen mit einer passend erkannten On-Chain-Auszahlung
- `SEPA_PAYIN_DEPOSIT`, `LIGHTNING_DEPOSIT`, alleinstehende Auszahlungen, Rewards und technische Zeilen: keine eigene Kaufbuchung

Ist einem Kauf eine passende `LIGHTNING_WITHDRAW`- oder `ON_CHAIN_WITHDRAW`-Zeile zugeordnet, wird ausschließlich deren BTC-Wert aus `From Amount` als Wallet-Eingang gespeichert. Die Auszahlung muss zeitlich nahe liegen und darf nicht größer als der Bruttokauf sein. Andernfalls bleibt die BTC-Menge aus `CURRENCY_SWAP` erhalten, damit eine fremde oder spätere Auszahlung den Kauf nicht verfälscht.

Gebühren werden weiterhin bevorzugt aus `Memo` gelesen. Bei `Trading Fee for 1 EUR to BTC 0.1 EUR` wird der letzte Betrag, also `0.1 EUR`, verwendet. `Transaction ID`, `Memo` und `Transaction Type` sind optionale Notizfelder und bei jedem Import standardmäßig ausgeschaltet.


### Wavespace-Kartenerstellung

Zeilen mit `APPLICATION_FEE` und dem Memo `Application Fee for Card Creation` werden als eigene Buchungsart **Ausgabe** importiert. Sie zählen nicht zu den Kartenumsätzen und werden nicht an einen `CARD_AUTHORIZATION`-Vorgang angehängt.

Da Wavespace in diesen Zeilen keinen EUR-Betrag ausgibt, berechnet die Vorschau den damaligen Gegenwert zunächst aus der BTC-Menge und den lokal gespeicherten EUR/BTC-Tageskursen. Anschließend wird der bekannte Kartenpreis zugeordnet:

- virtuelle Karte: **2,99 EUR**
- physische Karte: **29,99 EUR**

Sind beide Kartenerstellungszeilen vorhanden, wird die kleinere BTC-Ausgabe der virtuellen und die größere der physischen Karte zugeordnet. Fehlt ein historischer Tageskurs, dient dieses Betragsverhältnis als Rückfall. In der Vorschau bleiben BTC-Menge, ermittelter Fiatwert, Depot und Notiz vollständig korrigierbar.

### Wavespace-Kartennutzung

Bei `CARD_AUTHORIZATION` wird zwischen Konsumausgabe und Bargeldabhebung unterschieden:

- `payWaveLowValuePurchase ...`, `POSPurchase ...`, `card purchase ...` oder `card payment ...` → Buchungsart **Ausgabe**
- `ATMWithdrawal ...` → **Verkauf / Bargeldabhebung**
- ein normaler `CURRENCY_SWAP` BTC → Fiat bleibt **Verkauf**

Beispielsweise wird `POSPurchase ... at REWE ...` als **Kartenzahlung bei REWE** / **Card payment at REWE** angezeigt. Eine im Memo oder einer zugeordneten `APPLICATION_FEE`-Zeile genannte BTC-Kartengebühr ist ein zusätzlicher Stack-Abgang: 100.000 sats Kartenumsatz plus 371 sats Fee ergeben 100.371 sats abgegangene BTC. Die Fee wird zugleich mit ihrem Fiat-Gegenwert separat gespeichert. Bewertete Ausgaben werden in der Rechenkontrolle wie Verkäufe behandelt, sodass `Fiat-Ausgabe = BTC-Abgang × Kurs − Fee` gilt. `Wavecard topup` ist dagegen nur eine interne Aufladung des Kartenkontos und wird nicht als zusätzlicher Verkauf oder zusätzliche Ausgabe angelegt.


## Rechenkontrolle für Beträge

Die Vorschau zeigt BTC/Sats-Menge, Preis pro BTC, Fiat-Gesamtbetrag und Fee nebeneinander. Zwei der drei Größen Menge, Kurs und Fiat-Gesamtbetrag reichen aus; die dritte Größe wird im Browser berechnet. Beim Kauf gilt `Fiat-Gesamtbetrag = BTC × Kurs + Fee`, beim Verkauf und bei einer bewerteten Ausgabe `Fiat-Gesamtbetrag = BTC × Kurs - Fee`. Sind alle Werte vorhanden und widersprechen sich, wird die Zeile zur Prüfung markiert. Der Kontrollbetrag wird nicht als zusätzliche Buchungswahrheit gespeichert, sondern vor dem Import gegen die weiterhin maßgeblichen Felder BTC-Menge, Kurs und Fee geprüft.

## Nachträgliche Korrektur importierter Buchungen

Nach dem Import können einzelne gespeicherte Buchungen direkt in der Buchungsliste über das Stift-Symbol korrigiert werden. Ein Löschen und erneutes Anlegen ist nicht erforderlich. Die stabile Buchungs-ID bleibt erhalten und FIFO wird vor dem Speichern erneut vollständig validiert.
