# Datenportabilität · Bitcoin Stack Tracker v0.21.0.3
Das portable `.bstbackup` ist bewusst als installationsunabhängiges Austauschformat für die nutzerbezogenen Bitcoin-Tracker-Daten ausgelegt.

## Enthalten

Ein neu erzeugtes Backup enthält ausschließlich:

1. Käufe und Verkäufe
2. Depots
3. Ziele
4. lokale Historie

## Nicht enthalten / nicht wiederhergestellt

- Tor-/Mempool-/Netzwerkziele
- Home-Assistant-Zugriffslisten
- Verschlüsselungseinstellungen des lokalen Tresors
- Installationsparameter des Tor Gateways
- Home-Assistant- oder Supervisor-Konfiguration

Ältere Backup-Schemata werden aus Kompatibilitätsgründen weiterhin gelesen. Falls sie historische Installations- oder Zugriffseinstellungen enthalten, werden diese beim Restore ignoriert.

Das Backup-Passwort wird nicht gespeichert. Ohne das richtige Backup-Passwort kann ein verschlüsseltes `.bstbackup` nicht wiederhergestellt werden.
