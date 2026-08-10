#!/usr/bin/python3
"""Minimal stdlib-only health agent for the Bitcoin Stack Tracker Tor gateway.

This process deliberately has no Home Assistant token, no portfolio storage,
no CSV parser, no backup code, and no password endpoints. Its only job is to
serve a tiny local watchdog endpoint from the Tor/killswitch state written by
run.sh.  It uses only Python's standard library so the network gateway does not
need aiohttp or any other application framework.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
from typing import Any

APP_VERSION = "0.21.0.2"
STATUS_FILE = Path(os.environ.get("NETWORK_STATUS_FILE", "/run/bitcoin-stack-network-status.json"))
STOP_FILE = Path(os.environ.get("NETWORK_STOP_FILE", "/run/bitcoin-stack-network-agent-stop"))


def _status() -> dict[str, Any]:
    try:
        value = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            return value
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return {}


def _payload(path: str) -> tuple[int, dict[str, Any]]:
    if path == "/health":
        status = _status()
        firewall = bool(status.get("killswitch_active") or status.get("firewall_active"))
        tor = bool(status.get("tor_process_running") or status.get("tor_running"))
        return 200, {
            "status": "ok" if firewall and tor else "protection-fault",
            "version": APP_VERSION,
            "role": "network-only-tor-gateway",
            "portfolio_access": False,
            "homeassistant_api_token": False,
            "ingress_ui": False,
            "killswitch": firewall,
            "tor_process": tor,
        }
    if path == "/network-status":
        # Keep this endpoint low-sensitivity because the add-on network is shared.
        # Home Assistant Core computes the owner-only exit-IP display itself. Do
        # not expose Tor relay/socket IPs or local socket targets to peer add-ons.
        status = _status()
        public = {
            key: status.get(key)
            for key in (
                "firewall_active", "firewall_ipv4", "firewall_ipv6",
                "ipv6_disabled", "firewall_backend", "firewall_error",
                "blocked_ipv4_packets", "blocked_ipv6_packets",
                "tor_process_running", "non_tor_public_socket_count",
                "clearnet_leak_detected", "policy", "updated_at",
            )
        }
        return 200, {
            "version": APP_VERSION,
            "role": "network-only-tor-gateway",
            "portfolio_access": False,
            "homeassistant_api_token": False,
            **public,
        }
    if path == "/":
        return 200, {
            "name": "Bitcoin Stack Tracker Tor Gateway",
            "version": APP_VERSION,
            "role": "network-only",
            "note": (
                "The dashboard is a native Home Assistant panel. This add-on "
                "handles Tor and the nftables killswitch only."
            ),
        }
    return 404, {"error": "not_found"}


class Handler(BaseHTTPRequestHandler):
    server_version = "BSTHealth/1"
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        code, payload = _payload(self.path.split("?", 1)[0])
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8099), Handler)
    # Do not rely on SIGTERM delivery through the nested AppArmor profile for
    # normal operator shutdown. run.sh creates STOP_FILE first; the bounded
    # handle_request loop notices it within 250 ms and exits with status 0.
    # Signals remain a last-resort fallback handled by s6.
    server.timeout = 0.25
    try:
        while not STOP_FILE.exists():
            server.handle_request()
    finally:
        server.server_close()
