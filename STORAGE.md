# Lokale Speicherung und Verschlüsselungsprüfung

Jedes Portfolio besitzt eine Home-Assistant-Config-Entry-ID. Sie steht in der Diagnosedatei unter `config_entry_id` und wird im Dashboard-App-Log gekürzt angezeigt. Für die Dateiprüfung wird die vollständige ID benötigt.

## Kaufbuch, Depots, Ziele und private Chartwerte

Home Assistant speichert die Portfolio-Nutzlast unter:

```text
/config/.storage/bitcoin_stack_tracker.ledger.<CONFIG_ENTRY_ID>
```

Darin befinden sich gemeinsam:

- Käufe, Verkäufe und Bestände ohne Einstand;
- Depots und Ziele;
- Haltezeit-Einstellungen;
- der lokal berechnete Stack- und Portfoliowert-Verlauf (`chart_cache`).

Die Datei darf bei laufendem Home Assistant nur gelesen, niemals manuell bearbeitet werden. Manuelle Änderungen können die Storage-Datei oder ihre Integritätsprüfung beschädigen.

### Passwortverschlüsselung prüfen

Im Terminal-/SSH-App ausführen und die ID ersetzen:

```bash
FILE="/config/.storage/bitcoin_stack_tracker.ledger.<CONFIG_ENTRY_ID>"; jq '.data | {encrypted,format,encryption_mode,has_ciphertext:has("ciphertext"),has_entries:has("entries"),has_chart_cache:has("chart_cache")}' "$FILE"
```

Bei aktiver Passwortverschlüsselung wird erwartet:

```json
{
  "encrypted": true,
  "format": "AES-256-GCM",
  "encryption_mode": "password-scrypt-v1",
  "has_ciphertext": true,
  "has_entries": false,
  "has_chart_cache": false
}
```

`entries` und `chart_cache` stecken dann ausschließlich im authentifizierten `ciphertext`. Sichtbar bleiben nur notwendige Verschlüsselungsmetadaten wie Scrypt-Parameter, Salt, Nonce und Chiffretext. Das Master-Passwort wird nicht gespeichert.

Ohne Verschlüsselung wird erwartet:

```json
{
  "encrypted": null,
  "format": null,
  "encryption_mode": null,
  "has_ciphertext": false,
  "has_entries": true,
  "has_chart_cache": true
}
```

Dann kann ein Nutzer mit Dateisystemzugriff das Kaufbuch im Klartext lesen. Die Home-Assistant-Nutzerfreigabe schützt in diesem Modus nur den Zugriff über Oberfläche und API.

Nur die Feldstruktur prüfen, nicht die komplette Datei in ein Chatfenster oder Fehlerprotokoll kopieren. Im Klartextmodus enthält sie reale Bestände, Preise, Notizen und Zeitpunkte.

## Öffentlicher BTC-Kurscache

Historische Tageskurse liegen getrennt unter:

```text
/config/.storage/bitcoin_stack_tracker.history.<CONFIG_ENTRY_ID>
```

Dieser Cache enthält öffentliche Marktdaten und Synchronisationsmetadaten. Er bleibt lokal erhalten, wenn Historie oder automatische Synchronisierung ausgeschaltet werden. Zeitraum, lineare/logarithmische Skala und Chartmodus verändern den Cache nicht.

Der öffentliche Kurscache ist lokal nicht mit dem Portfolio-Master-Passwort verschlüsselt. Private Stack- und Portfoliowerte liegen dagegen im verschlüsselbaren Ledger-`chart_cache`. Ein exportiertes `.bstbackup` ist immer mit dem gewählten Backup-Passwort verschlüsselt und kann auch den Kurscache enthalten.

## Nutzerfreigabe und Verschlüsselungsmodus

Die Zugriffsrichtlinie liegt unter:

```text
/config/.storage/bitcoin_stack_tracker.security.<CONFIG_ENTRY_ID>
```

Darin stehen erlaubte Home-Assistant-Nutzer und der gewählte Verschlüsselungsmodus, aber weder Master-Passwort noch abgeleiteter Sitzungsschlüssel. Entsperrte Nutzer und Schlüssel existieren nur im Arbeitsspeicher und gehen bei einem Home-Assistant-Neustart verloren.

## Backup-Gesundheitsmetadaten

Die Dashboard-App speichert Erinnerungsmetadaten getrennt vom Portfolio unter:

```text
/data/bitcoin-stack-tracker-runtime/backup-health.json
```

Darin stehen nur Config-Entry-ID, Zeitstempel des letzten verschlüsselten Backups beziehungsweise Wiederherstellungstests und die gewählten Warnfristen. Backup-Passwörter, Master-Passwörter, Seed-Wörter, Passphrases und private Schlüssel werden dort nicht gespeichert.

## Temporäre CSV-Uploads

Der CSV-Import erzeugt keine Datei unter `/config`, `/data` oder `/tmp`. Der Upload wird im Arbeitsspeicher geparst und anschließend verworfen. Gespeichert werden nur die ausdrücklich bestätigten normalisierten Kauf- und Verkaufsbuchungen. Die Originaldatei auf dem Client-Gerät kann das Dashboard nicht löschen.
