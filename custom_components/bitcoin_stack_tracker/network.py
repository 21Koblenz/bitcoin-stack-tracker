"""Fail-closed network routing and leak accounting for Bitcoin Stack Tracker."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from ipaddress import ip_address, ip_network
from socket import AddressFamily
import secrets
from typing import AsyncIterator, Any
from urllib.parse import quote, urlparse, urlunparse

from aiohttp import ClientSession, TCPConnector
from aiohttp.abc import AbstractResolver
from aiohttp.resolver import DefaultResolver
from aiohttp_socks import ProxyConnector

from homeassistant.core import HomeAssistant
from .const import (
    CONF_BASE_URL,
    CONF_MEMPOOL_OWN_INSTANCE,
    DEFAULT_HISTORY_TOR_PROXY,
    DOMAIN,
    MEMPOOL_ROUTE_DIRECT,
    MEMPOOL_ROUTE_TOR,
    TOR_GATEWAY_HOST_CANDIDATES,
)

_NETWORK_SECURITY_KEY = "_network_security"


class TorConfigurationError(ValueError):
    """Raised when a request that must use Tor cannot be routed safely."""


class ClearnetBlockedError(TorConfigurationError):
    """Raised before a prohibited direct public connection can be attempted."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state(hass: HomeAssistant) -> dict[str, Any]:
    domain_data = hass.data.setdefault(DOMAIN, {})
    state = domain_data.get(_NETWORK_SECURITY_KEY)
    if not isinstance(state, dict):
        state = {
            "policy": "local-direct-or-tor-only",
            "killswitch": True,
            "tor_requests": 0,
            "tor_successes": 0,
            "tor_failures": 0,
            "local_direct_requests": 0,
            "blocked_direct_requests": 0,
            "last_blocked_host": None,
            "last_blocked_at": None,
            "last_tor_success_at": None,
            "last_tor_failure_at": None,
            "last_tor_error": None,
            "connections": {},
            "tor_isolation_token": secrets.token_hex(16),
            "tor_identity_generation": 1,
            "tor_last_rotated_at": None,
        }
        domain_data[_NETWORK_SECURITY_KEY] = state
    state.setdefault("tor_isolation_token", secrets.token_hex(16))
    state.setdefault("tor_identity_generation", 1)
    state.setdefault("tor_last_rotated_at", None)
    return state


def rotate_tor_isolation(hass: HomeAssistant) -> dict[str, Any]:
    """Request fresh Tor stream isolation without exposing Tor ControlPort.

    Tor's SocksPort is configured with IsolateSOCKSAuth. Rotating the random
    SOCKS credential therefore places all subsequent public requests into a new
    isolation group. The credential is ephemeral, contains no portfolio secret,
    and never leaves Home Assistant Core except as SOCKS authentication to the
    local Tor add-on.
    """
    state = _state(hass)
    state["tor_isolation_token"] = secrets.token_hex(16)
    state["tor_identity_generation"] = int(state.get("tor_identity_generation", 0) or 0) + 1
    state["tor_last_rotated_at"] = _utc_now()
    return {
        "requested": True,
        "tor_identity_generation": state["tor_identity_generation"],
        "last_rotated_at": state["tor_last_rotated_at"],
        "method": "IsolateSOCKSAuth",
    }


def _proxy_with_isolation(hass: HomeAssistant, proxy_url: str) -> str:
    parsed = urlparse(proxy_url)
    token = str(_state(hass).get("tor_isolation_token") or secrets.token_hex(16))
    host = parsed.hostname or ""
    port = parsed.port or 9050
    # A unique username is enough for IsolateSOCKSAuth. The random token is not
    # a security credential for the vault; it only selects a Tor circuit group.
    netloc = f"bst-{quote(token, safe='')}:{quote(token, safe='')}@{host}:{port}"
    return urlunparse(parsed._replace(netloc=netloc))


def network_security_snapshot(hass: HomeAssistant) -> dict[str, Any]:
    """Return non-secret counters for the dashboard leak-test panel."""
    state = _state(hass)
    return {
        "policy": state["policy"],
        "killswitch": bool(state["killswitch"]),
        "tor_requests": int(state["tor_requests"]),
        "tor_successes": int(state["tor_successes"]),
        "tor_failures": int(state["tor_failures"]),
        "local_direct_requests": int(state["local_direct_requests"]),
        "blocked_direct_requests": int(state["blocked_direct_requests"]),
        "last_blocked_host": state.get("last_blocked_host"),
        "last_blocked_at": state.get("last_blocked_at"),
        "last_tor_success_at": state.get("last_tor_success_at"),
        "last_tor_failure_at": state.get("last_tor_failure_at"),
        "last_tor_error": state.get("last_tor_error"),
        "remote_dns": True,
        "public_direct_allowed": False,
        "tor_identity_method": "IsolateSOCKSAuth",
        "tor_identity_generation": int(state.get("tor_identity_generation", 1) or 1),
        "tor_last_rotated_at": state.get("tor_last_rotated_at"),
        "connections": [
            {
                "target": str(item.get("target") or ""),
                "route": str(item.get("route") or ""),
                "active": int(item.get("active", 0) or 0),
                "last_started_at": item.get("last_started_at"),
                "last_success_at": item.get("last_success_at"),
                "last_failure_at": item.get("last_failure_at"),
                "last_error": item.get("last_error"),
            }
            for item in state.get("connections", {}).values()
            if isinstance(item, dict)
        ],
    }


def _host_for_log(url: str) -> str:
    return (urlparse(str(url)).hostname or "invalid-host").lower().rstrip(".")[:255]


def _record_block(hass: HomeAssistant, url: str) -> None:
    state = _state(hass)
    state["blocked_direct_requests"] += 1
    state["last_blocked_host"] = _host_for_log(url)
    state["last_blocked_at"] = _utc_now()


def _record_local(hass: HomeAssistant) -> None:
    _state(hass)["local_direct_requests"] += 1


def _record_tor_start(hass: HomeAssistant) -> None:
    _state(hass)["tor_requests"] += 1


def _record_tor_success(hass: HomeAssistant) -> None:
    state = _state(hass)
    state["tor_successes"] += 1
    state["last_tor_success_at"] = _utc_now()
    state["last_tor_error"] = None


def _record_tor_failure(hass: HomeAssistant, err: BaseException) -> None:
    state = _state(hass)
    state["tor_failures"] += 1
    state["last_tor_failure_at"] = _utc_now()
    state["last_tor_error"] = f"{type(err).__name__}: {err}"[:500]




def _connection_item(hass: HomeAssistant, url: str, route: str) -> dict[str, Any]:
    state = _state(hass)
    connections = state.setdefault("connections", {})
    target = _host_for_log(url)
    key = f"{route}:{target}"
    item = connections.get(key)
    if not isinstance(item, dict):
        item = {
            "target": target,
            "route": route,
            "active": 0,
            "last_started_at": None,
            "last_success_at": None,
            "last_failure_at": None,
            "last_error": None,
        }
        connections[key] = item
    return item


def _record_connection_start(hass: HomeAssistant, url: str, route: str) -> None:
    item = _connection_item(hass, url, route)
    item["active"] = int(item.get("active", 0) or 0) + 1
    item["last_started_at"] = _utc_now()


def _record_connection_end(
    hass: HomeAssistant, url: str, route: str, err: BaseException | None = None
) -> None:
    item = _connection_item(hass, url, route)
    item["active"] = max(0, int(item.get("active", 0) or 0) - 1)
    if err is None:
        item["last_success_at"] = _utc_now()
        item["last_error"] = None
    else:
        item["last_failure_at"] = _utc_now()
        item["last_error"] = f"{type(err).__name__}: {err}"[:300]

async def async_tor_gateway_host() -> str:
    """Return the reachable private Supervisor DNS alias for the Tor gateway.

    Repository-installed apps use a hashed repository prefix, while local apps
    use the ``local-`` prefix. Only private/internal DNS answers are accepted.
    """
    last_error: BaseException | None = None
    for host in TOR_GATEWAY_HOST_CANDIDATES:
        resolver = DefaultResolver()
        try:
            results = await resolver.resolve(host, 9050, AddressFamily.AF_UNSPEC)
        except BaseException as err:  # noqa: BLE001 - try the next internal alias
            last_error = err
            continue
        finally:
            await resolver.close()
        if results and all(
            _address_is_private_or_local(str(result.get("host", "")))
            for result in results
        ):
            return host
        last_error = TorConfigurationError(
            f"Tor gateway alias {host} did not resolve exclusively to private addresses"
        )
    raise TorConfigurationError(
        "Tor gateway is not reachable through the Home Assistant internal network"
    ) from last_error


async def _resolve_bundled_proxy_url(proxy_url: str) -> str:
    """Resolve the bundled proxy alias without allowing a public fallback."""
    parsed = urlparse(proxy_url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if host not in set(TOR_GATEWAY_HOST_CANDIDATES):
        return proxy_url
    gateway_host = await async_tor_gateway_host()
    port = parsed.port or 9050
    return urlunparse(parsed._replace(netloc=f"{gateway_host}:{port}"))


def normalize_proxy_url(value: Any) -> str:
    """Validate and normalize a proxy URL while keeping DNS resolution remote."""
    raw = str(value or "").strip()
    if not raw:
        raise TorConfigurationError(
            "Tor proxy is not configured; public requests are blocked"
        )
    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()
    if scheme == "socks5h":
        scheme = "socks5"
    if scheme != "socks5":
        raise TorConfigurationError("Tor proxy must use socks5:// or socks5h://")
    if not parsed.hostname or parsed.port is None:
        raise TorConfigurationError("Tor proxy URL must include host and port")
    return urlunparse(parsed._replace(scheme=scheme))


def tor_proxy_from_settings(settings: dict[str, Any]) -> str:
    """Return the bundled Tor proxy; stored overrides cannot weaken routing."""
    del settings
    return normalize_proxy_url(DEFAULT_HISTORY_TOR_PROXY)


def is_onion_url(url: str) -> bool:
    """Return whether a URL targets a Tor onion service."""
    host = (urlparse(str(url)).hostname or "").lower().rstrip(".")
    return host.endswith(".onion")


_LOCAL_NETWORKS = (
    ip_network("10.0.0.0/8"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    ip_network("127.0.0.0/8"),
    ip_network("169.254.0.0/16"),
    ip_network("fc00::/7"),
    ip_network("fe80::/10"),
    ip_network("::1/128"),
)


def _address_is_private_or_local(value: str) -> bool:
    try:
        address = ip_address(value)
    except ValueError:
        return False
    return any(address in network for network in _LOCAL_NETWORKS)


def is_private_or_local_url(url: str) -> bool:
    """Classify explicit local names and literal private/local addresses."""
    host = (urlparse(str(url)).hostname or "").lower().rstrip(".")
    if host in {"localhost", "homeassistant", "supervisor", *TOR_GATEWAY_HOST_CANDIDATES}:
        return True
    if host.endswith((".local", ".home.arpa", ".lan", ".internal")):
        return True
    return _address_is_private_or_local(host)


class _LocalOnlyResolver(AbstractResolver):
    """Resolve a local hostname while rejecting every public answer."""

    def __init__(self, hass: HomeAssistant, target_url: str) -> None:
        self._resolver = DefaultResolver()
        self._hass = hass
        self._target_url = target_url

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: AddressFamily = AddressFamily.AF_UNSPEC,
    ) -> list[dict[str, Any]]:
        results = await self._resolver.resolve(host, port, family)
        if not results or any(
            not _address_is_private_or_local(str(result.get("host", "")))
            for result in results
        ):
            _record_block(self._hass, self._target_url)
            raise ClearnetBlockedError(
                f"Local target {host} resolved outside private networks; blocked"
            )
        return results

    async def close(self) -> None:
        await self._resolver.close()


def is_public_mempool_url(url: str) -> bool:
    """Return whether a source is the public mempool.space service."""
    host = (urlparse(str(url)).hostname or "").lower().rstrip(".")
    return host == "mempool.space" or host.endswith(".mempool.space")


def automatic_mempool_route(*, base_url: str, own_instance: bool) -> str:
    """Route only an explicitly own private/local node directly."""
    if own_instance and is_private_or_local_url(base_url) and not is_onion_url(base_url):
        return MEMPOOL_ROUTE_DIRECT
    return MEMPOOL_ROUTE_TOR


def mempool_source_uses_tor(source: dict[str, Any]) -> bool:
    """Return whether a mempool source must be contacted through Tor."""
    return automatic_mempool_route(
        base_url=str(source.get(CONF_BASE_URL, "")),
        own_instance=bool(source.get(CONF_MEMPOOL_OWN_INSTANCE, False)),
    ) == MEMPOOL_ROUTE_TOR


def mempool_source_is_exclusive(source: dict[str, Any]) -> bool:
    """Legacy compatibility helper; historical sources are no longer exclusive."""
    return False


def validate_mempool_route(
    *, base_url: str, own_instance: bool, route: str
) -> None:
    """Reject configurations that differ from the fixed privacy policy."""
    if route not in {MEMPOOL_ROUTE_DIRECT, MEMPOOL_ROUTE_TOR}:
        raise ValueError("Unsupported mempool connection route")
    if is_private_or_local_url(base_url) and not own_instance:
        raise ValueError("A private or local node URL must be marked as your own instance")
    expected = automatic_mempool_route(base_url=base_url, own_instance=own_instance)
    if route != expected:
        if expected == MEMPOOL_ROUTE_DIRECT:
            raise ValueError("An own private or local node must be contacted directly")
        if is_onion_url(base_url):
            raise ValueError("Onion addresses require Tor")
        if is_public_mempool_url(base_url):
            raise ValueError("The public mempool.space service may not bypass Tor")
        raise ValueError("Every non-local node must use Tor")


def _validated_target(url: str) -> str:
    raw = str(url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ClearnetBlockedError("Only explicit HTTP(S) targets are permitted")
    if parsed.username or parsed.password:
        raise ClearnetBlockedError("Credentials in request target URLs are not permitted")
    return raw


def direct_target_allowed(url: str, *, allow_local_direct: bool) -> bool:
    """Return True only for a caller-approved local non-onion target."""
    target = _validated_target(url)
    return (
        allow_local_direct
        and is_private_or_local_url(target)
        and not is_onion_url(target)
    )


def assert_direct_target_allowed(url: str, *, allow_local_direct: bool) -> None:
    """Pure guard used by the live request path and the leak self-test."""
    if not direct_target_allowed(url, allow_local_direct=allow_local_direct):
        raise ClearnetBlockedError(
            f"Direct Clearnet blocked for {_host_for_log(url)}; Tor is mandatory"
        )


@asynccontextmanager
async def async_routed_session(
    hass: HomeAssistant,
    *,
    target_url: str,
    proxy_url: str | None,
    allow_local_direct: bool = False,
    verify_ssl: bool = True,
) -> AsyncIterator[tuple[ClientSession, dict[str, Any]]]:
    """Yield a session whose route is fixed before any socket is opened.

    Direct networking is available only for an explicitly approved local target.
    Every onion or public destination requires the bundled SOCKS5 proxy. SOCKS DNS
    is resolved remotely (``rdns=True``), so the local resolver never sees public
    provider or onion hostnames.
    """
    target = _validated_target(target_url)

    if direct_target_allowed(target, allow_local_direct=allow_local_direct):
        if proxy_url is not None:
            raise TorConfigurationError("A local direct request may not also set a proxy")
        _record_local(hass)
        _record_connection_start(hass, target, "local-direct")
        resolver = _LocalOnlyResolver(hass, target)
        connector = TCPConnector(resolver=resolver)
        request_kwargs: dict[str, Any] = {"allow_redirects": False}
        if not verify_ssl:
            request_kwargs["ssl"] = False
        try:
            async with ClientSession(connector=connector) as session:
                yield session, request_kwargs
        except BaseException as err:
            _record_connection_end(hass, target, "local-direct", err)
            raise
        else:
            _record_connection_end(hass, target, "local-direct")
        return

    if proxy_url is None:
        _record_block(hass, target)
        raise ClearnetBlockedError(
            f"Direct Clearnet blocked for {_host_for_log(target)}; Tor is unavailable"
        )

    # Public internet targets still travel exclusively through Tor. HTTPS is an
    # additional integrity/authentication layer against a malicious exit path;
    # v3 onion services already authenticate the destination cryptographically.
    parsed_target = urlparse(target)
    if not is_onion_url(target):
        if parsed_target.scheme.lower() != "https":
            _record_block(hass, target)
            raise ClearnetBlockedError(
                f"Public non-onion target {_host_for_log(target)} requires HTTPS over Tor"
            )
        if not verify_ssl:
            _record_block(hass, target)
            raise TorConfigurationError(
                f"TLS verification may not be disabled for public target {_host_for_log(target)}"
            )

    normalized = normalize_proxy_url(proxy_url)
    normalized = await _resolve_bundled_proxy_url(normalized)
    isolated_proxy = _proxy_with_isolation(hass, normalized)
    connector = ProxyConnector.from_url(isolated_proxy, rdns=True)
    _record_tor_start(hass)
    _record_connection_start(hass, target, "tor")
    try:
        async with ClientSession(connector=connector) as session:
            request_kwargs: dict[str, Any] = {"allow_redirects": False}
            if not verify_ssl:
                request_kwargs["ssl"] = False
            yield session, request_kwargs
    except BaseException as err:
        _record_tor_failure(hass, err)
        _record_connection_end(hass, target, "tor", err)
        raise
    else:
        _record_tor_success(hass)
        _record_connection_end(hass, target, "tor")
