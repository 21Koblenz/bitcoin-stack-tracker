# Bitcoin Stack Tracker Tor Gateway v0.21.0.3

**ONLY TOR · FAIL CLOSED**

Das Tor Gateway ist der Netzwerk-Baustein des Bitcoin Stack Trackers. Es kapselt öffentliche Internetzugriffe in eine eigene Home-Assistant-App und stellt Home Assistant Core einen internen Tor-SOCKS5-Endpunkt bereit.

Die eigentliche Bitcoin-Stack-Tracker-Integration läuft in Home Assistant Core. Portfolio, Käufe, Verkäufe, Depots, Ziele, FIFO-Berechnungen und verschlüsselte Tracker-Daten befinden sich **nicht** in dieser App.

## 1. Warum gibt es ein separates Tor Gateway?

Die Trennung verfolgt zwei Ziele:

1. Öffentliche Datenquellen sollen ausschließlich über Tor erreichbar sein.
2. Der Netzwerkdienst soll möglichst wenig von den persönlichen Tracker-Daten sehen.

Dadurch ergibt sich eine klare Aufteilung:

```text
Bitcoin Stack Tracker Integration
(Home Assistant Core)
        │
        ├── lokale/private Node
        │      └── direkter LAN-Pfad
        │
        └── öffentliche Quelle
               │
               ▼
      Tor Gateway :9050
               │
               ▼
              Tor
               │
               ▼
          öffentliche API
```

Das Tor Gateway kennt dabei nicht den Inhalt des Kaufbuchs oder des Tresors. Es transportiert lediglich die dafür notwendigen öffentlichen HTTP-Verbindungen über Tor.

## 2. Fail-Closed-Prinzip

Das Gateway richtet beim Start einen nftables-Killswitch ein.

Das Grundprinzip lautet:

```text
öffentlicher Direktzugriff → blockiert
Tor-Prozess               → öffentlicher Egress erlaubt
interner SOCKS-Zugriff     → Tor
```

Die Regeln verwenden Default-Drop. Kann die Firewall nicht eingerichtet oder verifiziert werden, soll die App nicht in einen normalen Betriebszustand wechseln.

Es gibt bewusst keinen Modus nach dem Prinzip:

```text
Tor nicht erreichbar → dann direkt ins Internet
```

Stattdessen gilt:

```text
Tor nicht erreichbar → öffentliche Abfrage schlägt fehl
```

Lokale Tracker-Funktionen und bereits vorhandene Daten können davon unabhängig weiter verfügbar bleiben.

## 3. Interne SOCKS-Endpunkte

### Port 9050 – Bitcoin Stack Tracker Core

`9050/tcp` ist der interne SOCKS5-Pfad für die Bitcoin-Stack-Tracker-Integration in Home Assistant Core.

Er ist für die öffentlichen Kurs- und Historienquellen des Trackers vorgesehen.

### Port 9051 – geteilter Tor-SOCKS-Port

`9051/tcp` kann bewusst als zusätzlicher interner Tor-SOCKS5-Endpunkt für andere Home-Assistant-Apps verwendet werden.

Auch über diesen Pfad werden private, Link-Local- und LAN-Ziele nicht als Proxy-Ziele freigegeben.

### Port 8099 – Health-Endpunkt

`8099/tcp` wird ausschließlich intern für den Supervisor-Watchdog verwendet.

Die Ports werden in der Standardkonfiguration **nicht auf den Home-Assistant-Host veröffentlicht**.

## 4. Welche Daten befinden sich nicht im Gateway?

Das Gateway speichert oder verarbeitet absichtlich keine persönlichen Tracker-Inhalte wie:

- BTC-Bestand
- Käufe und Verkäufe
- FIFO-Zuordnungen
- Depotnamen
- Ziele oder Milestones
- Notizen
- Master-Passwort
- Backup-Passwort
- verschlüsselte portable Backups
- CSV-Importdateien
- Wallet-Seeds
- Wallet-Passphrasen
- Private Keys

Das Gateway ist außerdem kein Wallet und verwaltet keine Bitcoin-Schlüssel.

## 5. Installation

### App-Repository hinzufügen

Am einfachsten über My Home Assistant:

[![Bitcoin Stack Tracker App-Repository hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2F21Koblenz%2Fbitcoin-stack-tracker)

Alternativ manuell:

1. **Einstellungen → Apps → App Store** öffnen.
2. Oben rechts das Repository-Menü öffnen.
3. Repository hinzufügen:

```text
https://github.com/21Koblenz/bitcoin-stack-tracker
```

4. **Bitcoin Stack Tracker Tor Gateway** öffnen.
5. **Installieren** wählen.
6. Nach der Installation **Starten**.

### Custom Integration installieren

Für die eigentliche Tracker-Oberfläche und Datenhaltung wird zusätzlich die HACS-Integration benötigt:

[![Bitcoin Stack Tracker in HACS öffnen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=21Koblenz&repository=bitcoin-stack-tracker&category=integration)

Nach Installation oder Aktualisierung der Custom Integration Home Assistant Core vollständig neu starten.

## 6. Konfiguration

Die App besitzt bewusst nur wenige Einstellungen.

### Log-Level

Verfügbare Werte:

- `debug`
- `info`
- `warning`
- `error`

Für den normalen Betrieb ist `info` vorgesehen.

`debug` sollte nur zur Fehlersuche verwendet werden, da dadurch wesentlich mehr technische Protokollausgaben entstehen können.

## 7. Start und Autostart

Die App ist für automatischen Start konfiguriert.

Nach einer normalen Home-Assistant-OS-/Supervisor-Neustartsequenz soll das Gateway wieder automatisch starten, damit der Tor-Pfad für die Integration verfügbar wird.

Im App-Bereich können folgende Zustände auftreten:

- **Gestartet** – Gateway läuft
- **Gestoppt** – kein Tor-SOCKS-Dienst für den Tracker
- **Fehler beim Start** – Logs auf Tor-, Firewall- oder Berechtigungsfehler prüfen

## 8. Keine eigene Weboberfläche

Das Tor Gateway besitzt absichtlich kein eigenes Ingress-Frontend.

Das sichtbare Dashboard **Bitcoin Stack** stammt aus der Custom Integration und läuft als natives Home-Assistant-Seitenleistenpanel.

Das Gateway ist ausschließlich der Netzwerkdienst darunter.

## 9. Tor-Ausfall

Wenn Tor nicht verfügbar ist:

- öffentliche Live-Kurse können fehlschlagen
- historische öffentliche Nachladevorgänge können fehlschlagen
- der Tracker soll nicht direkt ins Clearnet ausweichen
- lokale Nodes können weiterhin über ihren ausdrücklich konfigurierten privaten Pfad erreichbar sein
- bereits vorhandene lokale Tracker-Daten bleiben unabhängig vom Tor-Netzwerk bestehen

Das ist beabsichtigtes Fail-Closed-Verhalten und kein automatischer Clearnet-Fallback.

## 10. Fehlerbehebung

### App startet nicht

Im Tab **Protokoll** nach folgenden Themen suchen:

- Tor-Konfigurationsfehler
- nftables-/Firewall-Fehler
- fehlende Berechtigungen
- Fehler beim Health-Check

Der Killswitch ist Teil der Sicherheitsgrenze. Wenn er nicht korrekt aufgebaut werden kann, soll die App nicht einfach unsicher weiterlaufen.

### Tracker zeigt keine öffentlichen Kurse

1. Prüfen, ob das Gateway gestartet ist.
2. App-Protokoll prüfen.
3. Im Tracker den Tor-/Leak-Test ausführen.
4. Prüfen, ob lokale Node-Adressen tatsächlich als lokale/private Ziele konfiguriert sind.
5. Im App Store **Nach Aktualisierungen suchen** ausführen, wenn Repository-Daten gerade geändert wurden.

### Nach Repository-Änderungen wird alte Dokumentation angezeigt

Home Assistant lädt App-Metadaten und Dokumentation aus dem App-Repository. Im App Store oben rechts **Nach Aktualisierungen suchen** ausführen und anschließend die App-Seite neu öffnen. Bei Bedarf die Home-Assistant-Oberfläche neu laden.

## 11. Berechtigungen

### `NET_ADMIN`

Die App benötigt `NET_ADMIN`, um innerhalb ihres Containers die nftables-Regeln für den Fail-Closed-Killswitch einzurichten.

Diese Berechtigung ist bewusst auf diesen Zweck begrenzt.

### Nicht angefordert

Das Gateway benötigt für seine Aufgabe insbesondere keinen:

- Docker-Socket
- allgemeinen Host-Dateisystemzugriff
- Home-Assistant-API-Token
- Zugriff auf die Tracker-Vault-Dateien

## 12. AppArmor

Das Repository liefert ein eigenes `apparmor.txt` für das Gateway mit. AppArmor ergänzt die Netzwerk- und Containergrenzen um eine weitere Einschränkung der erlaubten Ressourcen.

## 13. Container und Architekturen

Die App wird als vorgebautes Container-Image über GHCR bereitgestellt.

Unterstützte Architekturen:

- `amd64`
- `aarch64`

Öffentliche Referenz des Multi-Arch-Images:

```text
ghcr.io/21koblenz/bitcoin-stack-tracker-tor-gateway:0.21.0.3
```

Home Assistant wählt anhand der Plattform die passende Architektur aus.

## 14. SBOM

Das Projekt enthält eine Source-SBOM und erzeugt zusätzlich eine Runtime-SBOM für die App. Dadurch lassen sich die verwendeten Komponenten und Abhängigkeiten besser nachvollziehen.

## 15. Sicherheitshinweise

- Keine Wallet-Seeds, Private Keys oder Wallet-Passphrasen im Tracker hinterlegen.
- Das Tor Gateway ist kein Anonymitätsversprechen für Home Assistant als Ganzes.
- Der Fail-Closed-Killswitch schützt den für das Gateway vorgesehenen öffentlichen Egress-Pfad; andere Home-Assistant-Integrationen besitzen ihre eigenen Netzwerkpfade.
- Ein lokaler Node-Pfad ist bewusst vom öffentlichen Tor-Pfad getrennt und kann direkt im privaten LAN angesprochen werden.

## 16. Projekt und Quellcode

Repository:

[github.com/21Koblenz/bitcoin-stack-tracker](https://github.com/21Koblenz/bitcoin-stack-tracker)

Das Projekt ist Open Source und steht unter **GNU Affero General Public License v3.0 only (`AGPL-3.0-only`)**.
