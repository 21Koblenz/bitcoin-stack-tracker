# Security Model · Bitcoin Stack Tracker v0.21.0.2
## Identität und Mehrbenutzerzugriff

Portfoliozugriffe werden einer **echten Home-Assistant-Benutzer-ID aus dem authentifizierten Request-Kontext** zugeordnet. Ein Client kann keine fremde `requester_user_id` vorgeben. System-generierte HA-Nutzer werden für Portfoliozugriffe abgewiesen.

Der Portfolio-Eigentümer kann weitere reale Home-Assistant-Nutzer freigeben. Im Passwortmodus muss jeder freigegebene Nutzer den Tresor in seiner eigenen Sitzung zusätzlich entsperren.

## Browser-/Panel-Grenze

Das native Home-Assistant-Panel und das Tracker-iframe kommunizieren über einen begrenzten `window.postMessage`-RPC-Kanal. Die Panel-Seite akzeptiert RPC-Nachrichten nur, wenn:

- `event.source` exakt dem aktuell eingebetteten Tracker-iframe entspricht,
- `event.origin` exakt der Home-Assistant-Origin entspricht,
- die interne RPC-Kennung stimmt.

Antworten werden nur an dieselbe Home-Assistant-Origin gesendet. Das Tracker-Dokument besitzt zusätzlich eine restriktive CSP mit `default-src 'none'`, `connect-src 'none'`, `form-action 'none'`, `object-src 'none'`, `base-uri 'none'` und `frame-ancestors 'self'`. Direkte Netzwerkaufrufe des Tracker-JavaScripts sind dadurch blockiert; Datenzugriffe laufen über Home Assistant Core.

Die Browser-Grenze setzt voraus, dass die Home-Assistant-Frontend-Origin selbst vertrauenswürdig ist. Ein kompromittierter Browser oder ein kompromittierter Home-Assistant-Host liegt außerhalb dieser Schutzgrenze.

## Kryptografie

- Ledger: AES-256-GCM mit zufälligen 96-Bit-Nonces und AAD.
- Passwort-KDF: Argon2id mit validierten Parametern.
- Envelope-Verschlüsselung: zufälliger Datenverschlüsselungsschlüssel (DEK), zusätzlich an einen separaten Core-Geräteschlüssel gebunden.
- Gerätegeheimnis: getrennt gespeichert und mit restriktiven Dateirechten geschützt.
- Portable Backups: eigenständig passwortverschlüsselt und nicht an eine bestimmte HA-Installation gebunden.
- Master- und Backup-Passwörter werden nicht dauerhaft gespeichert.

Ein Angreifer mit Root-/Hostkontrolle oder Schadcode im Browser eines gerade entsperrten Nutzers liegt außerhalb dieser Schutzgrenze.

## Portable Backups

Neue Backups enthalten ausschließlich:

1. Käufe und Verkäufe
2. Depots
3. Ziele
4. lokale Historie

Netzwerkziele, Tor-/Mempool-Einstellungen, HA-Zugriffslisten und Verschlüsselungseinstellungen werden nicht wiederhergestellt. Ältere Backup-Schemata können aus Kompatibilitätsgründen gelesen werden; darin enthaltene Installations-/Zugriffseinstellungen werden beim Restore ignoriert.

## Netzwerk und Tor

Öffentliche Datenabfragen sind fail-closed und benutzen Tor. Das Netzwerk-App-Modul besitzt keinen HA-API-Token und keinen Zugriff auf Portfolio-Dateien. nftables verwendet für `OUTPUT` und `INPUT` Default-Drop-Regeln.

- **9050/tcp:** ausschließlich Home Assistant Core / Bitcoin Stack Tracker.
- **9051/tcp:** bewusst geteilter interner Tor-SOCKS5-Port für andere Home-Assistant-Apps.
- **8099/tcp:** interner Health-Endpunkt.

Nur der Tor-Prozess darf öffentlichen Egress initiieren. Private/LAN- und Link-Local-Ziele werden auch für den Tor-Egress geblockt. Der Health-Agent darf selbst keinen neuen öffentlichen Egress initiieren. AppArmor beschränkt zusätzlich Host-/HA-Dateizugriffe und andere gefährliche Ressourcen.

## HTTP-Ressourcenlimits

Externe Providerantworten werden begrenzt eingelesen:

- JSON/Text: maximal 8 MiB
- Bulk-/ZIP-Daten: maximal 32 MiB
- Fehlertexte: maximal 4 KiB

Die Reader begrenzen auch Antworten ohne beziehungsweise mit falschem `Content-Length`. Native Panel-RPC-Requests werden ebenfalls hart begrenzt.

## Supply Chain

Die Integration pinnt ihre direkten Python-Abhängigkeiten exakt in `manifest.json` und `DEPENDENCIES.lock`. Von Home Assistant bereitgestellte Laufzeitpakete werden nicht unnötig überschrieben.

Das Tor Gateway pinnt die Home-Assistant-Base-Images auf konkrete OCI-SHA256-Digests. Die SBOM enthält dieselben Referenzen. Das GitHub-Release baut amd64 und aarch64 über den Home-Assistant-Builder und veröffentlicht ein signiertes Multi-Arch-Manifest über GitHub OIDC/Cosign.

## Schutzgrenzen

Geschützt wird insbesondere gegen nicht freigegebene HA-Nutzer, manipulierte verschlüsselte Dateien, direkten Clearnet-Fallback, ungewollte Backup-Wiederherstellung von Netzwerk-/Zugriffsparametern und mehrere Klassen von Ressourcen-/Importangriffen.

Nicht vollständig geschützt werden kann gegen einen kompromittierten HA-Host/Root-Account, einen kompromittierten Browser während einer entsperrten Sitzung oder die Weitergabe von Master-/Backup-Passwörtern.
