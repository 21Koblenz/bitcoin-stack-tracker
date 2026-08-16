# Bitcoin Stack Tracker v0.21.0.12 — Sats Sentinel HD-Wallet Reliability

## English

v0.21.0.12 is a maintenance release focused on making Sats Sentinel reliable with real HD watch-only wallets.

### Highlights
- Receive and Change are now independent true gap limits: all used addresses stay monitored, followed by the configured consecutive-unused reserve.
- XPUB/YPUB/ZPUB/descriptor discovery survives startup/reload and no longer collapses back to `Receive N + Change N`.
- Fulcrum/Electrum settings, derived runtime coverage and saved watch targets persist across Home Assistant restarts.
- XPUB/descriptor saves are non-blocking: the encrypted configuration is saved immediately and the potentially long Fulcrum gap scan continues as a Home Assistant background task.
- Newer saves supersede older pending scans, preventing stale discovery results from overwriting the newest configuration.
- Watch-card Balance and the transaction view's Current wallet balance are kept in sync; the transaction overview becomes the authoritative frontend value when loaded.
- Balance, UTXOs and transaction discovery use the same active used-address + gap set; inactive standby addresses are excluded.
- The stable frontend filenames introduced in v0.21.0.11 remain permanent. **Nothing needs to be deleted from GitHub for this release.**

### Privacy
Raw XPUB/descriptor secrets remain in the password-protected vault. The device-bound runtime cache contains only concrete pre-derived addresses required for locked-vault monitoring.

### Validation
- **502 tests + 8 subtests passed**
- Python compile passed
- JavaScript syntax passed
- JSON/SBOM and release-integrity checks passed
- Custom Integration: **v0.21.0.12**
- Tor Gateway: **v0.21.0.3** unchanged

---

## Deutsch

v0.21.0.12 ist ein Wartungsrelease mit Fokus auf einen zuverlässigen Sats Sentinel für echte HD-Watch-only-Wallets.

### Highlights
- Receive und Change sind jetzt getrennte echte Gap-Limits: Alle benutzten Adressen bleiben überwacht, danach folgt jeweils die eingestellte Reserve aufeinanderfolgender unbenutzter Adressen.
- Die XPUB/YPUB/ZPUB-/Descriptor-Erkennung überlebt Start/Reload und fällt nicht mehr auf `Receive N + Change N` zurück.
- Fulcrum-/Electrum-Einstellungen, abgeleitete Runtime-Abdeckung und gespeicherte Watch-Ziele bleiben über Home-Assistant-Neustarts erhalten.
- XPUB-/Descriptor-Speichern blockiert nicht mehr: Die verschlüsselte Konfiguration wird sofort gespeichert und der möglicherweise lange Fulcrum-Gap-Scan läuft danach als Home-Assistant-Hintergrundtask weiter.
- Neuere Speichervorgänge ersetzen ältere noch laufende Scans, damit veraltete Ergebnisse keinen neueren Konfigurationsstand überschreiben.
- Der Bestand der Watch-Karte und der „Aktuelle Wallet-Bestand“ der Transaktionsübersicht bleiben synchron; nach dem Laden ist die Transaktionsübersicht der maßgebliche Frontend-Wert.
- Bestand, UTXOs und TX-Erkennung verwenden denselben aktiven Satz aus benutzten Adressen + Gap; inaktive Standby-Adressen werden ausgeschlossen.
- Die stabilen Frontend-Dateinamen aus v0.21.0.11 bleiben dauerhaft. **Für dieses Release muss bei GitHub nichts gelöscht werden.**

### Datenschutz
Rohe XPUB-/Descriptor-Geheimnisse bleiben im passwortgeschützten Tresor. Der gerätegebundene Runtime-Cache enthält nur konkret vorab abgeleitete Adressen, die für die Überwachung bei gesperrtem Tresor benötigt werden.

### Prüfung
- **502 Tests + 8 Subtests bestanden**
- Python-Compile bestanden
- JavaScript-Syntax bestanden
- JSON-/SBOM- und Release-Integritätsprüfungen bestanden
- Custom Integration: **v0.21.0.12**
- Tor Gateway: **v0.21.0.3** unverändert

Full changelog / Vollständiger Changelog: `CHANGELOG.md`
