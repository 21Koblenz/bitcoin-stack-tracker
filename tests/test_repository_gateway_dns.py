from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_repository_gateway_dns_alias_and_local_fallback_are_present():
    const = (ROOT / "custom_components/bitcoin_stack_tracker/const.py").read_text()
    network = (ROOT / "custom_components/bitcoin_stack_tracker/network.py").read_text()
    init = (ROOT / "custom_components/bitcoin_stack_tracker/__init__.py").read_text()

    assert 'TOR_GATEWAY_REPOSITORY_ID = hashlib.sha1' in const
    assert 'TOR_GATEWAY_HOST_CANDIDATES = (TOR_GATEWAY_PUBLISHED_HOST, TOR_GATEWAY_LOCAL_HOST)' in const
    assert 'socks5://{TOR_GATEWAY_PUBLISHED_HOST}:9050' in const
    assert 'async def async_tor_gateway_host()' in network
    assert '_address_is_private_or_local' in network
    assert 'async_tor_gateway_host' in init.split('from .network import', 1)[1].split('\n', 1)[0]
    assert 'gateway_host = await async_tor_gateway_host()' in init
    assert 'asyncio.open_connection(gateway_host, 9050)' in init


def test_config_migration_moves_old_local_gateway_default_to_repository_default():
    migrations = (ROOT / "custom_components/bitcoin_stack_tracker/migrations.py").read_text()
    config_flow = (ROOT / "custom_components/bitcoin_stack_tracker/config_flow.py").read_text()
    assert "LATEST_CONFIG_VERSION = 10" in migrations
    assert "if version < 10:" in migrations
    assert "LOCAL_HISTORY_TOR_PROXY" in migrations
    assert "VERSION = 10" in config_flow
