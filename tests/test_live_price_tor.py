from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components/bitcoin_stack_tracker"
ADDON = ROOT / "bitcoin_stack_tracker_dashboard"


def test_live_public_price_is_multi_provider_arithmetic_mean_over_tor():
    coordinator = (COMP / "coordinator.py").read_text(encoding="utf-8")
    for host in (
        "api.kraken.com",
        "api.exchange.coinbase.com",
        "www.bitstamp.net",
        "api.coingecko.com",
    ):
        assert host in coordinator
    assert 'provider_names = ("Kraken", "Coinbase", "Bitstamp", "CoinGecko")' in coordinator
    assert 'mean_value = sum(item[2] for item in accepted) / len(accepted)' in coordinator
    assert 'abs(item[2] - median) / median <= 0.05' in coordinator
    assert "async_routed_session(" in coordinator
    assert '"route": "tor"' in coordinator


def test_public_requests_have_no_direct_clearnet_fallback():
    network = (COMP / "network.py").read_text(encoding="utf-8")
    assert "Direct Clearnet blocked" in network
    assert "if proxy_url is None:" in network
    assert "raise ClearnetBlockedError" in network
    assert "ProxyConnector.from_url(isolated_proxy, rdns=True)" in network
    assert 'TOR_GATEWAY_HOST_CANDIDATES' in network
    assert 'async_tor_gateway_host' in network
    assert '_address_is_private_or_local' in network


def test_gateway_exposes_read_only_transport_telemetry_to_core():
    agent = (ADDON / "app/network_agent.py").read_text(encoding="utf-8")
    init = (COMP / "__init__.py").read_text(encoding="utf-8")
    assert 'if path == "/network-status"' in agent
    assert "portfolio_access\": False" in agent
    assert "SUPERVISOR_TOKEN" not in agent
    assert 'gateway_url = (' in init
    assert 'gateway.get("tor_public_socket_targets"' in init
    assert 'gateway.get("non_tor_public_socket_targets"' in init
    assert '"public_direct_fallback": False' in init


def test_connection_refresh_has_visible_feedback_and_refreshes_live_quotes():
    app = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")
    index = (COMP / "frontend/index.html").read_text(encoding="utf-8")
    init = (COMP / "__init__.py").read_text(encoding="utf-8")
    assert 'id="connectionRefreshResult"' in index
    assert 'refreshLive:true' in app
    assert 'refresh_live=1' in app
    assert 'connectionsRefreshed' in app
    assert 'livePriceRefreshedAt' in app
    assert 'await runtime["coordinator"].async_refresh()' in init
    assert '"refreshed_at": datetime.now(timezone.utc).isoformat()' in init


def test_transport_ui_explains_internal_socks_then_tor_relay():
    app = (COMP / "frontend/static/app.js").read_text(encoding="utf-8")
    assert "Core → interner SOCKS5 → Tor-Gateway → Tor-Circuit → HTTPS-API" in app
    assert "Tor Guard/Relay" in app
    assert "direkten öffentlichen Clearnet-Fallback" in app
