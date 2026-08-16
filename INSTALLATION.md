# Installation · Bitcoin Stack Tracker v0.21.0.10

## Voraussetzungen

- Home Assistant mit Unterstützung für Custom Integrations
- Zugriff auf `/config/custom_components/` oder HACS
- Home-Assistant-App-/Add-on-Repository-Unterstützung für das Tor Gateway

## 1. Custom Integration installieren

### Manuell

1. Ordner `custom_components/bitcoin_stack_tracker` nach `/config/custom_components/bitcoin_stack_tracker` kopieren.
2. Home Assistant Core vollständig neu starten.
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen** öffnen.
4. **Bitcoin Stack Tracker** auswählen und einrichten.

### HACS

Das Repository als benutzerdefiniertes Integrations-Repository hinzufügen, installieren und Home Assistant Core danach vollständig neu starten.

## 2. Tor Gateway installieren

1. Dieses Repository im Home-Assistant-App-Shop als zusätzliches Repository hinzufügen.
2. **Bitcoin Stack Tracker Tor Gateway** installieren.
3. Gateway starten.
4. Im Tracker unter Netzwerk/Tor prüfen, ob SOCKS5, Killswitch und Gateway-Health erkannt werden.

Öffentliche Datenquellen dürfen nicht direkt ins Clearnet ausweichen. Lokale private Node-Ziele können weiterhin direkt im LAN genutzt werden.

## 3. Tracker einrichten

1. **Bitcoin Stack** in der Home-Assistant-Seitenleiste öffnen.
2. Tresor/Passwortmodus nach Wunsch einrichten.
3. Depots, Käufe, Verkäufe und Ziele anlegen oder CSV importieren.
4. Ein verschlüsseltes `.bstbackup` erstellen und außerhalb von Home Assistant sichern.

## Aktualisierung

Bei einem späteren Update zuerst die Custom Integration aktualisieren, Home Assistant Core vollständig neu starten und anschließend das Tor Gateway auf denselben Release-Stand bringen. Die versionierten Frontend-Assets verhindern, dass Browser oder Companion-App veraltete JS-/CSS-Dateien weiterverwenden.

## Fehlerdiagnose

- Home Assistant Core nach Änderungen an der Integration vollständig neu starten.
- Bei Frontend-Problemen Browser/Companion-App neu laden.
- Netzwerkstatus des Trackers prüfen: öffentliche Daten müssen über Tor laufen.
- Für Details zu Sicherheits- und Tor-Grenzen: [`SECURITY.md`](SECURITY.md) und [`TOR-HINWEISE.md`](TOR-HINWEISE.md).
