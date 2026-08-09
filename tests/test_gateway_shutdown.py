from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "bitcoin_stack_tracker_dashboard"
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"


def test_gateway_socks_is_internal_only():
    config = yaml.safe_load((ADDON / "config.yaml").read_text(encoding="utf-8"))
    assert config["ports"]["9050/tcp"] is None
    assert config["ports"]["8099/tcp"] is None
    assert config.get("ingress") in (None, False)
    assert config.get("auth_api") in (None, False)
    assert config.get("apparmor") is True
    assert "NET_ADMIN" in config.get("privileged", [])


def test_core_uses_internal_gateway_dns_not_host_published_port():
    const = (COMP / "const.py").read_text(encoding="utf-8")
    init = (COMP / "__init__.py").read_text(encoding="utf-8")
    assert 'TOR_GATEWAY_REPOSITORY_ID = hashlib.sha1' in const
    assert 'DEFAULT_HISTORY_TOR_PROXY = f"socks5://{TOR_GATEWAY_PUBLISHED_HOST}:9050"' in const
    assert 'asyncio.open_connection(gateway_host, 9050)' in init
    assert "172.30.32.1:19050" not in const
    assert "172.30.32.1:19050" not in init


def test_health_agent_has_marker_based_graceful_shutdown():
    agent = (ADDON / "app" / "network_agent.py").read_text(encoding="utf-8")
    run = (ADDON / "run.sh").read_text(encoding="utf-8")
    finish = (ADDON / "rootfs/etc/services.d/bitcoin-stack-tracker/finish").read_text(encoding="utf-8")
    assert "STOP_FILE" in agent
    assert "server.timeout = 0.25" in agent
    assert "while not STOP_FILE.exists()" in agent
    assert "server.handle_request()" in agent
    assert "Network health agent did not stop promptly" in run
    assert "Dashboard did not stop promptly" not in run
    assert "Network health agent exited unexpectedly" in run
    assert '2|15) container_code=0' in finish
    assert "s6-linux-init-container-results/exitcode" in finish
