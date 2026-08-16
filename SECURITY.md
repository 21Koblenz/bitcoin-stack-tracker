# Security Model · Bitcoin Stack Tracker v0.21.0.12

Dieses Dokument beschreibt die Schutzgrenzen des Projekts. Der grundlegende Security-Audit aus v0.21.0.6 bleibt für v0.21.0.7 maßgeblich; v0.21.0.7 ändert primär CSV-Import, Gebührenanalyse und Repository-CI. Der Audit ist ein **Code-, Datenfluss- und Regressionstest-Audit** und kein externer Penetrationstest.

## Identität und Mehrbenutzerzugriff

Portfoliozugriffe werden ausschließlich einer echten Home-Assistant-Benutzer-ID aus dem authentifizierten Request-/Service-Kontext zugeordnet. Ein Client kann keine fremde `requester_user_id` als Identität vorgeben. System-generierte HA-Nutzer werden für Portfoliozugriffe abgewiesen.

Der Eigentümer kann reale Home-Assistant-Nutzer freigeben. Im Passwortmodus muss ein freigegebener Nutzer den Tresor zusätzlich in seiner eigenen Sitzung entsperren. Owner-only-Funktionen bleiben separat geschützt.

## Browser-/Panel-Grenze

Das native Home-Assistant-Panel und das Tracker-iframe kommunizieren über einen begrenzten `window.postMessage`-RPC-Kanal. Nachrichten werden nur akzeptiert, wenn `event.source` dem aktuell eingebetteten iframe entspricht, `event.origin` exakt der Home-Assistant-Origin entspricht und die interne RPC-Kennung stimmt.

Das Tracker-Dokument verwendet eine restriktive Content Security Policy mit unter anderem `default-src 'none'`, `connect-src 'none'`, `object-src 'none'`, `base-uri 'none'`, `form-action 'none'` und `frame-ancestors 'self'`. Direkte öffentliche Netzwerkaufrufe aus dem Tracker-JavaScript sind damit blockiert; Datenzugriffe laufen über Home Assistant Core.

Das iframe ist bewusst Bestandteil derselben vertrauenswürdigen Home-Assistant-Origin und **keine separate opaque-origin Sandbox**. Ein kompromittierter Home-Assistant-Host oder kompromittierter Browser während einer entsperrten Sitzung liegt außerhalb dieser Schutzgrenze.

## Datenminimierung im Frontend

Nach dem Entsperren wird zunächst nur eine kompakte Dashboard-Zusammenfassung geladen.

- **Übersicht/Charts:** reduzierte Rechenereignisse ohne Notizen, Provider-/Order-IDs, `import_ref_hash` oder interne Ledger-UUIDs.
- **Buchungen:** vollständige für die Buchungsansicht nötige Ledger-Felder werden erst beim Öffnen dieses Reiters geladen. Eine Allow-List verhindert, dass interne Felder wie `import_ref_hash` oder `fee_btc` versehentlich mitgesendet werden.
- **FIFO/Haltezeit:** display-only FIFO-Daten; interne Ledger-IDs werden für die Anzeige nicht benötigt.
- **CSV-Dublettenprüfung:** findet seit v0.21.0.6 vollständig in Home Assistant Core statt. Bestehende Import-Hashes verlassen Core nicht; das Frontend erhält nur boolesche Dubletten-Flags. Die Prüfanfrage ist zusätzlich rate-limitiert.

Authentifizierte Panel-Antworten werden mit `Cache-Control: no-store, private, max-age=0`, `Pragma: no-cache`, `Cross-Origin-Resource-Policy: same-origin`, `Referrer-Policy: no-referrer` und `X-Content-Type-Options: nosniff` ausgeliefert. Veraltete Lazy-Responses werden anhand einer lokalen Revision verworfen.

## Lokaler Browser-Speicher

`localStorage` wird nur für UI-/Sitzungspräferenzen verwendet, zum Beispiel Sprache, Theme, BTC/Sats-Einheit, Chartmodus/-skalen, aktiven Reiter, Diskretmodus, Auto-Lock-Minuten und die ausgewählte Portfolio-ID.

Nicht in `localStorage` gespeichert werden Master-/Backup-Passwörter, Ledgerzeilen, Notizen, Import-Hashes, Provider-IDs oder konkrete Transaktionsbeträge. Während einer entsperrten Sitzung liegen die für die aktuelle Ansicht benötigten Daten zwangsläufig im Browser-RAM.

## Kryptografie

- Ledger-Verschlüsselung: AES-256-GCM mit zufälligen 96-Bit-Nonces, 128-Bit-Tag und AAD.
- Passwort-KDF: Argon2id; das aktuelle Profil verwendet 128 MiB Speicher, drei Iterationen und Parallelität 1.
- Schlüsseltrennung: HKDF-SHA-512; ein zufälliger 256-Bit-DEK verschlüsselt die Nutzdaten und wird durch einen KEK geschützt.
- Geräteschlüssel: separat in Home Assistant gespeichert und mit restriktiven Dateirechten angelegt. Ein fehlender Geräteschlüssel wird nicht stillschweigend neu erzeugt.
- Portable `.bstbackup`-Backups besitzen absichtlich eine eigene passwortbasierte, geräteunabhängige Verschlüsselung, damit sie auf einer anderen Installation wiederhergestellt werden können.
- Neue Tresorpasswörter müssen mindestens 16 Zeichen lang sein.

Master- und Backup-Passwörter werden nicht dauerhaft gespeichert. Seed-Wörter, Wallet-Passphrasen oder Private Keys gehören niemals in den Tracker.

## Netzwerk und Tor

Portfolio-, Ledger-, Ziel- und Tresordaten werden nicht an öffentliche Kursanbieter gesendet. Öffentliche Kurs-/Historienquellen werden über das getrennte Tor Gateway angesprochen. Explizit konfigurierte lokale Node-/Mempool-Ziele dürfen direkt im LAN angesprochen werden.

Das Tor Gateway ist ein getrenntes Modul und hat keinen Zugriff auf Tracker-Ledger, Tresorpasswort oder Home-Assistant-API-Token. Seine eigene Version bleibt bei diesem Integrationsrelease **v0.21.0.3**.

## Eingabe-/Mutationsschutz

- maximale Ledger-, Depot-, Ziel- und Statistikgrößen sind begrenzt;
- Bulk-Import und Dublettenprüfung sind auf 5.000 Zeilen pro Aufruf begrenzt;
- sicherheitsrelevante/schwere Endpunkte besitzen Rate-Limits;
- Add/Edit/Delete/Bulk-Import werden vor dem Persistieren gegen FIFO-Oversell validiert und bleiben atomar;
- neue oder bearbeitete Ledgerbuchungen dürfen nicht mehr als fünf Minuten in der Zukunft liegen, da der Tracker keine geplanten zukünftigen Buchungen modelliert;
- Backup-Importe werden strukturell validiert und dürfen keine Netzwerk-/Tor-/Berechtigungskonfiguration aus dem portablen Backup überschreiben.

## Verbleibende Annahmen

Die Sicherheitsarchitektur setzt einen vertrauenswürdigen Home-Assistant-Core, dessen Dateisystem, die HA-Frontend-Origin und das Endgerät voraus. Der Tracker schützt nicht gegen einen bereits kompromittierten Host, Browser oder Administrator. Für eine unabhängige Sicherheitszertifizierung wären zusätzlich externe Penetrationstests und eine getrennte Codeprüfung durch Dritte nötig.
