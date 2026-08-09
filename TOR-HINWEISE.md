# Tor- und mempool-Hinweise

## Integrierter Proxy

Das **Bitcoin Stack Tracker Tor Gateway** enthält den Tor-Client und startet ihn beim App-Start. Home Assistant Core erreicht den SOCKS5-Port der Repository-Installation über:

```text
socks5://20c000e9-bitcoin-stack-tracker-dashboard:9050
```

Es ist keine separate Tor-Installation auf Home Assistant oder dem RaspiBlitz erforderlich. Stoppt Tor oder ist das interne Gateway nicht erreichbar, bleibt das native Tracker-Dashboard verfügbar und wechselt in den Modus **nur lokal und Cache**. Livepreise sowie öffentliche und Onion-Aktualisierungen werden blockiert; eine direkte Clearnet-Ersatzverbindung ist nicht vorhanden.

Beim Start zeigt das Dashboard den tatsächlichen Tor-Aufbau in Prozent an. Erst bei 100 % wird die öffentliche Tor-Ausgangsverbindung geprüft. Der Tor-Verzeichnis- und Guard-Cache liegt geschützt unter `/data/tor`, damit ein App-Neustart normalerweise nicht wieder das vollständige Tor-Verzeichnis laden muss.

## Feste Routing-Regel

- Livepreis-Marktmittelwert aus Kraken, Coinbase Exchange, Bitstamp und CoinGecko: nur Tor.
- Kraken-, CoinGecko-, Blockchain.com-, EZB- und öffentliche mempool-Historie: nur Tor.
- Öffentliche mempool-Livepreise: nur Tor.
- Eigene `.onion`-mempool-Instanz: nur Tor.
- Eigene private lokale mempool-Instanz, zum Beispiel `192.168.x.x`, `10.x.x.x` oder `*.home.arpa`: direkt im LAN.
- Home-Assistant-Preis-Entity: wird lokal gelesen; deren zugrunde liegende Integration liegt außerhalb der Kontrolle des Trackers.

Ist Tor nicht erreichbar, schlägt die öffentliche Abfrage fehl. Es existiert kein Clearnet-Fallback.

## Eigene mempool-Instanz

Eine als eigene Instanz markierte Quelle wird zuerst abgefragt und bleibt bei Überschneidungen bevorzugt. Für ältere fehlende Zeiträume arbeitet der Tracker anschließend die Quellenkaskade ab:

```text
<BASIS-URL>/api/v1/historical-price?currency=EUR
```

und für den Livepreis ausschließlich über die öffentliche Tor-Route:

```text
<BASIS-URL>/api/v1/prices
```

Bei einer privaten lokalen Adresse erfolgt diese Verbindung direkt. Bei einer Onion- oder sonstigen nichtlokalen Adresse erfolgt sie automatisch über Tor.

## Datenbeschaffung der mempool-Instanz selbst

Der Tracker kontrolliert nur seine Verbindung zur eigenen Instanz. Wenn das mempool-Backend selbst Börsenkurse aus dem Internet lädt, muss dessen eigener Ausgang ebenfalls auf Tor gestellt werden:

```json
"SOCKS5PROXY": {
  "ENABLED": true,
  "HOST": "127.0.0.1",
  "PORT": "9050",
  "USERNAME": "",
  "PASSWORD": ""
}
```

Danach das mempool-Backend neu starten und dessen Log prüfen.


## Only-Tor-Killswitch und Leak-Test

- Nur der gebündelte Tor-Systemnutzer darf aus dem Add-on öffentliche IPv4-/IPv6-Sockets öffnen.
- Dashboard und Hilfsprozesse dürfen direkt nur Loopback und private Netze erreichen.
- DNS-Port 53 ist für den Dashboard-Nutzer gesperrt; öffentliche Namen gehen mit Remote-DNS an Tor.
- Fällt Tor aus, bleiben Cache, Portfolio und lokale Node verfügbar. Livepreis und externe Synchronisierung bleiben aus.
- Der Leak-Test unter **Einstellungen → Tor-Killswitch & Leak-Test** prüft ohne direkte Clearnet-Testanfrage.
- Ein steigender Zähler für blockierte Direktpakete bedeutet, dass der Killswitch einen Verbindungsversuch abgefangen hat.
