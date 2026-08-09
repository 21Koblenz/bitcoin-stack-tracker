# CSV-Import

Der CSV-Import befindet sich im Dashboard unter **Buchungen**. Er übernimmt ausschließlich Bitcoin-Käufe und Bitcoin-Verkäufe. Einzahlungen, Auszahlungen, interne Transfers, Altcoins und sonstige Kontobewegungen werden nicht automatisch als Kauf oder Verkauf gespeichert.

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
- Im Kaufbuch landen nur bestätigte Felder für Kauf oder Verkauf. Dateiname, vollständige Originalzeile und CSV-Inhalt werden nicht gespeichert.

## Direkt erkannte Formate

- Coinbase Transaction History
- Kraken Trades History
- Kraken Ledgers History
- Binance Trade History
- Binance Transaction History / Transaction Record
- CoinTracking Universal CSV
- Coinfinity „My Activities“ mit On-Chain- und Lightning-Auszahlungen

Beim aktuellen Coinfinity-Format wird `Amount Crypto` als Satoshi-Betrag interpretiert und für die Vorschau in BTC umgerechnet. Das gilt auch für `Mining Fee Crypto`. Als Fiatgebühr wird `Total Fee EUR` übernommen; fehlt dieser Wert, setzt sich die Gebühr aus `Mining Fee EUR` und `Service Fee EUR` zusammen. Die Aufschlüsselung sowie Lightning oder On-Chain erscheinen zusätzlich in der editierbaren Notiz. Die exportierte BTC-Menge wird nicht eigenmächtig um die Mining Fee verändert.

Für Relai, Bittr/getbittr und Wavespace gibt es eine flexible Broker-Erkennung anhand des Dateinamens und üblicher Spaltenbezeichnungen. Pocket Bitcoin wird in zwei eigenen Varianten unterstützt: dem CoinTracking-kompatiblen Export (`Type, Buy Amount, Buy Cur., ...`) und dem nativen Pocket-Dashboard-Export (`type,date,reference,price.currency,...`). Beim CoinTracking-kompatiblen Pocket-Export ist eine Fiat-Gebühr bereits im `Sell Amount` enthalten: für den Ausführungskurs wird deshalb `Sell Amount - Fee Amount` verwendet, während die Gebühr separat erhalten bleibt. So entspricht der gesamte Einstand weiterhin exakt dem tatsächlich eingezahlten Fiatbetrag. Bei einer CoinTracking-`Withdrawal` ist der Wallet-Eingang `Sell Amount - Fee Amount`, wenn die Gebühr in BTC/Sats angegeben ist. Mehrere Käufe dürfen in einer einzigen Pocket-Auszahlung gebündelt werden: Der Parser sortiert Trade und Withdrawal chronologisch, sammelt alle noch nicht ausgezahlten Käufe seit der vorherigen Withdrawal und verteilt den Netto-Walletbetrag proportional nach BTC-Menge auf diesen Block. Dadurch funktionieren auch Auszahlungen nach Mitternacht (z. B. 01:55 oder 02:24 Uhr), ohne einen späteren Kauf nach der Auszahlung fälschlich einzubeziehen. Beim nativen Pocket-Dashboard-CSV ist dagegen `value.amount` bereits der Netto-Walletbetrag und wird nicht noch einmal um `fee.amount` reduziert. Werden dort mehrere Käufe in einer Withdrawal zusammen ausgezahlt, sammelt der Parser ebenfalls alle Käufe seit der vorherigen Withdrawal, auch über Mitternacht hinweg, und verteilt `value.amount` proportional nach Brutto-BTC auf diese Käufe. Der jeweilige Anteil der gemeinsamen Netzwerkgebühr ergibt sich aus der Differenz zwischen Brutto- und Netto-BTC und wird mit dem Kaufkurs des jeweiligen Trades in Fiat berücksichtigt. Bei Pocket erzeugt nur der eigentliche Trade/Kauf eine Buchung; Deposit und Withdrawal werden als Transfers behandelt. Andere Anbieter werden über den generischen Bitcoin-CSV-Parser erkannt, sofern die Datei verständliche Felder für Art, Datum, BTC-Menge sowie Fiatbetrag oder BTC-Kurs enthält.

Da Anbieter ihre Exportformate ändern können, ist die Vorschau immer verbindlich. Eine Zeile mit fehlenden oder widersprüchlichen Werten wird nicht automatisch ausgewählt und muss vor dem Import korrigiert werden.

## Dubletten und Gebühren

Eine Buchung gilt als Dublette, wenn Art, Zeitpunkt, Depot, BTC-Menge, Währung, Kurs und Gebühr mit einer vorhandenen oder bereits ausgewählten Buchung übereinstimmen. Dubletten werden standardmäßig abgewählt und beim Speichern nochmals serverseitig geprüft.

Gebühren werden im Kaufbuch in der jeweiligen Fiat- beziehungsweise Handelswährung geführt. Erkennt der Parser eine Gebühr in BTC oder einer anderen Coin-Währung, wird die Gebühr nicht ungeprüft übernommen, sondern auf `0` gesetzt und die Zeile zur manuellen Kontrolle markiert.

## Grenzen

- maximal 10 MiB pro Upload
- maximal 5.000 Datenzeilen pro Import
- bei einer ZIP-Datei wird die erste enthaltene CSV- oder TXT-Datei verwendet
- ausschließlich BTC beziehungsweise XBT
- keine automatische Steuerklassifizierung externer Transaktionstypen

## Datenschutz beim Import

Wallet-Adressen, Blockchain-TXIDs, Memos und Lightning-Rechnungen werden standardmäßig nicht in die Buchungsnotiz übernommen. Sofern ein Parser diese Felder erkennt, können sie oberhalb der Vorschautabelle ausdrücklich einzeln aktiviert werden. Die Auswahl ist bei jedem Import zunächst leer.

## Wavespace-Ereigniserkennung

Wavespace verwendet keine feste Anzahl von Zeilen pro Vorgang. Ein Kauf kann nur aus `BUY` und `WITHDRAWAL` bestehen oder zusätzlich `DEPOSIT`, `APPLICATION_FEE`, `NETWORK_FEE` und `TRANSACTION` enthalten. Unabhängige Einzahlungen und Auszahlungen können dazwischenstehen.

Der Import verwendet deshalb `Transaction Type` als Grundlage:

- `CURRENCY_SWAP` mit EUR/Fiat → BTC/XBT: Bitcoin-Kauf
- `CURRENCY_SWAP` mit BTC/XBT → EUR/Fiat: Bitcoin-Verkauf
- `CARD_AUTHORIZATION` mit BTC → Fiat: Kartenumsatz und damit Bitcoin-Verkauf
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

`CARD_AUTHORIZATION` mit BTC → Fiat wird als Bitcoin-Verkauf importiert. Das Memo bestimmt den Hinweistext:

- `POSPurchase ... at REWE ...` → **Kartenzahlung bei REWE** / **Card payment at REWE**
- `ATMWithdrawal ... at SPARKASSE ...` → **Bargeldabhebung bei SPARKASSE** / **Cash withdrawal at SPARKASSE**

Eine im Memo genannte `application fee of ... BTC` wird als Kartengebühr berücksichtigt. `Wavecard topup` ist dagegen nur eine interne Aufladung des Kartenkontos und wird nicht als zusätzlicher Verkauf angelegt.


## Rechenkontrolle für Beträge

Die Vorschau zeigt BTC/Sats-Menge, Preis pro BTC, Fiat-Gesamtbetrag und Fee nebeneinander. Zwei der drei Größen Menge, Kurs und Fiat-Gesamtbetrag reichen aus; die dritte Größe wird im Browser berechnet. Beim Kauf gilt `Fiat-Gesamtbetrag = BTC × Kurs + Fee`, beim Verkauf `Fiat-Gesamtbetrag = BTC × Kurs - Fee`. Sind alle Werte vorhanden und widersprechen sich, wird die Zeile zur Prüfung markiert. Der Kontrollbetrag wird nicht als zusätzliche Buchungswahrheit gespeichert, sondern vor dem Import gegen die weiterhin maßgeblichen Felder BTC-Menge, Kurs und Fee geprüft.

## Nachträgliche Korrektur importierter Buchungen

Nach dem Import können einzelne gespeicherte Buchungen direkt in der Buchungsliste über das Stift-Symbol korrigiert werden. Ein Löschen und erneutes Anlegen ist nicht erforderlich. Die stabile Buchungs-ID bleibt erhalten und FIFO wird vor dem Speichern erneut vollständig validiert.
