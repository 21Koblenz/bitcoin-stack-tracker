# Bitcoin Stack Tracker Tor Gateway — Changelog

## v0.21.0.0 — Initial Public Release

### Tor und Netzwerk

- Eigenständiges Tor Gateway für die öffentlichen Netzwerkzugriffe des Bitcoin Stack Trackers.
- Interner SOCKS5-Endpunkt `9050` für Home Assistant Core / Bitcoin Stack Tracker.
- Optionaler interner SOCKS5-Endpunkt `9051` für andere Home-Assistant-Apps.
- Private, Link-Local- und LAN-Ziele werden über den öffentlichen Tor-Egress blockiert.
- Kein direkter Clearnet-Fallback für öffentliche Tracker-Daten.

### Fail Closed

- nftables-Killswitch mit Default-Drop-Regeln.
- Öffentlichen Egress darf ausschließlich der Tor-Prozess öffnen.
- Die App startet nicht normal weiter, wenn der Killswitch nicht eingerichtet oder verifiziert werden kann.

### Home Assistant

- Bereitstellung als Home-Assistant-App für `amd64` und `aarch64`.
- Vorbereitete Multi-Arch-Container-Images über GHCR.
- Automatischer Start mit Home Assistant.
- Interner Health-Endpunkt `8099` für den Supervisor-Watchdog.
- Bewusst kein eigenes Ingress-Dashboard; die Benutzeroberfläche wird von der Bitcoin-Stack-Tracker-Custom-Integration bereitgestellt.

### Sicherheit und Transparenz

- Keine Portfolio-, Ledger-, FIFO-, Depot-, Ziel- oder Tresordaten im Gateway.
- Kein Home-Assistant-API-Token, Docker-Socket oder allgemeiner Host-Dateisystemzugriff erforderlich.
- `NET_ADMIN` ausschließlich für den nftables-Killswitch.
- Eigenes AppArmor-Profil.
- Source- und Runtime-SBOM.

### Lizenz

- Öffentlicher Release unter **AGPL-3.0-only**.
