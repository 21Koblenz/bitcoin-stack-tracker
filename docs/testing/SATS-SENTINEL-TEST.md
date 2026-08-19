# Sats Sentinel – v0.21.0.9 Test-DROP-IN

Dieser Teststand basiert vollständig auf dem vorhandenen Bitcoin Stack Tracker **v0.21.0.9** inklusive der zuletzt getesteten Market-Assessment/Turning-Point-Erweiterungen. Die öffentliche Versionsnummer bleibt absichtlich `0.21.0.9`, bis Sats Sentinel lokal geprüft wurde.

## Enthalten

- eigene App-Seite **Sats Sentinel**
- dauerhafte Überwachung einzelner Bitcoin-Mainnet-Adressen
- neue Eingänge auf einer bereits bekannten Adresse werden automatisch erkannt
- alle später auf dieser Adresse entstehenden UTXOs bleiben überwacht
- Ausgänge werden erkannt und gemeldet
- Wallet-interne Change-Ausgaben eines XPUB-Monitors werden pro TXID zusammengefasst statt doppelt gemeldet
- XPUB / YPUB / ZPUB mit nicht-hardened Receive-/Change-Ableitung
- einfache Single-Key-Descriptoren: `pkh()`, `wpkh()`, `sh(wpkh())`
- Receive-/Change-Reserve separat einstellbar: **0–20**, UI-Default **2 + 2**
- keine XPUB-/Descriptor-Daten im 24/7-Runtime-Cache
- Runtime-Cache: AES-256-GCM, device-bound, separater HKDF-Kontext
- vollständige Watch-Konfiguration liegt im normalen Tracker-Tresor
- Sats Sentinel mit Watch-Zielen erfordert Passwortverschlüsselung des Tresors
- Passwortverschlüsselung kann nicht deaktiviert werden, solange Watch-Ziele existieren
- beim Sperren/Auto-Lock werden geladene Watch-Daten aus dem Browserzustand entfernt
- eigene lokale mempool-Instanz wird bevorzugt
- öffentliche mempool-Quelle nur nach expliziter Freigabe und ausschließlich über die vorhandene Tor-Fail-Closed-Route
- **kein Clearnet-Fallback**
- Home-Assistant Event: `bitcoin_stack_tracker_wallet_activity`
- Status-Event: `bitcoin_stack_tracker_wallet_monitor_status`
- persistente HA-Benachrichtigung
- auswählbare vorhandene `notify.*`-Dienste (z. B. Home-Assistant-Mobile-App)
- Benachrichtigungsdetails: Diskret / Normal / Detailliert
- Ausfallalarm nach mehreren fehlgeschlagenen Prüfungen
- bestehende Historie erzeugt beim ersten Baseline-Abgleich keinen Fehlalarm

## Datenschutzmodell

Vollständige Adressen, XPUBs, Descriptoren, Namen und Einstellungen liegen im normalen Tracker-Tresor. Für die Überwachung bei gesperrtem Tresor wird ein separater verschlüsselter Minimal-Cache erzeugt. Bei XPUB/Descriptor enthält dieser nur die konkret vorab abgeleiteten Adressen, nicht den XPUB oder Descriptor selbst.

Eine explizit eingetragene Einzeladresse muss naturgemäß im 24/7-Monitor verfügbar sein, damit auch zukünftige Eingänge auf exakt dieser Adresse erkannt werden können. Der Runtime-Cache ist deshalb device-bound verschlüsselt und wird nach einem Neustart automatisch wieder geöffnet.

Bei Verwendung einer öffentlichen mempool-Instanz verbirgt Tor die Anschluss-IP, aber der Betreiber der öffentlichen Instanz kann die abgefragten Bitcoin-Adressen sehen. Für maximale Privatsphäre eine eigene lokale mempool-Instanz verwenden.

## Unterstützte Watch-Daten

- Mainnet Einzeladresse: Legacy, P2SH, SegWit, Taproot
- `xpub` → P2PKH
- `ypub` → P2SH-P2WPKH
- `zpub` → P2WPKH
- Descriptoren mit `pkh()`, `wpkh()` oder `sh(wpkh())`, optional mit Origin und `/0/*` bzw. `/1/*`

Private Schlüssel, Seeds und xprv/yprv/zprv werden nicht unterstützt.

## Lokaler Test

1. Bestehenden `bitcoin_stack_tracker` sichern.
2. Inhalt des CUSTOM-COMPONENT-ZIPs nach `/config/custom_components/` entpacken bzw. den Ordner `bitcoin_stack_tracker` ersetzen.
3. Home Assistant Core neu starten.
4. Tracker-Tresor entsperren und sicherstellen, dass Passwortverschlüsselung aktiv ist.
5. **Sats Sentinel** öffnen.
6. Zuerst eine eigene lokale mempool-Instanz verwenden, sofern vorhanden.
7. Einzeladresse hinzufügen, Eingänge und Ausgänge aktiviert lassen und speichern.
8. Ersten Baseline-Abgleich abwarten/„Jetzt prüfen“ drücken – bestehende Historie darf keine Bewegungsmeldung erzeugen.
9. Danach mit einer Testadresse einen neuen Eingang/Ausgang prüfen.
10. Gewünschten `notify.mobile_app_*`-Dienst auswählen, wenn zusätzlich zur persistenten HA-Meldung Push gewünscht ist.

## QA

- bestehende Suite: **398 Tests + 8 Subtests bestanden**
- Python-Syntax aller Integration-Dateien geprüft
- JavaScript-Syntax geprüft
- unabhängiger BIP32-Public-Derivation-Gegencheck bestanden
- zpub/wpkh-Descriptor-Smoke-Test bestanden
- bestätigt: XPUB/Descriptor werden nicht in den Runtime-Cache übernommen


## Benachrichtigungen

- mehrere Home-Assistant `notify.*`-Dienste gleichzeitig
- mehrere selbst gehostete `ntfy`-Ziele gleichzeitig
- mehrere Webhook-Ziele gleichzeitig
- jedes externe Ziel kann `Diskret`, `Normal` oder `Detailliert` verwenden
- `Diskret` überträgt keine Richtung, Beträge, TXID, Adresse oder Monitor-ID
- lokale Ziele dürfen direkt im LAN angesprochen werden
- öffentliche und Onion-Ziele laufen ausschließlich über Tor; kein Clearnet-Fallback
- ein fehlerhaftes Ziel blockiert die übrigen Benachrichtigungskanäle nicht


## Nicht-invasive Bewegungssimulation

Die Seite **Sats Sentinel → Testlabor** kann einen künstlichen Eingang oder Ausgang durch denselben Home-Assistant-Event- und Benachrichtigungspfad schicken wie eine echte erkannte Bewegung. Die Meldung ist als **TEST** markiert. Dabei werden keine UTXOs, Salden, Baseline-Daten oder Blockchain-Daten verändert.

Ein beliebiger fremder Mempool-Transfer ist kein zuverlässiger Sentinel-Test: Eine echte Erkennung darf nur dann auslösen, wenn eine überwachte Adresse an der Transaktion beteiligt ist. Beim erstmaligen Hinzufügen einer bereits aktiven fremden Adresse wird außerdem bewusst eine Baseline erstellt, damit alte Historie keinen Fehlalarm auslöst.


## Live-Test mit einer fremden Mempool-Transaktion

Zusätzlich kann eine beliebige öffentliche 64-stellige Bitcoin-TXID im **Live Mempool Test** verwendet werden. Sats Sentinel lädt die echte Transaktion über die normale erlaubte Datenroute, wertet wahlweise eine Input-Adresse als Ausgang oder eine Output-Adresse als Eingang aus und schickt das Ergebnis als klar markierte TEST-Meldung durch denselben Alarmweg. Die TXID wird dadurch nicht als eigene Wallet oder Baseline gespeichert. Eine eigene lokale mempool-Instanz wird bevorzugt; eine öffentliche Quelle funktioniert nur bei aktivierter Tor-Erlaubnis und besitzt keinen Clearnet-Fallback.


## Source exclusivity v3

- If an own mempool instance is configured, Sats Sentinel uses only the first configured own mempool source.
- If that node is unavailable, Sentinel becomes offline. It never falls back to mempool.space or any other public source, including over Tor.
- Public mempool over Tor is only possible when no own mempool instance is configured and the user explicitly opts in.

## Live-price fast lane is not a Sentinel fallback

The dashboard may use faster additional Tor-routed public **price** sources. These sources are never promoted to Sats Sentinel blockchain sources. With an own mempool instance configured, Sats Sentinel remains own-node-exclusive and stops when that node is unavailable.

## v9: Self-hosted mempool without `/utxo`

Sats Sentinel no longer requires `GET /api/address/:address/utxo`.
For monitoring it uses the address summary plus `GET /api/address/:address/txs`.
Balance and the displayed UTXO/output count are derived from the summary's
`chain_stats` and `mempool_stats` (`funded_txo_*` minus `spent_txo_*`).
This keeps own-node-only routing intact and reduces sensitive runtime data,
because the concrete UTXO set is no longer stored in the Sentinel cache.

## Quellenregel v10: konfigurierte Public-/Onion-Nodes

- Eigene lokale/private Mempool-Node: exklusiv und direkt im LAN.
- Eigene/custom `.onion`-Node: exklusiv, ausschließlich über den gebündelten Tor-SOCKS-Proxy mit Remote-DNS.
- Ohne eigene/custom Node kann Sats Sentinel die **erste bereits im Tracker konfigurierte öffentliche Mempool-Quelle** verwenden, aber nur wenn `allow_public_tor` aktiviert ist.
- Es wird **kein implizites mempool.space-Fallback** erzeugt und nicht zwischen mehreren öffentlichen Providern kaskadiert; dadurch werden Watch-Adressen nicht unnötig mehreren Anbietern offengelegt.
- Fällt eine ausgewählte eigene/custom Node aus, bleibt Sentinel offline.

## v11 movement journal and live status

- Sentinel status is refreshed locally from Home Assistant every 15 seconds while the Sentinel page is open. This does not trigger an additional blockchain request.
- The UI shows both the last successful poll and the last poll attempt.
- Every real detected movement is written to the encrypted device-bound activity journal before per-monitor notification filters are evaluated.
- Journal display can be limited by days or entry count without deleting older stored entries, or shown unlimited with 25 entries per page.
- Journal filters: own address, exchange, interesting, hacker/incident, other.
- Watch entries are editable after creation and support category, note, per-entry minimum alert amount, direction filters and per-entry channel switches (HA event, persistent HA notification, selected notify services, external ntfy/webhooks).
- A movement below the alert threshold remains in the local journal but does not send an active alert.

## v12 – Journal navigation, readable watch rules, partial poll health

- Movement Journal remains capped at 25 movements per page but now has first/previous/direct page selector/next/last navigation.
- Counterparty display can show 1, 3, 5 or up to 12 addresses per movement without changing journal retention.
- Watch cards render Monitoring, Incoming alert, Outgoing alert, Alert threshold and Alert channels as separate readable fields instead of a compact symbol string.
- A timeout on a single address transaction-history request no longer marks the entire Sats Sentinel source offline if the node summary endpoint is reachable.
- Transaction-history requests use a 45 second timeout. Incomplete per-address checks are retried on the next poll and exposed as a partial warning while other watch targets continue.
- Provider/source fail-closed rules are unchanged.


## TLS certificate pinning + destructive monitor removal

- Self-signed Fulcrum/electrs TLS can use an explicitly pasted PEM server certificate.
- The main encrypted vault keeps the public PEM; the device-bound runtime cache keeps only its SHA-256 fingerprint.
- TLS pin mode compares the peer certificate from the live handshake with the configured SHA-256 fingerprint.
- Private-key PEM blocks are rejected.
- Removing a watch monitor now immediately persists the updated Sentinel configuration and permanently removes every journal row whose `monitor_id` belongs to that removed monitor.
- XPUB/descriptor removal also removes all derived runtime addresses for that monitor.
