"""Privacy-first watch-only Bitcoin wallet monitoring.

The authoritative watch configuration is stored by the main encrypted ledger vault.
A separate device-bound AES-GCM runtime vault keeps the public watch-only material
(address/xpub/descriptor), derived concrete addresses and connection metadata needed
for monitoring/owner management while the user vault is locked. It never stores
seeds, private extended keys or spend keys. Public requests use the existing
fail-closed Tor policy; local private nodes may be contacted directly.
"""
from __future__ import annotations

import asyncio
import base64
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import ssl
import unicodedata
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util.ssl import client_context, client_context_no_verify

from .const import (
    CONF_BASE_URL,
    CONF_MEMPOOL_OWN_INSTANCE,
    CONF_MEMPOOL_ROUTE,
    CONF_SOURCE_TYPE,
    CONF_SOURCES,
    CONF_VERIFY_SSL,
    MEMPOOL_ROUTE_DIRECT,
    MEMPOOL_ROUTE_TOR,
    SOURCE_MEMPOOL,
)
from .helpers import effective_settings
from .http_limits import async_json_limited
from .network import (
    async_routed_session,
    async_tor_socks_connection_info,
    is_onion_url,
    is_private_or_local_url,
    automatic_mempool_route,
    mempool_source_uses_tor,
    tor_proxy_from_settings,
)

WATCH_EVENT = "bitcoin_stack_tracker_wallet_activity"
WATCH_TEST_EVENT = "bitcoin_stack_tracker_wallet_activity_test"
WATCH_STATUS_EVENT = "bitcoin_stack_tracker_wallet_monitor_status"
WATCH_STORAGE_VERSION = 1
WATCH_STORAGE_KEY = "bitcoin_stack_tracker.wallet_watch_runtime"
WATCH_CACHE_SCHEMA = 1
WATCH_ENDPOINT_STORAGE_VERSION = 1
WATCH_ENDPOINT_STORAGE_KEY = "bitcoin_stack_tracker.wallet_watch_endpoint"
WATCH_ENDPOINT_SCHEMA = 1
MAX_MONITORS = 32
MAX_DERIVED_PER_BRANCH = 20  # maximum configurable gap limit per branch
# BIP44-style restore discovery uses a 20-address gap. Older Sentinel builds
# accidentally defaulted HD monitors to 2, so initial discovery must look far
# enough to recover already-used addresses without silently rewriting a user's
# saved custom gap setting.
HD_DISCOVERY_BOOTSTRAP_ADDRESSES = 20
MAX_GAP_DISCOVERY_ADDRESSES_PER_BRANCH = 500
GAP_STANDBY_ADDRESSES_PER_BRANCH = 20
MAX_RUNTIME_ADDRESSES = 4096
MAX_NOTIFICATION_TARGETS = 16
MAX_NOTIFICATION_TOKEN_LENGTH = 1024
MAX_NOTIFICATION_URL_LENGTH = 2048
MAX_ELECTRUM_CERT_PEM_LENGTH = 32768
DEFAULT_POLL_SECONDS = 60
_ALLOWED_POLL_SECONDS = {30, 60, 120, 300}
_ALLOWED_WATCH_CATEGORIES = {"own", "exchange", "interesting", "incident", "other"}
_ALLOWED_LOG_DISPLAY_MODES = {"count", "days", "unlimited"}
MAX_LOG_DISPLAY_COUNT = 500
MAX_LOG_DISPLAY_DAYS = 36500
# Bound the encrypted in-memory/persistent Sentinel journal. "Unlimited" means
# no display filter, not unbounded Home Assistant RAM growth.
MAX_STORED_ACTIVITY_LOG = 5000
LOG_PAGE_SIZE = 25
DEFAULT_LOG_PAGE_SIZE = 10
ALLOWED_TX_OVERVIEW_LIMITS = {0, 5, 10, 25, 50, 100}
DEFAULT_TX_OVERVIEW_LIMIT = 10
TX_OVERVIEW_PAGE_SIZE = 25
TX_OVERVIEW_MAX_PREVOUT_TXS_PER_TRANSACTION = 64
SUMMARY_REQUEST_TIMEOUT_SECONDS = 20
TX_REQUEST_TIMEOUT_SECONDS = 45
ELECTRUM_REQUEST_TIMEOUT_SECONDS = 30
ELECTRUM_MAX_LINE_BYTES = 16 * 1024 * 1024
ELECTRUM_BALANCE_RECONCILE_SECONDS = 60 * 60
ELECTRUM_STATUS_BATCH_SIZE = 20
ELECTRUM_BASELINE_BATCH_SIZE = 20
ELECTRUM_RECONCILE_BATCH_SIZE = 8
ELECTRUM_BATCH_YIELD_SECONDS = 0.02
GAP_DISCOVERY_YIELD_SECONDS = 0.10
RUNTIME_PERSIST_MIN_INTERVAL_SECONDS = 5 * 60
_ALLOWED_QUERY_SOURCES = {"auto", "fulcrum", "electrs", "mempool_own", "mempool_public"}
_ALLOWED_ELECTRUM_KINDS = {"fulcrum", "electrs"}
_EXTENDED_PUBLIC_KEY_RE = re.compile(r"^(?:xpub|ypub|zpub)[1-9A-HJ-NP-Za-km-z]+$")
_EXTENDED_PUBLIC_KEY_WITH_ORIGIN_RE = re.compile(
    r"^(?:\[[0-9A-Fa-f]{8}(?:/[0-9]+(?:[hH\']?)?)*\])?((?:xpub|ypub|zpub)[1-9A-HJ-NP-Za-km-z]+)$",
    re.IGNORECASE,
)
_DESCRIPTOR_PREFIX_RE = re.compile(r"^(?:pkh\(|wpkh\(|sh\(wpkh\(|tr\()", re.IGNORECASE)


def _compact_watch_source(source: Any) -> str:
    """Normalize copy/paste artifacts in watch-only public material.

    XPUB/YPUB/ZPUB values and the supported descriptors are ASCII tokens and never
    need whitespace or Unicode format characters. Wallet/password-manager copy
    operations can inject line wraps, NBSPs, zero-width characters or a BOM. Those
    must be removed *before* type classification so a long extended public key can
    never fall through to the ordinary Bitcoin-address validator.
    """
    text = unicodedata.normalize("NFKC", str(source or "")).strip().strip("`\"'")
    return "".join(
        ch for ch in text
        if not ch.isspace() and unicodedata.category(ch) != "Cf"
    )


def _extract_extended_public_key(source: Any) -> str | None:
    """Extract a raw mainnet XPUB/YPUB/ZPUB from supported wallet exports.

    Besides a plain extended public key, many wallets copy account keys with an
    origin prefix such as ``[d34db33f/84h/0h/0h]zpub...``. The origin is metadata
    describing how the account key was reached; the account zpub itself already
    contains the child depth/parent fingerprint. For Sentinel account monitoring
    we therefore store the public key token, never route the long export through
    the ordinary Bitcoin-address validator.
    """
    compact = _compact_watch_source(source)
    match = _EXTENDED_PUBLIC_KEY_WITH_ORIGIN_RE.fullmatch(compact)
    return match.group(1) if match else None


def _normalize_monitor_kind(raw_kind: Any, source: str) -> str:
    """Return the effective watch kind, with the payload taking precedence.

    The content is authoritative. A recognizable XPUB/YPUB/ZPUB or supported
    descriptor is routed to its dedicated validator even if an old frontend, a
    stale browser cache or a migrated config labels it as ``address`` (or any other
    kind). Full checksum/descriptor validation still happens afterwards.
    """
    requested = str(raw_kind or "address").strip().lower()
    compact = _compact_watch_source(source)
    lowered = compact.lower()
    if _extract_extended_public_key(compact) is not None or lowered.startswith(("xpub", "ypub", "zpub")):
        return "xpub"
    if _DESCRIPTOR_PREFIX_RE.match(compact):
        return "descriptor"
    return requested

# ---- Bitcoin address / public BIP32 helpers ---------------------------------
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_MAP = {c: i for i, c in enumerate(_B58)}
_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_G = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
)
_XPUB_VERSIONS = {
    0x0488B21E: "p2pkh",        # xpub is script-ambiguous; this is only its legacy serialization hint
    0x049D7CB2: "p2sh-p2wpkh", # ypub
    0x04B24746: "p2wpkh",      # zpub
}
_ALLOWED_XPUB_ADDRESS_TYPES = {"auto", "p2pkh", "p2sh-p2wpkh", "p2wpkh", "p2tr"}
_XPUB_AUTO_CANDIDATES = ("p2wpkh", "p2sh-p2wpkh", "p2tr", "p2pkh")


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _hash160(data: bytes) -> bytes:
    return hashlib.new("ripemd160", _sha256(data)).digest()


def _tagged_hash(tag: str, payload: bytes) -> bytes:
    tag_hash = _sha256(tag.encode("ascii"))
    return _sha256(tag_hash + tag_hash + payload)


def _b58decode(value: str) -> bytes:
    number = 0
    for char in value:
        if char not in _B58_MAP:
            raise ValueError("Invalid Base58 character")
        number = number * 58 + _B58_MAP[char]
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    pad = len(value) - len(value.lstrip("1"))
    return b"\x00" * pad + raw


def _b58encode(data: bytes) -> str:
    number = int.from_bytes(data, "big")
    chars = ""
    while number:
        number, rem = divmod(number, 58)
        chars = _B58[rem] + chars
    pad = len(data) - len(data.lstrip(b"\x00"))
    return "1" * pad + (chars or "")


def _b58check_decode(value: str) -> bytes:
    raw = _b58decode(value)
    if len(raw) < 5 or _sha256(_sha256(raw[:-4]))[:4] != raw[-4:]:
        raise ValueError("Invalid Base58 checksum")
    return raw[:-4]


def _b58check(prefix: bytes, payload: bytes) -> str:
    raw = prefix + payload
    return _b58encode(raw + _sha256(_sha256(raw))[:4])


def _bech32_polymod(values: list[int]) -> int:
    chk = 1
    generators = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    for value in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ value
        for i, gen in enumerate(generators):
            if (top >> i) & 1:
                chk ^= gen
    return chk


def _bech32_hrp_expand(hrp: str) -> list[int]:
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _convertbits(data: bytes | list[int], frombits: int, tobits: int, pad: bool = True) -> list[int]:
    acc = 0
    bits = 0
    ret: list[int] = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or value >> frombits:
            raise ValueError("Invalid bit group")
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        raise ValueError("Invalid bit padding")
    return ret


def _bech32_address(program: bytes, witness_version: int = 0) -> str:
    data = [witness_version] + _convertbits(program, 8, 5)
    values = _bech32_hrp_expand("bc") + data + [0] * 6
    const = 1 if witness_version == 0 else 0x2BC830A3
    polymod = _bech32_polymod(values) ^ const
    checksum = [(polymod >> (5 * (5 - i))) & 31 for i in range(6)]
    charset = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
    return "bc1" + "".join(charset[d] for d in data + checksum)


def _bech32_decode(address: str) -> tuple[str, list[int], int]:
    if address.lower() != address and address.upper() != address:
        raise ValueError("Mixed-case Bech32 address")
    value = address.lower()
    pos = value.rfind("1")
    if pos < 1 or pos + 7 > len(value):
        raise ValueError("Invalid Bech32 address")
    hrp = value[:pos]
    charset = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
    mapping = {c: i for i, c in enumerate(charset)}
    try:
        data = [mapping[c] for c in value[pos + 1 :]]
    except KeyError as err:
        raise ValueError("Invalid Bech32 character") from err
    polymod = _bech32_polymod(_bech32_hrp_expand(hrp) + data)
    if polymod == 1:
        encoding = 1
    elif polymod == 0x2BC830A3:
        encoding = 2
    else:
        raise ValueError("Invalid Bech32 checksum")
    return hrp, data[:-6], encoding


def validate_mainnet_address(address: str) -> str:
    """Validate a mainnet P2PKH/P2SH/SegWit/Taproot address."""
    value = str(address or "").strip()
    if not value or len(value) > 100:
        raise ValueError("Bitcoin address is missing or too long")
    if value.lower().startswith("bc1"):
        hrp, data, encoding = _bech32_decode(value)
        if hrp != "bc" or not data:
            raise ValueError("Only Bitcoin mainnet addresses are supported")
        witver = data[0]
        program = bytes(_convertbits(data[1:], 5, 8, False))
        if witver > 16 or len(program) < 2 or len(program) > 40:
            raise ValueError("Invalid SegWit address")
        if witver == 0 and (encoding != 1 or len(program) not in {20, 32}):
            raise ValueError("Invalid SegWit v0 address")
        if witver > 0 and encoding != 2:
            raise ValueError("Invalid Bech32m address")
        return value.lower()
    decoded = _b58check_decode(value)
    if len(decoded) != 21 or decoded[0] not in {0x00, 0x05}:
        raise ValueError("Only Bitcoin mainnet addresses are supported")
    return value


def _inv(value: int) -> int:
    return pow(value, _P - 2, _P)


def _point_add(a: tuple[int, int] | None, b: tuple[int, int] | None) -> tuple[int, int] | None:
    if a is None:
        return b
    if b is None:
        return a
    x1, y1 = a
    x2, y2 = b
    if x1 == x2 and (y1 + y2) % _P == 0:
        return None
    if a == b:
        slope = (3 * x1 * x1) * _inv(2 * y1 % _P) % _P
    else:
        slope = (y2 - y1) * _inv((x2 - x1) % _P) % _P
    x3 = (slope * slope - x1 - x2) % _P
    y3 = (slope * (x1 - x3) - y1) % _P
    return x3, y3


def _point_mul(scalar: int, point: tuple[int, int] = _G) -> tuple[int, int] | None:
    if scalar % _N == 0:
        return None
    result = None
    addend: tuple[int, int] | None = point
    k = scalar
    while k:
        if k & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        k >>= 1
    return result


def _decode_pubkey(data: bytes) -> tuple[int, int]:
    if len(data) != 33 or data[0] not in {2, 3}:
        raise ValueError("Extended public key does not contain a compressed public key")
    x = int.from_bytes(data[1:], "big")
    alpha = (pow(x, 3, _P) + 7) % _P
    beta = pow(alpha, (_P + 1) // 4, _P)
    y = beta if (beta & 1) == (data[0] & 1) else _P - beta
    return x, y


def _encode_pubkey(point: tuple[int, int]) -> bytes:
    x, y = point
    return bytes([2 | (y & 1)]) + x.to_bytes(32, "big")


@dataclass(frozen=True)
class ExtPub:
    chain_code: bytes
    pubkey: bytes
    script_type: str


def _parse_extpub(value: str) -> ExtPub:
    value = _compact_watch_source(value)
    if not value.lower().startswith(("xpub", "ypub", "zpub")):
        raise ValueError("Extended public key must start with xpub, ypub or zpub")
    if not _EXTENDED_PUBLIC_KEY_RE.fullmatch(value):
        raise ValueError("Invalid extended public key characters")
    raw = _b58check_decode(value)
    if len(raw) != 78:
        raise ValueError("Invalid extended public key length")
    version = int.from_bytes(raw[:4], "big")
    script_type = _XPUB_VERSIONS.get(version)
    if script_type is None:
        raise ValueError("Unsupported extended public key; use mainnet xpub, ypub or zpub")
    key_data = raw[45:78]
    _decode_pubkey(key_data)
    return ExtPub(chain_code=raw[13:45], pubkey=key_data, script_type=script_type)


def _derive_pub(parent: ExtPub, index: int) -> ExtPub:
    if index < 0 or index >= 0x80000000:
        raise ValueError("Only non-hardened public derivation is supported")
    digest = hmac.new(parent.chain_code, parent.pubkey + index.to_bytes(4, "big"), hashlib.sha512).digest()
    left = int.from_bytes(digest[:32], "big")
    if left == 0 or left >= _N:
        raise ValueError("Invalid BIP32 child; choose another index")
    child = _point_add(_point_mul(left), _decode_pubkey(parent.pubkey))
    if child is None:
        raise ValueError("Invalid BIP32 child point")
    return ExtPub(chain_code=digest[32:], pubkey=_encode_pubkey(child), script_type=parent.script_type)


def _taproot_output_program(pubkey: bytes) -> bytes:
    """Return the BIP341/BIP86 key-path-only Taproot witness program."""
    point = _decode_pubkey(pubkey)
    x, y = point
    # BIP340 x-only keys use the even-Y lift of the X coordinate.
    internal = (x, y if y % 2 == 0 else (-y) % _P)
    xonly = internal[0].to_bytes(32, "big")
    tweak = int.from_bytes(_tagged_hash("TapTweak", xonly), "big")
    if tweak >= _N:
        raise ValueError("Invalid Taproot tweak")
    output = _point_add(internal, _point_mul(tweak))
    if output is None:
        raise ValueError("Invalid Taproot output key")
    return output[0].to_bytes(32, "big")


def _pubkey_address(pubkey: bytes, script_type: str) -> str:
    keyhash = _hash160(pubkey)
    if script_type == "p2pkh":
        return _b58check(b"\x00", keyhash)
    if script_type == "p2sh-p2wpkh":
        redeem = b"\x00\x14" + keyhash
        return _b58check(b"\x05", _hash160(redeem))
    if script_type == "p2wpkh":
        return _bech32_address(keyhash, 0)
    if script_type == "p2tr":
        return _bech32_address(_taproot_output_program(pubkey), 1)
    raise ValueError("Unsupported address type")


def _extpub_root_for_address_type(extpub: str, address_type: str | None = None) -> ExtPub:
    root = _parse_extpub(extpub)
    requested = str(address_type or "auto").strip().lower()
    if requested not in _ALLOWED_XPUB_ADDRESS_TYPES:
        raise ValueError("Invalid XPUB address format")
    # ypub/zpub carry an unambiguous SLIP-132 script hint. A plain xpub does not:
    # BIP44/49/84/86 account keys may all be serialized as xpub by wallet software.
    if requested == "auto":
        return root
    return ExtPub(root.chain_code, root.pubkey, requested)


def derive_extpub_addresses(
    extpub: str, receive_count: int, change_count: int, *, address_type: str | None = None
) -> list[dict[str, Any]]:
    root = _extpub_root_for_address_type(extpub, address_type)
    result: list[dict[str, Any]] = []
    for branch, count, label in ((0, receive_count, "receive"), (1, change_count, "change")):
        if count <= 0:
            continue
        branch_key = _derive_pub(root, branch)
        for index in range(count):
            child = _derive_pub(branch_key, index)
            result.append({
                "address": _pubkey_address(child.pubkey, child.script_type),
                "branch": label,
                "index": index,
            })
    return result


def derive_extpub_branch_address(
    extpub: str, branch: int, index: int, *, address_type: str | None = None
) -> dict[str, Any]:
    """Derive one concrete receive/change address without exposing private keys."""
    if branch not in {0, 1} or index < 0:
        raise ValueError("Invalid xpub branch/index")
    root = _extpub_root_for_address_type(extpub, address_type)
    branch_key = _derive_pub(root, branch)
    child = _derive_pub(branch_key, index)
    return {
        "address": _pubkey_address(child.pubkey, child.script_type),
        "branch": "receive" if branch == 0 else "change",
        "index": index,
    }


def _descriptor_payload(value: str) -> tuple[str, int | None, str | None]:
    # Strip checksum and origin metadata. This deliberately supports only the
    # simple single-key descriptors that can be derived without private keys.
    descriptor = str(value or "").strip().split("#", 1)[0]
    lowered = descriptor.lower().replace(" ", "")
    if lowered.startswith("sh(wpkh(") and lowered.endswith("))"):
        script_type = "p2sh-p2wpkh"
        inner = descriptor[8:-2]
    elif lowered.startswith("wpkh(") and lowered.endswith(")"):
        script_type = "p2wpkh"
        inner = descriptor[5:-1]
    elif lowered.startswith("pkh(") and lowered.endswith(")"):
        script_type = "p2pkh"
        inner = descriptor[4:-1]
    elif lowered.startswith("tr(") and lowered.endswith(")"):
        script_type = "p2tr"
        inner = descriptor[3:-1]
    else:
        raise ValueError("Only pkh(), wpkh(), sh(wpkh()) and tr() single-key descriptors are supported")
    inner = re.sub(r"^\[[^\]]+\]", "", inner.strip())
    match = re.search(r"((?:xpub|ypub|zpub)[1-9A-HJ-NP-Za-km-z]+)(/.*)?$", inner)
    if not match:
        raise ValueError("Descriptor must contain a mainnet xpub/ypub/zpub")
    extpub = match.group(1)
    suffix = match.group(2) or ""
    branch: int | None = None
    if suffix:
        parts = [p for p in suffix.split("/") if p]
        if not parts or parts[-1] != "*":
            raise ValueError("Descriptor must end in an unhardened /* wildcard")
        fixed = parts[:-1]
        if len(fixed) > 1:
            raise ValueError("Only one fixed branch before /* is supported")
        if fixed:
            token = fixed[0].replace(" ", "")
            if token == "<0;1>":
                # Standard multipath descriptor: expand to receive /0/* and change /1/*.
                branch = None
            elif token in {"0", "1"}:
                branch = int(token)
            else:
                raise ValueError("Descriptor branch must be /0/*, /1/* or /<0;1>/*")
    return extpub, branch, script_type


def derive_descriptor_addresses(descriptor: str, receive_count: int, change_count: int) -> list[dict[str, Any]]:
    extpub, branch, script_type = _descriptor_payload(descriptor)
    root = _parse_extpub(extpub)
    # Descriptor wrapper is authoritative; SLIP-132 prefix is only a convenient hint.
    root = ExtPub(root.chain_code, root.pubkey, script_type or root.script_type)
    result: list[dict[str, Any]] = []
    branches = ((branch, receive_count if branch == 0 else change_count),) if branch in {0, 1} else ((0, receive_count), (1, change_count))
    for branch_value, count in branches:
        if count <= 0:
            continue
        branch_key = _derive_pub(root, int(branch_value))
        for index in range(count):
            child = _derive_pub(branch_key, index)
            result.append({
                "address": _pubkey_address(child.pubkey, child.script_type),
                "branch": "receive" if branch_value == 0 else "change",
                "index": index,
            })
    return result


def derive_descriptor_branch_address(descriptor: str, branch: int, index: int) -> dict[str, Any] | None:
    """Derive one descriptor address, respecting an optional fixed /0/* or /1/* branch."""
    if branch not in {0, 1} or index < 0:
        raise ValueError("Invalid descriptor branch/index")
    extpub, fixed_branch, script_type = _descriptor_payload(descriptor)
    if fixed_branch in {0, 1} and fixed_branch != branch:
        return None
    root = _parse_extpub(extpub)
    root = ExtPub(root.chain_code, root.pubkey, script_type or root.script_type)
    branch_key = _derive_pub(root, branch)
    child = _derive_pub(branch_key, index)
    return {
        "address": _pubkey_address(child.pubkey, child.script_type),
        "branch": "receive" if branch == 0 else "change",
        "index": index,
    }



def _normalize_notification_url(value: Any) -> str:
    """Validate a notification endpoint without weakening the network policy."""
    raw = str(value or "").strip()
    if not raw or len(raw) > MAX_NOTIFICATION_URL_LENGTH:
        raise ValueError("Notification target URL is missing or too long")
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Notification targets must use an explicit http:// or https:// URL")
    if parsed.username or parsed.password:
        raise ValueError("Credentials are not allowed inside notification URLs; use the token field")
    if parsed.fragment:
        raise ValueError("Notification target URLs may not contain fragments")
    if (
        not is_private_or_local_url(raw)
        and not is_onion_url(raw)
        and parsed.scheme.lower() != "https"
    ):
        raise ValueError("Public notification targets require HTTPS; onion and local targets may use HTTP")
    return raw


def _normalize_notification_targets(raw: Any) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw or []):
        if not isinstance(item, dict):
            continue
        target_id = str(item.get("id") or f"notify_{index + 1}").strip()[:64]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", target_id) or target_id in seen_ids:
            raise ValueError("Notification target IDs must be unique letters/numbers/_/-")
        seen_ids.add(target_id)
        kind = str(item.get("kind") or "ntfy").strip().lower()
        if kind not in {"ntfy", "webhook"}:
            raise ValueError("Notification target type must be ntfy or webhook")
        label = str(item.get("label") or ("ntfy" if kind == "ntfy" else "Webhook")).strip()[:120]
        url = _normalize_notification_url(item.get("url"))
        detail = str(item.get("detail") or "inherit").strip().lower()
        if detail not in {"inherit", "discreet", "normal", "detailed"}:
            raise ValueError("Notification target detail must be inherit, discreet, normal or detailed")
        token = str(item.get("token") or "").strip()
        if len(token) > MAX_NOTIFICATION_TOKEN_LENGTH or "\r" in token or "\n" in token:
            raise ValueError("Notification target token is invalid or too long")
        verify_ssl = bool(item.get("verify_ssl", True))
        if not verify_ssl and not (is_private_or_local_url(url) or is_onion_url(url)):
            raise ValueError("TLS verification can only be disabled for local or onion notification targets")
        targets.append({
            "id": target_id,
            "label": label,
            "kind": kind,
            "url": url,
            "token": token,
            "enabled": bool(item.get("enabled", True)),
            "detail": detail,
            "verify_ssl": verify_ssl,
        })
    if len(targets) > MAX_NOTIFICATION_TARGETS:
        raise ValueError(f"A maximum of {MAX_NOTIFICATION_TARGETS} notification targets is allowed")
    return targets



def _normalize_electrum_pinned_certificate(raw: Any) -> tuple[str, str]:
    """Validate one PEM X.509 certificate and return normalized PEM + SHA-256 pin."""
    pem = str(raw or "").strip()
    if not pem:
        return "", ""
    if len(pem) > MAX_ELECTRUM_CERT_PEM_LENGTH:
        raise ValueError("Fulcrum/Electrum certificate PEM is too large")
    upper = pem.upper()
    if "PRIVATE KEY" in upper:
        raise ValueError("Only the public Fulcrum/Electrum certificate is allowed; never paste a private key")
    if pem.count("-----BEGIN CERTIFICATE-----") != 1 or pem.count("-----END CERTIFICATE-----") != 1:
        raise ValueError("Paste exactly one PEM X.509 certificate")
    try:
        cert = x509.load_pem_x509_certificate(pem.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as err:
        raise ValueError("Invalid Fulcrum/Electrum PEM certificate") from err
    normalized = cert.public_bytes(encoding=serialization.Encoding.PEM).decode("ascii").strip()
    fingerprint = cert.fingerprint(hashes.SHA256()).hex()
    return normalized, fingerprint

def normalize_watch_config(raw: Any) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    interval = int(data.get("poll_interval_seconds") or DEFAULT_POLL_SECONDS)
    if interval not in _ALLOWED_POLL_SECONDS:
        raise ValueError("Sats Sentinel interval must be 30, 60, 120 or 300 seconds")
    detail = str(data.get("notification_detail") or "discreet").lower()
    if detail not in {"discreet", "normal", "detailed"}:
        raise ValueError("Invalid Sats Sentinel notification detail")
    services = []
    for item in data.get("notification_services") or []:
        name = str(item or "").strip()
        if name and re.fullmatch(r"[a-z0-9_]+", name) and name not in services:
            services.append(name[:128])
    notification_targets = _normalize_notification_targets(data.get("notification_targets"))
    monitors = []
    seen_ids: set[str] = set()
    for index, item in enumerate(data.get("monitors") or []):
        if not isinstance(item, dict):
            continue
        monitor_id = str(item.get("id") or f"watch_{index + 1}").strip()[:64]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", monitor_id) or monitor_id in seen_ids:
            raise ValueError("Sats Sentinel monitor IDs must be unique letters/numbers/_/-")
        seen_ids.add(monitor_id)
        label = str(item.get("label") or f"Wallet {index + 1}").strip()[:120]
        source = str(item.get("value") or "").strip()
        kind = _normalize_monitor_kind(item.get("kind"), source)
        if kind == "xpub":
            source = _extract_extended_public_key(source) or _compact_watch_source(source)
        elif kind == "descriptor":
            source = _compact_watch_source(source)
        receive_count = max(0, min(MAX_DERIVED_PER_BRANCH, int(item.get("receive_count") or 0)))
        change_count = max(0, min(MAX_DERIVED_PER_BRANCH, int(item.get("change_count") or 0)))
        address_type = str(item.get("address_type") or "auto").strip().lower()
        if address_type not in _ALLOWED_XPUB_ADDRESS_TYPES:
            raise ValueError(f"Sats Sentinel monitor '{label}': invalid XPUB address format")
        if kind != "xpub":
            address_type = "auto"
        try:
            history_limit_raw = int(item.get("history_limit", DEFAULT_TX_OVERVIEW_LIMIT))
        except (TypeError, ValueError):
            history_limit_raw = DEFAULT_TX_OVERVIEW_LIMIT
        history_limit = history_limit_raw if history_limit_raw in ALLOWED_TX_OVERVIEW_LIMITS else DEFAULT_TX_OVERVIEW_LIMIT
        created_at = str(item.get("created_at") or "").strip()[:40]
        try:
            if kind == "address":
                source = validate_mainnet_address(source)
                receive_count = change_count = 0
            elif kind == "xpub":
                _parse_extpub(source)
            elif kind == "descriptor":
                _descriptor_payload(source)
            else:
                raise ValueError("Sats Sentinel type must be address, xpub or descriptor")
        except ValueError as err:
            raise ValueError(f"Sats Sentinel monitor '{label}' ({kind}): {err}") from err
        category = str(item.get("category") or "other").strip().lower()
        if category not in _ALLOWED_WATCH_CATEGORIES:
            category = "other"
        note = str(item.get("note") or "").strip()[:500]
        min_notify_sats = max(0, min(2_100_000_000_000_000, int(item.get("min_notify_sats") or 0)))
        monitor_detail = str(item.get("notification_detail") or detail).strip().lower()
        if monitor_detail not in {"discreet", "normal", "detailed"}:
            raise ValueError(f"Sats Sentinel monitor '{label}': invalid notification detail")
        monitors.append({
            "id": monitor_id,
            "label": label,
            "kind": kind,
            "value": source,
            "enabled": bool(item.get("enabled", True)),
            "receive_count": receive_count,
            "change_count": change_count,
            "address_type": address_type,
            "history_limit": history_limit,
            "created_at": created_at,
            "category": category,
            "note": note,
            "min_notify_sats": min_notify_sats,
            # The server-level notification_detail is only the creation default.
            # Once a watch target exists, its own mode is authoritative for all
            # activity notifications from that wallet/address.
            "notification_detail": monitor_detail,
            "notify_incoming": bool(item.get("notify_incoming", True)),
            "notify_outgoing": bool(item.get("notify_outgoing", True)),
            "notify_ha_event": bool(item.get("notify_ha_event", True)),
            "notify_persistent": bool(item.get("notify_persistent", True)),
            "notify_services": bool(item.get("notify_services", True)),
            "notify_external": bool(item.get("notify_external", True)),
        })
    if len(monitors) > MAX_MONITORS:
        raise ValueError(f"A maximum of {MAX_MONITORS} Sats Sentinel monitors is allowed")
    log_display_mode = str(data.get("log_display_mode") or "days").strip().lower()
    if log_display_mode not in _ALLOWED_LOG_DISPLAY_MODES:
        log_display_mode = "days"
    log_display_count = max(1, min(MAX_LOG_DISPLAY_COUNT, int(data.get("log_display_count") or 100)))
    log_display_days = max(1, min(MAX_LOG_DISPLAY_DAYS, int(data.get("log_display_days") or 30)))
    query_source = str(data.get("query_source") or "auto").strip().lower()
    if query_source not in _ALLOWED_QUERY_SOURCES:
        query_source = "auto"
    electrum_kind = str(data.get("electrum_kind") or "fulcrum").strip().lower()
    if electrum_kind not in _ALLOWED_ELECTRUM_KINDS:
        electrum_kind = "fulcrum"
    if query_source in _ALLOWED_ELECTRUM_KINDS:
        electrum_kind = query_source
    electrum_host = str(data.get("electrum_host") or "").strip()[:255]
    for prefix in ("tcp://", "ssl://", "tls://"):
        if electrum_host.lower().startswith(prefix):
            electrum_host = electrum_host[len(prefix):]
            break
    if "/" in electrum_host:
        electrum_host = electrum_host.split("/", 1)[0]
    if electrum_host.startswith("[") and electrum_host.endswith("]"):
        electrum_host = electrum_host[1:-1]
    electrum_port = max(1, min(65535, int(data.get("electrum_port") or (50002 if bool(data.get("electrum_tls", False)) else 50001))))
    electrum_tls = bool(data.get("electrum_tls", False))
    electrum_verify_ssl = bool(data.get("electrum_verify_ssl", True))
    electrum_pinned_cert_pem, electrum_pinned_cert_sha256 = _normalize_electrum_pinned_certificate(
        data.get("electrum_pinned_cert_pem")
    )
    # The device-bound Sentinel runtime vault persists only the public certificate
    # SHA-256 pin, not the PEM text. Accept that already-normalized pin when the
    # PEM is absent so locked-vault monitor edits can retain the exact TLS trust
    # boundary without requiring the portfolio vault to be open.
    if not electrum_pinned_cert_sha256:
        cached_pin = str(data.get("electrum_pinned_cert_sha256") or "").strip().lower()
        if cached_pin and re.fullmatch(r"[0-9a-f]{64}", cached_pin):
            electrum_pinned_cert_sha256 = cached_pin
    if electrum_pinned_cert_pem and not electrum_tls:
        raise ValueError("A pinned Fulcrum/Electrum certificate requires TLS / SSL")
    if electrum_host and not electrum_verify_ssl and not electrum_pinned_cert_sha256:
        host_url = f"http://[{electrum_host}]:{electrum_port}" if ":" in electrum_host else f"http://{electrum_host}:{electrum_port}"
        if not (is_private_or_local_url(host_url) or electrum_host.lower().rstrip(".").endswith(".onion")):
            raise ValueError("Electrum TLS verification can only be disabled for local/private or onion targets")
    return {
        "enabled": bool(data.get("enabled", False)),
        "poll_interval_seconds": interval,
        "query_source": query_source,
        "electrum_kind": electrum_kind,
        "electrum_host": electrum_host,
        "electrum_port": electrum_port,
        "electrum_tls": electrum_tls,
        "electrum_verify_ssl": electrum_verify_ssl,
        "electrum_pinned_cert_pem": electrum_pinned_cert_pem,
        "electrum_pinned_cert_sha256": electrum_pinned_cert_sha256,
        "allow_public_tor": bool(data.get("allow_public_tor", False)),
        "persistent_notification": bool(data.get("persistent_notification", True)),
        "notification_detail": detail,
        "notification_services": services,
        "notification_targets": notification_targets,
        "log_display_mode": log_display_mode,
        "log_display_count": log_display_count,
        "log_display_days": log_display_days,
        "monitors": monitors,
    }


def runtime_cache_from_config(config: dict[str, Any]) -> dict[str, Any]:
    addresses: list[dict[str, Any]] = []
    for monitor_slot, monitor in enumerate(config.get("monitors", []), start=1):
        if not monitor.get("enabled", True):
            continue
        kind = monitor["kind"]
        if kind == "address":
            derived = [{"address": monitor["value"], "branch": "fixed", "index": None}]
        elif kind == "xpub":
            seed_type = str(monitor.get("address_type") or "auto")
            # For ambiguous plain xpubs the real script type is discovered against
            # Fulcrum/electrs in the background. Native SegWit is the least-surprising
            # temporary seed while discovery is pending.
            if seed_type == "auto" and str(monitor["value"]).lower().startswith("xpub"):
                seed_type = "p2wpkh"
            derived = derive_extpub_addresses(
                monitor["value"], monitor["receive_count"], monitor["change_count"],
                address_type=seed_type,
            )
        else:
            derived = derive_descriptor_addresses(monitor["value"], monitor["receive_count"], monitor["change_count"])
        for row in derived:
            addresses.append({
                "monitor_id": monitor["id"],
                "monitor_slot": monitor_slot,
                "address": row["address"],
                "branch": row["branch"],
                "index": row["index"],
                "gap_limit": (
                    int(monitor.get("receive_count") or 0) if row["branch"] == "receive"
                    else int(monitor.get("change_count") or 0) if row["branch"] == "change"
                    else 0
                ),
                "active": True,
                "used": None,
                "notify_incoming": monitor["notify_incoming"],
                "notify_outgoing": monitor["notify_outgoing"],
                "category": monitor.get("category", "other"),
                "min_notify_sats": int(monitor.get("min_notify_sats") or 0),
                "notification_detail": str(monitor.get("notification_detail") or config.get("notification_detail") or "discreet"),
                "notify_ha_event": bool(monitor.get("notify_ha_event", True)),
                "notify_persistent": bool(monitor.get("notify_persistent", True)),
                "notify_services": bool(monitor.get("notify_services", True)),
                "notify_external": bool(monitor.get("notify_external", True)),
                "baseline_complete": False,
                "summary_signature": None,
                "known_txids": [],
                # Do not persist individual UTXOs. The local address summary
                # already exposes funded/spent output counts, which is enough
                # for Sentinel status while minimizing sensitive runtime data.
                "utxo_count": 0,
                "balance_sats": 0,
                "last_activity_at": None,
                "last_balance_refresh_unix": 0,
            })
    if len(addresses) > MAX_RUNTIME_ADDRESSES:
        raise ValueError(f"Sats Sentinel runtime address limit is {MAX_RUNTIME_ADDRESSES}")
    # Watch-only monitor catalog for the separately encrypted Sentinel vault.
    # XPUB/YPUB/ZPUB/descriptor/address material contains no spending keys, but it
    # is privacy-sensitive. It is therefore stored only inside the device-bound
    # AES-256-GCM runtime vault so Sentinel can remain fully manageable while the
    # password-protected portfolio vault is locked. Seeds/private extended keys
    # are rejected by normalize_watch_config before this point.
    monitor_catalog = [
        {
            "id": str(monitor.get("id") or ""),
            "label": str(monitor.get("label") or ""),
            "kind": str(monitor.get("kind") or "address"),
            "watch_value": str(monitor.get("value") or ""),
            "category": str(monitor.get("category") or "other"),
            "enabled": bool(monitor.get("enabled", True)),
            "receive_count": int(monitor.get("receive_count") or 0),
            "change_count": int(monitor.get("change_count") or 0),
            "address_type": str(monitor.get("address_type") or "auto"),
            "history_limit": int(monitor.get("history_limit") if monitor.get("history_limit") is not None else 10),
            "note": str(monitor.get("note") or "")[:500],
            "min_notify_sats": int(monitor.get("min_notify_sats") or 0),
            "notification_detail": str(monitor.get("notification_detail") or config.get("notification_detail") or "discreet"),
            "notify_incoming": bool(monitor.get("notify_incoming", True)),
            "notify_outgoing": bool(monitor.get("notify_outgoing", True)),
            "notify_ha_event": bool(monitor.get("notify_ha_event", True)),
            "notify_persistent": bool(monitor.get("notify_persistent", True)),
            "notify_services": bool(monitor.get("notify_services", True)),
            "notify_external": bool(monitor.get("notify_external", True)),
            "created_at": str(monitor.get("created_at") or "")[:40],
        }
        for monitor in config.get("monitors", [])
        if isinstance(monitor, dict) and str(monitor.get("id") or "")
    ]
    return {
        "schema": WATCH_CACHE_SCHEMA,
        "enabled": bool(config.get("enabled")),
        "poll_interval_seconds": int(config.get("poll_interval_seconds") or DEFAULT_POLL_SECONDS),
        "query_source": str(config.get("query_source") or "auto"),
        "electrum_kind": str(config.get("electrum_kind") or "fulcrum"),
        "electrum_host": str(config.get("electrum_host") or ""),
        "electrum_port": int(config.get("electrum_port") or 50001),
        "electrum_tls": bool(config.get("electrum_tls")),
        "electrum_verify_ssl": bool(config.get("electrum_verify_ssl", True)),
        # Only the SHA-256 certificate pin is needed while the password vault is locked.
        # The PEM itself remains in the main encrypted Sentinel configuration.
        "electrum_pinned_cert_sha256": str(config.get("electrum_pinned_cert_sha256") or ""),
        "allow_public_tor": bool(config.get("allow_public_tor")),
        "persistent_notification": bool(config.get("persistent_notification", True)),
        "notification_detail": str(config.get("notification_detail") or "discreet"),
        "notification_services": list(config.get("notification_services") or []),
        "notification_targets": deepcopy(config.get("notification_targets") or []),
        "monitor_catalog": monitor_catalog,
        "pending_vault_sync": False,
        "addresses": addresses,
        "activity_log": [],
        "activity_log_trimmed_total": 0,
        "last_poll_at": None,
        "last_success_at": None,
        "last_error": None,
        "last_warning": None,
        "partial_failures": 0,
        "last_partial_at": None,
        "error_streak": 0,
        "outage_notified": False,
        "last_notification_success_at": None,
        "last_notification_error": None,
        "notification_delivery_failures": 0,
    }


class WalletWatchRuntimeStore:
    """Device-bound encrypted cache that remains available while the user vault is locked."""

    def __init__(self, hass: HomeAssistant, entry_id: str, device_secret_loader) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._store = Store[dict[str, Any]](hass, WATCH_STORAGE_VERSION, f"{WATCH_STORAGE_KEY}.{entry_id}")
        # Connection settings live in a second device-bound encrypted store.
        # It is intentionally independent from the runtime-cache schema so a
        # custom-component update/reload cannot make a saved Fulcrum/electrs
        # endpoint disappear just because runtime state is rebuilt/migrated.
        self._endpoint_store = Store[dict[str, Any]](
            hass, WATCH_ENDPOINT_STORAGE_VERSION, f"{WATCH_ENDPOINT_STORAGE_KEY}.{entry_id}"
        )
        self._device_secret_loader = device_secret_loader
        self.data: dict[str, Any] = runtime_cache_from_config({})
        self.endpoint_data: dict[str, Any] = {}
        self._last_save_monotonic = 0.0

    async def _key(self) -> bytes:
        secret = await self._device_secret_loader(create=True)
        return HKDF(
            algorithm=hashes.SHA256(), length=32,
            salt=self.entry_id.encode("utf-8"),
            info=b"bitcoin-stack-tracker:wallet-watch-runtime:v1",
        ).derive(secret)

    async def _endpoint_key(self) -> bytes:
        secret = await self._device_secret_loader(create=True)
        return HKDF(
            algorithm=hashes.SHA256(), length=32,
            salt=self.entry_id.encode("utf-8"),
            info=b"bitcoin-stack-tracker:wallet-watch-endpoint:v1",
        ).derive(secret)

    @staticmethod
    def _endpoint_payload(config: dict[str, Any]) -> dict[str, Any]:
        """Return the durable Sentinel connection subset.

        No seed/private-key material is ever part of this store.  The server
        certificate is represented only by its public SHA-256 pin, not the PEM.
        """
        return {
            "schema": WATCH_ENDPOINT_SCHEMA,
            "query_source": str(config.get("query_source") or "auto"),
            "electrum_kind": str(config.get("electrum_kind") or "fulcrum"),
            "electrum_host": str(config.get("electrum_host") or ""),
            "electrum_port": int(config.get("electrum_port") or 50001),
            "electrum_tls": bool(config.get("electrum_tls")),
            "electrum_verify_ssl": bool(config.get("electrum_verify_ssl", True)),
            "electrum_pinned_cert_sha256": str(config.get("electrum_pinned_cert_sha256") or ""),
            "allow_public_tor": bool(config.get("allow_public_tor")),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _async_load_endpoint_backup(self) -> dict[str, Any]:
        raw = await self._endpoint_store.async_load()
        if not isinstance(raw, dict) or raw.get("encrypted") is not True:
            self.endpoint_data = {}
            return {}
        try:
            key = await self._endpoint_key()
            nonce = base64.urlsafe_b64decode(str(raw["nonce"]).encode("ascii"))
            ciphertext = base64.urlsafe_b64decode(str(raw["ciphertext"]).encode("ascii"))
            plain = AESGCM(key).decrypt(
                nonce, ciphertext, f"wallet-watch-endpoint:{self.entry_id}".encode()
            )
            loaded = json.loads(plain.decode("utf-8"))
            if isinstance(loaded, dict) and int(loaded.get("schema") or 0) == WATCH_ENDPOINT_SCHEMA:
                self.endpoint_data = loaded
                return loaded
        except Exception:
            # A damaged endpoint backup must never destroy the richer runtime
            # cache or prevent Home Assistant from starting.
            self.endpoint_data = {}
        return {}

    async def async_save_endpoint_from_config(self, config: dict[str, Any]) -> None:
        payload = self._endpoint_payload(config)
        key = await self._endpoint_key()
        nonce = os.urandom(12)
        plain = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ciphertext = AESGCM(key).encrypt(
            nonce, plain, f"wallet-watch-endpoint:{self.entry_id}".encode()
        )
        await self._endpoint_store.async_save({
            "encrypted": True,
            "format": "AES-256-GCM-device-bound-endpoint-v1",
            "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
            "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
        })
        self.endpoint_data = payload

    def _overlay_endpoint_backup(self) -> None:
        if not self.endpoint_data:
            return
        for key in (
            "query_source", "electrum_kind", "electrum_host", "electrum_port",
            "electrum_tls", "electrum_verify_ssl", "electrum_pinned_cert_sha256",
            "allow_public_tor",
        ):
            if key in self.endpoint_data:
                self.data[key] = deepcopy(self.endpoint_data[key])

    async def async_load(self) -> None:
        raw = await self._store.async_load()
        if isinstance(raw, dict) and raw.get("encrypted") is True:
            try:
                key = await self._key()
                nonce = base64.urlsafe_b64decode(str(raw["nonce"]).encode("ascii"))
                ciphertext = base64.urlsafe_b64decode(str(raw["ciphertext"]).encode("ascii"))
                plain = AESGCM(key).decrypt(nonce, ciphertext, f"wallet-watch:{self.entry_id}".encode())
                loaded = json.loads(plain.decode("utf-8"))
                if isinstance(loaded, dict) and int(loaded.get("schema") or 0) == WATCH_CACHE_SCHEMA:
                    self.data = loaded
                    activity_log = [
                        item for item in self.data.get("activity_log", []) if isinstance(item, dict)
                    ]
                    if len(activity_log) > MAX_STORED_ACTIVITY_LOG:
                        # Existing busy-address installations may have accumulated
                        # an unbounded journal in older builds. Keep the newest
                        # records immediately so startup RAM is bounded as well.
                        activity_log.sort(key=lambda item: str(item.get("detected_at") or ""))
                        self.data["activity_log"] = activity_log[-MAX_STORED_ACTIVITY_LOG:]
                        self.data["activity_log_trimmed_total"] = int(
                            self.data.get("activity_log_trimmed_total") or 0
                        ) + (len(activity_log) - MAX_STORED_ACTIVITY_LOG)
                    self._last_save_monotonic = asyncio.get_running_loop().time()
            except Exception as err:
                self.data = runtime_cache_from_config({})
                self.data["last_error"] = f"Encrypted Sats Sentinel cache could not be opened: {type(err).__name__}"

        # Load the source endpoint independently from the larger runtime cache.
        # This survives integration updates/reloads and also protects against a
        # future runtime-cache schema migration resetting the node selection.
        endpoint = await self._async_load_endpoint_backup()
        if endpoint:
            self._overlay_endpoint_backup()
        elif str(self.data.get("electrum_host") or "").strip():
            # One-time migration for existing installations: seed the durable
            # endpoint store from an already valid rc14-or-earlier runtime cache.
            await self.async_save_endpoint_from_config(self.data)

    async def async_save(self) -> None:
        key = await self._key()
        nonce = os.urandom(12)
        plain = json.dumps(self.data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ciphertext = AESGCM(key).encrypt(nonce, plain, f"wallet-watch:{self.entry_id}".encode())
        await self._store.async_save({
            "encrypted": True,
            "format": "AES-256-GCM-device-bound-v1",
            "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
            "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
        })
        self._last_save_monotonic = asyncio.get_running_loop().time()

    async def async_save_if_due(self, *, force: bool = False, min_interval: int = RUNTIME_PERSIST_MIN_INTERVAL_SECONDS) -> bool:
        """Persist runtime state at a bounded cadence to avoid HA storage churn.

        Poll timestamps and unchanged balance snapshots do not need an encrypted
        disk rewrite every 30/60 seconds. Activity/configuration paths still call
        ``async_save`` directly; normal polling uses this coalesced path.
        """
        now = asyncio.get_running_loop().time()
        if not force and self._last_save_monotonic > 0 and now - self._last_save_monotonic < max(1, int(min_interval)):
            return False
        await self.async_save()
        return True

    async def async_remove(self) -> None:
        await self._store.async_remove()
        await self._endpoint_store.async_remove()
        self.data = runtime_cache_from_config({})
        self.endpoint_data = {}

    async def async_replace_from_full_config(self, config: dict[str, Any]) -> int:
        source_keys = (
            "query_source", "electrum_kind", "electrum_host", "electrum_port",
            "electrum_tls", "electrum_verify_ssl", "electrum_pinned_cert_sha256", "allow_public_tor",
        )
        old_source_fingerprint = tuple(self.data.get(key) for key in source_keys)
        old_by_key = {
            (str(row.get("monitor_id")), str(row.get("address"))): row
            for row in self.data.get("addresses", []) if isinstance(row, dict)
        }
        old_catalog = {
            str(item.get("id") or ""): item
            for item in self.data.get("monitor_catalog", [])
            if isinstance(item, dict) and str(item.get("id") or "")
        }
        new_monitor_map = {
            str(item.get("id") or ""): item
            for item in config.get("monitors", [])
            if isinstance(item, dict) and str(item.get("id") or "")
        }
        old_monitor_ids = {
            str(row.get("monitor_id") or "")
            for row in self.data.get("addresses", []) if isinstance(row, dict) and str(row.get("monitor_id") or "")
        } | {
            str(item.get("monitor_id") or "")
            for item in self.data.get("activity_log", []) if isinstance(item, dict) and str(item.get("monitor_id") or "")
        }
        new_monitor_ids = {str(item.get("id") or "") for item in config.get("monitors", []) if isinstance(item, dict)}
        removed_monitor_ids = old_monitor_ids - new_monitor_ids
        fresh = runtime_cache_from_config(config)
        # If the watch-only key itself did not change, keep the complete already
        # discovered HD range instead of collapsing the wallet to the initial gap
        # seed addresses. This is especially important for locked edits and source
        # changes: labels/alerts/server settings must never make used addresses
        # disappear while a background reconciliation is still running.
        fresh_keys = {
            (str(row.get("monitor_id") or ""), str(row.get("address") or ""))
            for row in fresh.get("addresses", []) if isinstance(row, dict)
        }
        for old_row in self.data.get("addresses", []):
            if not isinstance(old_row, dict):
                continue
            monitor_id = str(old_row.get("monitor_id") or "")
            monitor = new_monitor_map.get(monitor_id)
            old_mon = old_catalog.get(monitor_id)
            if not monitor or not old_mon or not monitor.get("enabled", True):
                continue
            if str(old_mon.get("kind") or "") != str(monitor.get("kind") or ""):
                continue
            if str(old_mon.get("watch_value") or "") != str(monitor.get("value") or ""):
                continue
            key = (monitor_id, str(old_row.get("address") or ""))
            if not key[1] or key in fresh_keys:
                continue
            preserved = deepcopy(old_row)
            branch = str(preserved.get("branch") or "")
            preserved["gap_limit"] = (
                int(monitor.get("receive_count") or 0) if branch == "receive"
                else int(monitor.get("change_count") or 0) if branch == "change"
                else 0
            )
            for setting_key in (
                "notify_incoming", "notify_outgoing", "category", "min_notify_sats",
                "notification_detail", "notify_ha_event", "notify_persistent",
                "notify_services", "notify_external",
            ):
                if setting_key == "category":
                    preserved[setting_key] = str(monitor.get(setting_key) or "other")
                elif setting_key == "min_notify_sats":
                    preserved[setting_key] = int(monitor.get(setting_key) or 0)
                elif setting_key == "notification_detail":
                    preserved[setting_key] = str(monitor.get(setting_key) or "discreet")
                else:
                    preserved[setting_key] = bool(monitor.get(setting_key, True))
            fresh["addresses"].append(preserved)
            fresh_keys.add(key)
        fresh["addresses"].sort(key=lambda row: (
            str(row.get("monitor_id") or ""),
            {"fixed": -1, "receive": 0, "change": 1}.get(str(row.get("branch") or ""), 9),
            -1 if row.get("index") is None else int(row.get("index") or 0),
        ))
        # Preserve baseline/known tx state for addresses that remain monitored.
        for row in fresh["addresses"]:
            old = old_by_key.get((row["monitor_id"], row["address"]))
            if not old:
                continue
            for key in ("baseline_complete", "summary_signature", "known_txids", "utxo_count", "balance_sats", "last_activity_at", "last_balance_refresh_unix", "active", "used", "gap_limit"):
                row[key] = deepcopy(old.get(key, row.get(key)))
            # Migrate older Sentinel caches that stored the full UTXO list.
            if "utxo_count" not in old and isinstance(old.get("utxos"), list):
                row["utxo_count"] = len(old.get("utxos") or [])
        old_activity_log = [item for item in self.data.get("activity_log", []) if isinstance(item, dict)]
        fresh["activity_log"] = [
            deepcopy(item) for item in old_activity_log
            if str(item.get("monitor_id") or "") not in removed_monitor_ids
        ]
        purged_activity_count = len(old_activity_log) - len(fresh["activity_log"])
        for key in ("last_poll_at", "last_success_at", "last_error", "last_warning", "partial_failures", "last_partial_at", "error_streak", "outage_notified", "last_notification_success_at", "last_notification_error", "notification_delivery_failures"):
            fresh[key] = deepcopy(self.data.get(key, fresh.get(key)))
        new_source_fingerprint = tuple(fresh.get(key) for key in source_keys)
        if new_source_fingerprint != old_source_fingerprint:
            # Never show an outage from the previously selected endpoint after
            # the user has saved a different source. The next source probe/poll
            # establishes the new health state.
            fresh["last_poll_at"] = None
            fresh["last_success_at"] = None
            fresh["last_error"] = None
            fresh["last_warning"] = None
            fresh["partial_failures"] = 0
            fresh["last_partial_at"] = None
            fresh["error_streak"] = 0
            fresh["outage_notified"] = False
        self.data = fresh
        # A non-empty endpoint from the authoritative full config refreshes the
        # durable endpoint backup. If the full config is temporarily empty/stale,
        # keep and re-apply the previous endpoint instead of erasing it.
        if str(fresh.get("electrum_host") or "").strip():
            await self.async_save_endpoint_from_config(fresh)
        elif self.endpoint_data and str(self.endpoint_data.get("electrum_host") or "").strip():
            self._overlay_endpoint_backup()
        await self.async_save()
        return purged_activity_count

    async def async_update_settings_from_config(self, config: dict[str, Any]) -> bool:
        """Update server/global Sentinel settings without rebuilding watches.

        Saving a Fulcrum/electrs endpoint, polling interval or global notification
        default must never collapse an already discovered HD wallet back to the
        raw gap seed addresses.  The monitor catalog, concrete runtime addresses,
        baselines, balances, UTXOs and journal therefore remain byte-for-byte
        intact; only server/global settings are replaced.
        """
        normalized = normalize_watch_config(config)
        source_keys = (
            "query_source", "electrum_kind", "electrum_host", "electrum_port",
            "electrum_tls", "electrum_verify_ssl", "electrum_pinned_cert_sha256",
            "allow_public_tor",
        )
        old_source_fingerprint = tuple(self.data.get(key) for key in source_keys)
        old_enabled = bool(self.data.get("enabled"))
        for key in (
            "enabled", "poll_interval_seconds", "query_source", "electrum_kind",
            "electrum_host", "electrum_port", "electrum_tls",
            "electrum_verify_ssl", "electrum_pinned_cert_sha256",
            "allow_public_tor", "persistent_notification", "notification_detail",
            "notification_services", "notification_targets",
        ):
            self.data[key] = deepcopy(normalized.get(key))
        new_source_fingerprint = tuple(self.data.get(key) for key in source_keys)
        if new_source_fingerprint != old_source_fingerprint:
            self.data["last_poll_at"] = None
            self.data["last_success_at"] = None
            self.data["last_error"] = None
            self.data["last_warning"] = None
            self.data["partial_failures"] = 0
            self.data["last_partial_at"] = None
            self.data["error_streak"] = 0
            self.data["outage_notified"] = False
        await self.async_save()
        await self.async_save_endpoint_from_config(self.data)
        return bool(new_source_fingerprint != old_source_fingerprint or (bool(normalized.get("enabled")) and not old_enabled))


def _canonical_mempool_base_url(raw_url: Any) -> str:
    """Return a mempool web root from either a root URL or a copied API URL.

    Existing installations normally store e.g. ``http://192.168.1.20:3006``.
    Some migrated/manual configurations can contain ``/api``, ``/api/v1`` or
    even the validated ``/api/v1/prices`` endpoint.  Sats Sentinel needs the
    same node's address API at ``/api/address/...``; normalize only these known
    mempool API suffixes and preserve any reverse-proxy prefix before them.
    """
    raw = str(raw_url or "").strip().rstrip("/")
    if not raw:
        return ""
    parsed = urlparse(raw)
    path = (parsed.path or "").rstrip("/")
    lower = path.lower()
    for suffix in ("/api/v1/prices", "/api/v1", "/api"):
        if lower.endswith(suffix):
            path = path[: -len(suffix)].rstrip("/")
            break
    return urlunparse(parsed._replace(path=path, params="", query="", fragment="")).rstrip("/")


def _is_own_mempool_source(raw: Any) -> bool:
    """Recognize the user's own mempool source across current and legacy configs.

    Current entries persist ``mempool_own_instance``. Older/migrated entries may
    still only carry the fixed direct route, while very old local entries can be
    identified by a private/local URL. Public/onion sources are never inferred as
    own merely from being a mempool source.
    """
    if not isinstance(raw, dict) or raw.get(CONF_SOURCE_TYPE) != SOURCE_MEMPOOL:
        return False
    if bool(raw.get(CONF_MEMPOOL_OWN_INSTANCE, False)):
        return True
    if str(raw.get(CONF_MEMPOOL_ROUTE) or "").lower() == MEMPOOL_ROUTE_DIRECT:
        return True
    base = _canonical_mempool_base_url(raw.get(CONF_BASE_URL))
    return bool(base and is_private_or_local_url(base) and not is_onion_url(base))


def _configured_public_mempool_sources(entry: ConfigEntry) -> list[dict[str, Any]]:
    """Return explicitly configured non-own mempool sources in user order.

    No implicit provider is invented here. A public/custom mempool source becomes
    eligible for Sats Sentinel only because the user configured it as a tracker
    source and explicitly enabled public Sentinel queries through Tor.
    """
    settings = effective_settings(entry)
    result: list[dict[str, Any]] = []
    for raw in settings.get(CONF_SOURCES, []):
        if not isinstance(raw, dict) or raw.get(CONF_SOURCE_TYPE) != SOURCE_MEMPOOL:
            continue
        if _is_own_mempool_source(raw):
            continue
        base = _canonical_mempool_base_url(raw.get(CONF_BASE_URL))
        if not base or is_private_or_local_url(base):
            # Never reinterpret a legacy local target as a public Tor source.
            continue
        source = dict(raw)
        source[CONF_BASE_URL] = base
        source[CONF_MEMPOOL_OWN_INSTANCE] = False
        source[CONF_MEMPOOL_ROUTE] = MEMPOOL_ROUTE_TOR
        result.append(source)
    return result


def _mempool_sources(entry: ConfigEntry, allow_public_tor: bool) -> list[dict[str, Any]]:
    """Return exactly one permitted Sats Sentinel data source.

    Privacy rule:
    * an explicitly configured own/custom mempool instance is exclusive;
    * an own local/private node is contacted directly;
    * an own/custom ``.onion`` node is contacted through Tor and remains exclusive;
    * only when no own/custom node exists may an explicitly configured non-own
      mempool source be used, and only when public Sentinel queries are enabled;
    * no implicit mempool.space/provider fallback is created.
    """
    settings = effective_settings(entry)
    for raw in settings.get(CONF_SOURCES, []):
        if not _is_own_mempool_source(raw):
            continue
        base = _canonical_mempool_base_url(raw.get(CONF_BASE_URL))
        if base:
            source = dict(raw)
            source[CONF_BASE_URL] = base
            source[CONF_MEMPOOL_OWN_INSTANCE] = True
            # Preserve fail-closed routing for every own/custom form: local IP/name
            # direct, onion/non-local custom node through Tor.
            source[CONF_MEMPOOL_ROUTE] = automatic_mempool_route(
                base_url=base, own_instance=True
            )
            return [source]

    if allow_public_tor:
        public_sources = _configured_public_mempool_sources(entry)
        if public_sources:
            # Privacy-first: use only the first explicitly configured public/custom
            # source. Do not leak watched addresses to a cascade of providers.
            return [public_sources[0]]
    return []



def _host_target_url(host: str, port: int) -> str:
    value = str(host or "").strip().strip("[]")
    if not value:
        return ""
    wrapped = f"[{value}]" if ":" in value else value
    return f"http://{wrapped}:{int(port)}"


def _electrum_source_from_config(config: dict[str, Any], *, force_kind: str | None = None) -> dict[str, Any] | None:
    host = str(config.get("electrum_host") or "").strip().strip("[]")
    if not host:
        return None
    kind = str(force_kind or config.get("electrum_kind") or "fulcrum").lower()
    if kind not in _ALLOWED_ELECTRUM_KINDS:
        kind = "fulcrum"
    port = max(1, min(65535, int(config.get("electrum_port") or 50001)))
    target_url = _host_target_url(host, port)
    route = "direct" if is_private_or_local_url(target_url) and not host.lower().rstrip(".").endswith(".onion") else "tor"
    return {
        "watch_source_type": "electrum",
        "server_kind": kind,
        "host": host,
        "port": port,
        "tls": bool(config.get("electrum_tls", False)),
        "verify_ssl": bool(config.get("electrum_verify_ssl", True)),
        "pinned_cert_sha256": str(config.get("electrum_pinned_cert_sha256") or ""),
        "route": route,
        "label": "Fulcrum" if kind == "fulcrum" else "electrs",
    }


def _own_mempool_source(entry: ConfigEntry) -> dict[str, Any] | None:
    sources = _mempool_sources(entry, False)
    return dict(sources[0]) if sources else None


def _public_mempool_source(entry: ConfigEntry) -> dict[str, Any] | None:
    sources = _configured_public_mempool_sources(entry)
    return dict(sources[0]) if sources else None


def _select_watch_source(entry: ConfigEntry, config: dict[str, Any]) -> dict[str, Any] | None:
    """Select one source by configuration only; never by runtime health.

    This is the core fail-closed rule. An explicit source never cascades to a
    second provider after a connection or protocol failure. In automatic mode,
    configuration presence decides the source before any network I/O: configured
    Electrum first, then an own mempool instance, then (only with explicit Tor
    opt-in and no own source) the configured public mempool source.
    """
    mode = str(config.get("query_source") or "auto").lower()
    own = _own_mempool_source(entry)
    public = _public_mempool_source(entry)
    if mode in _ALLOWED_ELECTRUM_KINDS:
        return _electrum_source_from_config(config, force_kind=mode)
    if mode == "mempool_own":
        if not own:
            return None
        own["watch_source_type"] = "mempool"
        own["label"] = "Eigene Mempool-Instanz"
        return own
    if mode == "mempool_public":
        if not bool(config.get("allow_public_tor")) or not public:
            return None
        public["watch_source_type"] = "mempool"
        public["label"] = "Öffentliche Mempool-Instanz · Tor"
        return public

    electrum = _electrum_source_from_config(config)
    if electrum:
        return electrum
    if own:
        own["watch_source_type"] = "mempool"
        own["label"] = "Eigene Mempool-Instanz"
        return own
    if bool(config.get("allow_public_tor")) and public:
        public["watch_source_type"] = "mempool"
        public["label"] = "Öffentliche Mempool-Instanz · Tor"
        return public
    return None


def _explorer_mempool_source(entry: ConfigEntry, allow_public_tor: bool) -> dict[str, Any] | None:
    """Return the independent Mempool web explorer used only for UI links."""
    own = _own_mempool_source(entry)
    if own:
        return own
    if allow_public_tor:
        return _public_mempool_source(entry)
    return None


def _address_scriptpubkey(address: str) -> bytes:
    value = validate_mainnet_address(address)
    if value.lower().startswith("bc1"):
        _hrp, data, _encoding = _bech32_decode(value)
        version = int(data[0])
        program = bytes(_convertbits(data[1:], 5, 8, False))
        opcode = 0 if version == 0 else 0x50 + version
        return bytes([opcode, len(program)]) + program
    decoded = _b58check_decode(value)
    version, payload = decoded[0], decoded[1:]
    if version == 0x00:
        return b"\x76\xa9\x14" + payload + b"\x88\xac"
    if version == 0x05:
        return b"\xa9\x14" + payload + b"\x87"
    raise ValueError("Unsupported mainnet address")


def _electrum_scripthash(address: str) -> str:
    return _sha256(_address_scriptpubkey(address))[::-1].hex()


def _scriptpubkey_address(script: bytes) -> str:
    if len(script) == 25 and script[:3] == b"\x76\xa9\x14" and script[-2:] == b"\x88\xac":
        return _b58check(b"\x00", script[3:23])
    if len(script) == 23 and script[:2] == b"\xa9\x14" and script[-1:] == b"\x87":
        return _b58check(b"\x05", script[2:22])
    if len(script) >= 4:
        op = script[0]
        if op == 0 or 0x51 <= op <= 0x60:
            version = 0 if op == 0 else op - 0x50
            length = script[1]
            if length == len(script) - 2 and 2 <= length <= 40:
                return _bech32_address(script[2:], version)
    return ""


def _read_varint(raw: bytes, offset: int) -> tuple[int, int]:
    if offset >= len(raw):
        raise ValueError("Truncated transaction varint")
    first = raw[offset]
    if first < 0xFD:
        return first, offset + 1
    size = 2 if first == 0xFD else 4 if first == 0xFE else 8
    end = offset + 1 + size
    if end > len(raw):
        raise ValueError("Truncated transaction varint")
    return int.from_bytes(raw[offset + 1:end], "little"), end


def _parse_raw_transaction(raw_hex: str) -> dict[str, Any]:
    try:
        raw = bytes.fromhex(str(raw_hex or ""))
    except ValueError as err:
        raise ValueError("Electrum returned invalid transaction hex") from err
    if len(raw) < 10:
        raise ValueError("Electrum returned a truncated transaction")
    offset = 4
    segwit = len(raw) > 6 and raw[offset] == 0 and raw[offset + 1] != 0
    if segwit:
        offset += 2
    input_count, offset = _read_varint(raw, offset)
    if input_count > 100_000:
        raise ValueError("Transaction input count exceeds Sentinel safety limit")
    inputs: list[dict[str, Any]] = []
    for _ in range(input_count):
        if offset + 36 > len(raw):
            raise ValueError("Truncated transaction input")
        prev_txid = raw[offset:offset + 32][::-1].hex(); offset += 32
        prev_vout = int.from_bytes(raw[offset:offset + 4], "little"); offset += 4
        script_len, offset = _read_varint(raw, offset)
        offset += script_len
        if offset + 4 > len(raw):
            raise ValueError("Truncated transaction input sequence")
        sequence = int.from_bytes(raw[offset:offset + 4], "little"); offset += 4
        inputs.append({"txid": prev_txid, "vout": prev_vout, "sequence": sequence})
    output_count, offset = _read_varint(raw, offset)
    if output_count > 100_000:
        raise ValueError("Transaction output count exceeds Sentinel safety limit")
    outputs: list[dict[str, Any]] = []
    for _ in range(output_count):
        if offset + 8 > len(raw):
            raise ValueError("Truncated transaction output")
        value_sats = int.from_bytes(raw[offset:offset + 8], "little"); offset += 8
        script_len, offset = _read_varint(raw, offset)
        end = offset + script_len
        if end > len(raw):
            raise ValueError("Truncated transaction output script")
        script = raw[offset:end]; offset = end
        outputs.append({"value_sats": value_sats, "script": script, "address": _scriptpubkey_address(script)})
    if segwit:
        for _ in range(input_count):
            item_count, offset = _read_varint(raw, offset)
            for _ in range(item_count):
                item_len, offset = _read_varint(raw, offset)
                offset += item_len
                if offset > len(raw):
                    raise ValueError("Truncated transaction witness")
    if offset + 4 > len(raw):
        raise ValueError("Truncated transaction locktime")
    return {"inputs": inputs, "outputs": outputs, "rbf": any(int(item["sequence"]) < 0xFFFFFFFE for item in inputs)}


class _ElectrumRPCClient:
    def __init__(self, manager: "WalletWatchManager", source: dict[str, Any]) -> None:
        self.manager = manager
        self.source = source
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self._next_id = 1
        self.server_version: Any = None

    async def __aenter__(self) -> "_ElectrumRPCClient":
        host = str(self.source.get("host") or "")
        port = int(self.source.get("port") or 50001)
        settings = effective_settings(self.manager.entry)
        if str(self.source.get("route")) == "tor":
            proxy = await async_tor_socks_connection_info(self.manager.hass, settings)
            self.reader, self.writer = await asyncio.open_connection(
                str(proxy["host"]), int(proxy["port"]), limit=ELECTRUM_MAX_LINE_BYTES
            )
            await self._socks_connect(host, port, str(proxy.get("username") or ""), str(proxy.get("password") or ""))
        else:
            target_url = _host_target_url(host, port)
            if not is_private_or_local_url(target_url):
                raise ValueError("Direct Electrum connections are allowed only to local/private targets")
            self.reader, self.writer = await asyncio.open_connection(host, port, limit=ELECTRUM_MAX_LINE_BYTES)
        if bool(self.source.get("tls")):
            pinned = str(self.source.get("pinned_cert_sha256") or "").lower()
            verify_ssl = bool(self.source.get("verify_ssl", True))
            # Home Assistant pre-warms and caches these contexts outside the
            # event loop. ssl.create_default_context() performs blocking disk I/O
            # (loading CA certificates) and must never run in Sentinel's async poll.
            # Certificate pinning still performs exact SHA-256 peer verification
            # after the TLS handshake, so self-signed Fulcrum certificates remain
            # supported without weakening authenticity.
            context = (
                client_context_no_verify()
                if pinned or not verify_ssl
                else client_context()
            )
            assert self.writer is not None
            await self.writer.start_tls(context, server_hostname=host)
            if pinned:
                ssl_object = self.writer.get_extra_info("ssl_object")
                peer_der = ssl_object.getpeercert(binary_form=True) if ssl_object is not None else None
                if not peer_der:
                    raise ssl.SSLCertVerificationError("Fulcrum/Electrum did not present a TLS certificate")
                actual = hashlib.sha256(peer_der).hexdigest().lower()
                if not hmac.compare_digest(actual, pinned):
                    raise ssl.SSLCertVerificationError(
                        f"Fulcrum/Electrum certificate pin mismatch (expected {pinned[:16]}…, got {actual[:16]}…)"
                    )
        self.server_version = await self.call("server.version", ["Bitcoin Stack Tracker", "1.4"])
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.writer is not None:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass
        self.reader = None
        self.writer = None

    async def _socks_connect(self, target_host: str, target_port: int, username: str, password: str) -> None:
        assert self.reader is not None and self.writer is not None
        methods = b"\x00\x02" if username else b"\x00"
        self.writer.write(bytes([5, len(methods)]) + methods); await self.writer.drain()
        reply = await self.reader.readexactly(2)
        if reply[0] != 5 or reply[1] == 0xFF:
            raise ConnectionError("Tor SOCKS proxy rejected authentication methods")
        if reply[1] == 2:
            user = username.encode("utf-8")[:255]; pwd = password.encode("utf-8")[:255]
            self.writer.write(bytes([1, len(user)]) + user + bytes([len(pwd)]) + pwd); await self.writer.drain()
            auth = await self.reader.readexactly(2)
            if auth != b"\x01\x00":
                raise ConnectionError("Tor SOCKS authentication failed")
        host_bytes = target_host.encode("idna")
        if len(host_bytes) > 255:
            raise ValueError("Electrum hostname is too long")
        self.writer.write(b"\x05\x01\x00\x03" + bytes([len(host_bytes)]) + host_bytes + int(target_port).to_bytes(2, "big")); await self.writer.drain()
        head = await self.reader.readexactly(4)
        if head[0] != 5 or head[1] != 0:
            raise ConnectionError(f"Tor SOCKS CONNECT failed with code {head[1] if len(head) > 1 else '?'}")
        atyp = head[3]
        if atyp == 1:
            await self.reader.readexactly(4)
        elif atyp == 4:
            await self.reader.readexactly(16)
        elif atyp == 3:
            size = (await self.reader.readexactly(1))[0]
            await self.reader.readexactly(size)
        else:
            raise ConnectionError("Tor SOCKS returned an invalid address type")
        await self.reader.readexactly(2)

    async def call(self, method: str, params: list[Any]) -> Any:
        values = await self.call_many([(method, params)])
        return values[0]

    async def call_many(self, calls: list[tuple[str, list[Any]]]) -> list[Any]:
        if not calls:
            return []
        assert self.reader is not None and self.writer is not None
        ids: list[int] = []
        for method, params in calls:
            request_id = self._next_id; self._next_id += 1; ids.append(request_id)
            payload = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}, separators=(",", ":"))
            self.writer.write(payload.encode("utf-8") + b"\n")
        await self.writer.drain()
        wanted = set(ids); results: dict[int, Any] = {}
        async with asyncio.timeout(ELECTRUM_REQUEST_TIMEOUT_SECONDS):
            while wanted:
                line = await self.reader.readline()
                if not line:
                    raise ConnectionError("Electrum connection closed")
                if len(line) > ELECTRUM_MAX_LINE_BYTES:
                    raise ValueError("Electrum response exceeds Sentinel safety limit")
                message = json.loads(line.decode("utf-8"))
                request_id = message.get("id") if isinstance(message, dict) else None
                if request_id not in wanted:
                    continue
                if message.get("error"):
                    raise RuntimeError(f"Electrum RPC {message['error']}")
                results[int(request_id)] = message.get("result")
                wanted.remove(request_id)
        return [results[request_id] for request_id in ids]


def _electrum_event_from_parsed(
    txid: str, tx: dict[str, Any], prev_transactions: dict[str, dict[str, Any]], address: str, height: int
) -> dict[str, Any]:
    watched_script = _address_scriptpubkey(address)
    received = 0
    spent = 0
    input_candidates: list[dict[str, Any]] = []
    output_candidates: list[dict[str, Any]] = []
    for output in tx.get("outputs", []):
        value = int(output.get("value_sats") or 0)
        if output.get("script") == watched_script:
            received += value
        candidate = str(output.get("address") or "")
        if candidate:
            output_candidates.append({"address": candidate, "value_sats": value})
    for txin in tx.get("inputs", []):
        prev = prev_transactions.get(str(txin.get("txid") or ""))
        vout = int(txin.get("vout") or 0)
        if not prev or vout < 0 or vout >= len(prev.get("outputs", [])):
            continue
        prevout = prev["outputs"][vout]
        value = int(prevout.get("value_sats") or 0)
        if prevout.get("script") == watched_script:
            spent += value
        candidate = str(prevout.get("address") or "")
        if candidate:
            input_candidates.append({"address": candidate, "value_sats": value})
    return {
        "txid": txid,
        "spent_sats": spent,
        "received_sats": received,
        "net_sats": received - spent,
        "direction": "outgoing" if spent > 0 else "incoming",
        "confirmed": int(height or 0) > 0,
        "rbf": bool(tx.get("rbf")),
        "block_height": int(height) if int(height or 0) > 0 else None,
        "block_time": None,
        "input_candidates": input_candidates,
        "output_candidates": output_candidates,
    }


def _summary_signature(payload: dict[str, Any]) -> str:
    chain = payload.get("chain_stats") if isinstance(payload.get("chain_stats"), dict) else {}
    mem = payload.get("mempool_stats") if isinstance(payload.get("mempool_stats"), dict) else {}
    parts = (
        int(chain.get("funded_txo_count") or 0), int(chain.get("funded_txo_sum") or 0),
        int(chain.get("spent_txo_count") or 0), int(chain.get("spent_txo_sum") or 0), int(chain.get("tx_count") or 0),
        int(mem.get("funded_txo_count") or 0), int(mem.get("funded_txo_sum") or 0),
        int(mem.get("spent_txo_count") or 0), int(mem.get("spent_txo_sum") or 0), int(mem.get("tx_count") or 0),
    )
    return ":".join(str(x) for x in parts)


def _address_summary_used(payload: dict[str, Any]) -> bool:
    """An HD address is used once it has any confirmed or mempool transaction history."""
    chain = payload.get("chain_stats") if isinstance(payload.get("chain_stats"), dict) else {}
    mem = payload.get("mempool_stats") if isinstance(payload.get("mempool_stats"), dict) else {}
    return any(
        int(stats.get(key) or 0) > 0
        for stats in (chain, mem)
        for key in ("tx_count", "funded_txo_count", "spent_txo_count")
    )


def _balance_sats(payload: dict[str, Any]) -> int:
    chain = payload.get("chain_stats") if isinstance(payload.get("chain_stats"), dict) else {}
    mem = payload.get("mempool_stats") if isinstance(payload.get("mempool_stats"), dict) else {}
    return (
        int(chain.get("funded_txo_sum") or 0) - int(chain.get("spent_txo_sum") or 0)
        + int(mem.get("funded_txo_sum") or 0) - int(mem.get("spent_txo_sum") or 0)
    )


def _utxo_count_from_summary(payload: dict[str, Any]) -> int:
    """Return the current output count without calling /address/:address/utxo.

    Esplora-style address summaries already expose funded/spent output counts
    for both chain and mempool state.  Using the net count avoids storing or
    fetching the user's concrete UTXO set and also works with self-hosted
    mempool deployments that intentionally do not expose the /utxo endpoint.
    """
    chain = payload.get("chain_stats") if isinstance(payload.get("chain_stats"), dict) else {}
    mem = payload.get("mempool_stats") if isinstance(payload.get("mempool_stats"), dict) else {}
    count = (
        int(chain.get("funded_txo_count") or 0) - int(chain.get("spent_txo_count") or 0)
        + int(mem.get("funded_txo_count") or 0) - int(mem.get("spent_txo_count") or 0)
    )
    return max(0, count)


def _tx_activity(tx: dict[str, Any], address: str) -> dict[str, Any]:
    received = sum(
        int(vout.get("value") or 0)
        for vout in tx.get("vout", []) if isinstance(vout, dict) and str(vout.get("scriptpubkey_address") or "") == address
    )
    spent = 0
    input_candidates: list[dict[str, Any]] = []
    for vin in tx.get("vin", []):
        if not isinstance(vin, dict):
            continue
        prevout = vin.get("prevout") if isinstance(vin.get("prevout"), dict) else {}
        prev_address = str(prevout.get("scriptpubkey_address") or "")
        prev_value = int(prevout.get("value") or 0)
        if prev_address:
            input_candidates.append({"address": prev_address, "value_sats": prev_value})
        if prev_address == address:
            spent += prev_value
    output_candidates = []
    for vout in tx.get("vout", []):
        if not isinstance(vout, dict):
            continue
        out_address = str(vout.get("scriptpubkey_address") or "")
        if out_address:
            output_candidates.append({"address": out_address, "value_sats": int(vout.get("value") or 0)})
    sequences = [int(v.get("sequence") or 0xFFFFFFFF) for v in tx.get("vin", []) if isinstance(v, dict)]
    status = tx.get("status") if isinstance(tx.get("status"), dict) else {}
    direction = "outgoing" if spent > 0 else "incoming"
    return {
        "txid": str(tx.get("txid") or ""),
        "direction": direction,
        "spent_sats": spent,
        "received_sats": received,
        "net_sats": received - spent,
        "confirmed": bool(status.get("confirmed")),
        "block_height": status.get("block_height"),
        "block_time": status.get("block_time"),
        "rbf": any(seq < 0xFFFFFFFE for seq in sequences),
        "input_candidates": input_candidates,
        "output_candidates": output_candidates,
    }


def _aggregate_counterparties(candidates: list[dict[str, Any]], watched_addresses: set[str]) -> list[dict[str, Any]]:
    combined: dict[str, int] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        address = str(candidate.get("address") or "")
        if not address or address in watched_addresses:
            continue
        combined[address] = combined.get(address, 0) + int(candidate.get("value_sats") or 0)
    return [
        {"address": address, "value_sats": value}
        for address, value in sorted(combined.items(), key=lambda item: item[1], reverse=True)[:12]
    ]


def _monitor_event_from_esplora(tx: dict[str, Any], watched_addresses: set[str]) -> dict[str, Any]:
    """Build one transaction-level view for all addresses of a monitor.

    This is intentionally separate from the alert baseline. Historical overview
    requests may inspect old transactions, but they never append to the Sentinel
    journal or send notifications.
    """
    received = 0
    spent = 0
    total_inputs = 0
    total_outputs = 0
    input_candidates: list[dict[str, Any]] = []
    output_candidates: list[dict[str, Any]] = []
    participating: list[str] = []
    for vin in tx.get("vin", []):
        if not isinstance(vin, dict):
            continue
        prevout = vin.get("prevout") if isinstance(vin.get("prevout"), dict) else {}
        address = str(prevout.get("scriptpubkey_address") or "")
        value = int(prevout.get("value") or 0)
        total_inputs += value
        if address:
            input_candidates.append({"address": address, "value_sats": value})
        if address in watched_addresses:
            spent += value
            if address not in participating:
                participating.append(address)
    for vout in tx.get("vout", []):
        if not isinstance(vout, dict):
            continue
        address = str(vout.get("scriptpubkey_address") or "")
        value = int(vout.get("value") or 0)
        total_outputs += value
        if address:
            output_candidates.append({"address": address, "value_sats": value})
        if address in watched_addresses:
            received += value
            if address not in participating:
                participating.append(address)
    direction = "outgoing" if spent > 0 else "incoming"
    counterparties = _aggregate_counterparties(output_candidates if direction == "outgoing" else input_candidates, watched_addresses)
    external_amount = sum(int(item.get("value_sats") or 0) for item in counterparties)
    amount_sats = external_amount if direction == "outgoing" else received
    if direction == "outgoing" and amount_sats <= 0:
        amount_sats = max(0, spent - received)
    status = tx.get("status") if isinstance(tx.get("status"), dict) else {}
    sequences = [int(v.get("sequence") or 0xFFFFFFFF) for v in tx.get("vin", []) if isinstance(v, dict)]
    fee = max(0, total_inputs - total_outputs) if total_inputs >= total_outputs and total_inputs > 0 else None
    return {
        "txid": str(tx.get("txid") or "").lower(),
        "direction": direction,
        "amount_sats": amount_sats,
        "spent_sats": spent,
        "received_sats": received,
        "net_sats": received - spent,
        "tx_total_input_sats": total_inputs,
        "tx_total_output_sats": total_outputs,
        "fee_sats": fee,
        "confirmed": bool(status.get("confirmed")),
        "block_height": status.get("block_height"),
        "block_time": status.get("block_time"),
        "rbf": any(seq < 0xFFFFFFFE for seq in sequences),
        "counterparties": counterparties,
        "watched_addresses": participating[:12],
    }


def _monitor_event_from_parsed(
    txid: str,
    tx: dict[str, Any],
    prev_transactions: dict[str, dict[str, Any]],
    watched_addresses: set[str],
    height: int,
    block_time: int | None = None,
) -> dict[str, Any]:
    watched_scripts = {_address_scriptpubkey(address): address for address in watched_addresses}
    received = 0
    spent = 0
    total_inputs = 0
    total_outputs = 0
    missing_prevouts = 0
    input_candidates: list[dict[str, Any]] = []
    output_candidates: list[dict[str, Any]] = []
    participating: list[str] = []
    for output in tx.get("outputs", []):
        value = int(output.get("value_sats") or 0)
        total_outputs += value
        script = output.get("script")
        watched_address = watched_scripts.get(script)
        candidate = str(output.get("address") or "")
        if candidate:
            output_candidates.append({"address": candidate, "value_sats": value})
        if watched_address:
            received += value
            if watched_address not in participating:
                participating.append(watched_address)
    for txin in tx.get("inputs", []):
        prev = prev_transactions.get(str(txin.get("txid") or ""))
        vout = int(txin.get("vout") or 0)
        if not prev or vout < 0 or vout >= len(prev.get("outputs", [])):
            missing_prevouts += 1
            continue
        prevout = prev["outputs"][vout]
        value = int(prevout.get("value_sats") or 0)
        total_inputs += value
        script = prevout.get("script")
        watched_address = watched_scripts.get(script)
        candidate = str(prevout.get("address") or "")
        if candidate:
            input_candidates.append({"address": candidate, "value_sats": value})
        if watched_address:
            spent += value
            if watched_address not in participating:
                participating.append(watched_address)
    direction = "outgoing" if spent > 0 else "incoming"
    counterparties = _aggregate_counterparties(output_candidates if direction == "outgoing" else input_candidates, watched_addresses)
    external_amount = sum(int(item.get("value_sats") or 0) for item in counterparties)
    amount_sats = external_amount if direction == "outgoing" else received
    if direction == "outgoing" and amount_sats <= 0:
        amount_sats = max(0, spent - received)
    inputs_complete = missing_prevouts == 0
    fee = max(0, total_inputs - total_outputs) if inputs_complete and total_inputs >= total_outputs and total_inputs > 0 else None
    return {
        "txid": txid.lower(),
        "direction": direction,
        "amount_sats": amount_sats,
        "spent_sats": spent,
        "received_sats": received,
        "net_sats": received - spent,
        "tx_total_input_sats": total_inputs if inputs_complete else None,
        "tx_total_output_sats": total_outputs,
        "fee_sats": fee,
        "confirmed": int(height or 0) > 0,
        "block_height": int(height) if int(height or 0) > 0 else None,
        "block_time": int(block_time) if block_time else None,
        "rbf": bool(tx.get("rbf")),
        "counterparties": counterparties,
        "watched_addresses": participating[:12],
        "inputs_complete": inputs_complete,
    }


def _electrum_header_time(header_hex: Any) -> int | None:
    try:
        raw = bytes.fromhex(str(header_hex or ""))
    except ValueError:
        return None
    if len(raw) < 72:
        return None
    return int.from_bytes(raw[68:72], "little")


class WalletWatchManager:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, ledger_store) -> None:
        self.hass = hass
        self.entry = entry
        self.ledger_store = ledger_store
        self.runtime_store = WalletWatchRuntimeStore(hass, entry.entry_id, ledger_store.async_device_binding_secret)
        self._cancel = None
        self._lock = asyncio.Lock()
        self._refresh_task: asyncio.Task | None = None
        self._last_poll_monotonic = 0.0
        self._last_runtime_persist_monotonic = 0.0
        # Some self-hosted mempool deployments expose Esplora-compatible
        # address routes under /api/, others proxy/reimplement the same routes
        # under /api/v1/.  Cache the working prefix per exact same-node base.
        # This never changes host, port, routing policy or provider.
        self._address_api_prefix_by_base: dict[str, str] = {}

    async def async_start(self) -> None:
        # Defensive against an accidental double-start during entry reloads.
        # Leaving the old interval callback alive would create duplicate polls.
        if self._cancel:
            self._cancel()
            self._cancel = None
        await self.runtime_store.async_load()
        # Do not hit Fulcrum while Home Assistant itself is still starting. The
        # normal timer performs the first poll after the configured interval; a
        # newly saved/recovered wallet can still schedule its own background scan.
        self._last_poll_monotonic = asyncio.get_running_loop().time()
        self._cancel = async_track_time_interval(self.hass, self._timer, timedelta(seconds=30))

    async def async_stop(self) -> None:
        if self._cancel:
            self._cancel()
            self._cancel = None
        task = self._refresh_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._refresh_task = None

    def cancel_background_refresh(self) -> None:
        """Cancel stale discovery before a newer encrypted config is persisted."""
        task = self._refresh_task
        if task is not None and not task.done():
            task.cancel()
        self._refresh_task = None

    async def _async_save_runtime_if_due(self, *, force: bool = False) -> bool:
        """Use coalesced persistence while remaining compatible with test stores."""
        saver = getattr(self.runtime_store, "async_save_if_due", None)
        if callable(saver):
            return bool(await saver(force=force))
        await self.runtime_store.async_save()
        return True

    def _runtime_management_config(self) -> dict[str, Any]:
        """Reconstruct a full watch-only config from the encrypted runtime vault.

        This is used only for owner-authorized Sentinel management while the main
        portfolio vault is locked.  The runtime vault may contain public watch-only
        keys (xpub/ypub/zpub/descriptors/addresses), but never seeds/private keys.
        """
        data = self.runtime_store.data
        monitors: list[dict[str, Any]] = []
        for item in data.get("monitor_catalog") or []:
            if not isinstance(item, dict):
                continue
            watch_value = str(item.get("watch_value") or "")
            if not watch_value:
                # Caches created before rc8 did not keep raw watch-only material.
                # One successful vault unlock repopulates it from the authoritative
                # password vault before locked editing becomes available. Never
                # silently drop such a wallet from a locked edit operation.
                raise ValueError("Locked Sats Sentinel editing needs one successful vault unlock after this update")
            monitors.append({
                "id": str(item.get("id") or ""),
                "label": str(item.get("label") or ""),
                "kind": str(item.get("kind") or "address"),
                "value": watch_value,
                "enabled": bool(item.get("enabled", True)),
                "receive_count": int(item.get("receive_count") or 0),
                "change_count": int(item.get("change_count") or 0),
                "history_limit": int(item.get("history_limit") if item.get("history_limit") is not None else 10),
                "created_at": str(item.get("created_at") or ""),
                "category": str(item.get("category") or "other"),
                "note": str(item.get("note") or ""),
                "min_notify_sats": int(item.get("min_notify_sats") or 0),
                "notification_detail": str(item.get("notification_detail") or data.get("notification_detail") or "discreet"),
                "notify_incoming": bool(item.get("notify_incoming", True)),
                "notify_outgoing": bool(item.get("notify_outgoing", True)),
                "notify_ha_event": bool(item.get("notify_ha_event", True)),
                "notify_persistent": bool(item.get("notify_persistent", True)),
                "notify_services": bool(item.get("notify_services", True)),
                "notify_external": bool(item.get("notify_external", True)),
            })
        return normalize_watch_config({
            "enabled": bool(data.get("enabled")),
            "poll_interval_seconds": int(data.get("poll_interval_seconds") or DEFAULT_POLL_SECONDS),
            "query_source": str(data.get("query_source") or "auto"),
            "electrum_kind": str(data.get("electrum_kind") or "fulcrum"),
            "electrum_host": str(data.get("electrum_host") or ""),
            "electrum_port": int(data.get("electrum_port") or 50001),
            "electrum_tls": bool(data.get("electrum_tls")),
            "electrum_verify_ssl": bool(data.get("electrum_verify_ssl", True)),
            "electrum_pinned_cert_sha256": str(data.get("electrum_pinned_cert_sha256") or ""),
            "allow_public_tor": bool(data.get("allow_public_tor")),
            "persistent_notification": bool(data.get("persistent_notification", True)),
            "notification_detail": str(data.get("notification_detail") or "discreet"),
            "notification_services": list(data.get("notification_services") or []),
            "notification_targets": deepcopy(data.get("notification_targets") or []),
            "monitors": monitors,
        })

    def public_locked_management_config(self) -> dict[str, Any]:
        """Return owner-safe editable monitor metadata without raw watch keys."""
        data = self.runtime_store.data
        rows: list[dict[str, Any]] = []
        for item in data.get("monitor_catalog") or []:
            if not isinstance(item, dict):
                continue
            raw = str(item.get("watch_value") or "")
            masked = ""
            if raw:
                masked = raw if len(raw) <= 18 else f"{raw[:8]}…{raw[-6:]}"
            rows.append({
                key: deepcopy(value)
                for key, value in item.items()
                if key != "watch_value"
            } | {
                "watch_value_masked": masked,
                "watch_value_available": bool(raw),
            })
        return {
            "enabled": bool(data.get("enabled")),
            "poll_interval_seconds": int(data.get("poll_interval_seconds") or DEFAULT_POLL_SECONDS),
            "query_source": str(data.get("query_source") or "auto"),
            "electrum_kind": str(data.get("electrum_kind") or "fulcrum"),
            "electrum_host": str(data.get("electrum_host") or ""),
            "electrum_port": int(data.get("electrum_port") or 50001),
            "electrum_tls": bool(data.get("electrum_tls")),
            "electrum_verify_ssl": bool(data.get("electrum_verify_ssl", True)),
            # The PEM itself intentionally remains in the password vault. The
            # owner-safe locked view may still show that an exact certificate
            # pin is configured and which SHA-256 fingerprint is active.
            "electrum_pinned_cert_sha256": str(data.get("electrum_pinned_cert_sha256") or ""),
            "allow_public_tor": bool(data.get("allow_public_tor")),
            "persistent_notification": bool(data.get("persistent_notification", True)),
            "notification_detail": str(data.get("notification_detail") or "discreet"),
            "notification_services": list(data.get("notification_services") or []),
            "monitors": rows,
            "pending_vault_sync": bool(data.get("pending_vault_sync")),
        }

    async def async_upsert_runtime_monitor(self, monitor: dict[str, Any]) -> dict[str, Any]:
        """Edit a watch-only target while the main portfolio vault is locked."""
        if not isinstance(monitor, dict):
            raise ValueError("Sats Sentinel watch entry is missing")
        monitor_id = str(monitor.get("id") or "").strip()
        if not monitor_id:
            raise ValueError("Sats Sentinel monitor ID is missing")
        base = self._runtime_management_config()
        rows = list(base.get("monitors") or [])
        existing = next((row for row in rows if str(row.get("id") or "") == monitor_id), None)
        if existing is None:
            raise ValueError("Locked-vault editing requires an existing runtime watch target")
        incoming = deepcopy(existing)
        for key in (
            "label", "category", "note", "kind", "receive_count", "change_count",
            "history_limit", "min_notify_sats", "notification_detail", "notify_incoming",
            "notify_outgoing", "notify_ha_event", "notify_persistent", "notify_services",
            "notify_external", "enabled",
        ):
            if key in monitor:
                incoming[key] = deepcopy(monitor[key])
        replacement_value = str(monitor.get("value") or "").strip()
        if replacement_value:
            incoming["value"] = replacement_value
        for index, row in enumerate(rows):
            if str(row.get("id") or "") == monitor_id:
                rows[index] = incoming
                break
        base["monitors"] = rows
        normalized = normalize_watch_config(base)
        self.cancel_background_refresh()
        await self.runtime_store.async_replace_from_full_config(normalized)
        self.runtime_store.data["pending_vault_sync"] = True
        await self.runtime_store.async_save()
        if normalized.get("enabled"):
            self.schedule_background_refresh(normalized, monitor_ids={monitor_id}, poll=True)
        return {
            "saved": True,
            "monitor_id": monitor_id,
            "config": self.public_locked_management_config(),
            "status": self.public_status(include_addresses=False),
        }

    async def async_remove_runtime_monitor(self, monitor_id: str) -> dict[str, Any]:
        """Delete one watch-only target from the runtime vault while locked."""
        monitor_id = str(monitor_id or "").strip()
        if not monitor_id:
            raise ValueError("Sats Sentinel monitor ID is missing")
        base = self._runtime_management_config()
        before = list(base.get("monitors") or [])
        after = [row for row in before if str(row.get("id") or "") != monitor_id]
        if len(after) == len(before):
            raise ValueError("Sats Sentinel watch entry was not found")
        base["monitors"] = after
        self.cancel_background_refresh()
        purged = await self.runtime_store.async_replace_from_full_config(normalize_watch_config(base))
        self.runtime_store.data["pending_vault_sync"] = True
        await self.runtime_store.async_save()
        return {
            "removed": True,
            "monitor_id": monitor_id,
            "config": self.public_locked_management_config(),
            "status": self.public_status(include_addresses=False) | {"purged_activity_count": purged},
        }

    def schedule_background_refresh(
        self,
        config: dict[str, Any],
        *,
        monitor_ids: set[str] | None = None,
        poll: bool = True,
    ) -> None:
        """Queue HD gap discovery without holding the panel HTTP request open.

        XPUB/descriptor discovery can require hundreds of explicit Fulcrum calls
        before the configured consecutive-unused gap is reached. Persisting the
        encrypted watch configuration is intentionally separated from that network
        work so the UI never reports Home Assistant as unavailable merely because
        a legitimate wallet has a long address history.
        """
        normalized = normalize_watch_config(config)
        targets = None if monitor_ids is None else {str(value) for value in monitor_ids}
        self.cancel_background_refresh()

        async def _runner() -> None:
            try:
                if not normalized.get("enabled"):
                    return
                source = _select_watch_source(self.entry, normalized)
                if source is None:
                    return
                # Serialize discovery against the normal poller. The network work
                # is background-only, so taking this lock can never delay saving.
                # Fulcrum can transiently time out while Core is busy. Retry the
                # whole discovery with a *fresh* Electrum connection rather than
                # leaving the wallet collapsed at the initial raw gap addresses.
                last_error: Exception | None = None
                for attempt in range(3):
                    try:
                        async with self._lock:
                            await self._discover_gap_addresses(
                                normalized, source, monitor_ids=targets
                            )
                        last_error = None
                        break
                    except (TimeoutError, asyncio.TimeoutError, ConnectionError) as err:
                        last_error = err
                        if attempt < 2:
                            await asyncio.sleep(1.0 + attempt * 2.0)
                if last_error is not None:
                    raise last_error
                self.runtime_store.data["last_warning"] = None
                self.runtime_store.data["partial_failures"] = 0
                await self.runtime_store.async_save()
                if poll:
                    await self.async_poll(force=True)
            except asyncio.CancelledError:
                raise
            except Exception as err:
                self.runtime_store.data["last_warning"] = (
                    f"Sats Sentinel background gap discovery pending: "
                    f"{type(err).__name__}: {err}"
                )[:500]
                await self.runtime_store.async_save()
            finally:
                current = asyncio.current_task()
                if self._refresh_task is current:
                    self._refresh_task = None

        self._refresh_task = self.hass.async_create_task(
            _runner(), "Bitcoin Stack Tracker Sats Sentinel gap discovery"
        )

    async def _timer(self, _now: Any = None) -> None:
        if not self.runtime_store.data.get("enabled"):
            return
        now = asyncio.get_running_loop().time()
        interval = int(self.runtime_store.data.get("poll_interval_seconds") or DEFAULT_POLL_SECONDS)
        if now - self._last_poll_monotonic >= interval:
            await self.async_poll()

    @staticmethod
    def _runtime_row_from_monitor(
        monitor: dict[str, Any], monitor_slot: int, derived: dict[str, Any], *, active: bool, used: bool | None
    ) -> dict[str, Any]:
        branch = str(derived.get("branch") or "fixed")
        gap_limit = (
            int(monitor.get("receive_count") or 0) if branch == "receive"
            else int(monitor.get("change_count") or 0) if branch == "change"
            else 0
        )
        return {
            "monitor_id": monitor["id"],
            "monitor_slot": monitor_slot,
            "address": derived["address"],
            "branch": branch,
            "index": derived.get("index"),
            "gap_limit": gap_limit,
            "active": bool(active),
            "used": used,
            "resolved_address_type": (
                str(monitor.get("_resolved_address_type") or monitor.get("address_type") or "auto")
                if str(monitor.get("kind") or "") == "xpub" else ""
            ),
            "resolved_address_type_verified": (
                bool(monitor.get("_resolved_address_type_verified"))
                if str(monitor.get("kind") or "") == "xpub" else True
            ),
            "notify_incoming": monitor["notify_incoming"],
            "notify_outgoing": monitor["notify_outgoing"],
            "category": monitor.get("category", "other"),
            "min_notify_sats": int(monitor.get("min_notify_sats") or 0),
            "notify_ha_event": bool(monitor.get("notify_ha_event", True)),
            "notify_persistent": bool(monitor.get("notify_persistent", True)),
            "notify_services": bool(monitor.get("notify_services", True)),
            "notify_external": bool(monitor.get("notify_external", True)),
            "baseline_complete": False,
            "summary_signature": None,
            "known_txids": [],
            "utxo_count": 0,
            "balance_sats": 0,
            "last_activity_at": None,
            "last_balance_refresh_unix": 0,
        }

    @staticmethod
    def _merge_runtime_row_state(row: dict[str, Any], old: dict[str, Any] | None) -> dict[str, Any]:
        if not old:
            return row
        for key in (
            "baseline_complete", "summary_signature", "known_txids", "utxo_count", "balance_sats",
            "last_activity_at", "last_balance_refresh_unix",
            "resolved_address_type", "resolved_address_type_verified",
        ):
            row[key] = deepcopy(old.get(key, row.get(key)))
        if "utxo_count" not in old and isinstance(old.get("utxos"), list):
            row["utxo_count"] = len(old.get("utxos") or [])
        return row

    @staticmethod
    def _derive_monitor_address(monitor: dict[str, Any], branch: int, index: int) -> dict[str, Any] | None:
        if monitor.get("kind") == "xpub":
            return derive_extpub_branch_address(
                str(monitor.get("value") or ""), branch, index,
                address_type=str(monitor.get("_resolved_address_type") or monitor.get("address_type") or "auto"),
            )
        if monitor.get("kind") == "descriptor":
            return derive_descriptor_branch_address(str(monitor.get("value") or ""), branch, index)
        return None

    async def _resolve_xpub_address_type(
        self, monitor: dict[str, Any], source: dict[str, Any], *, electrum_client: _ElectrumRPCClient | None
    ) -> tuple[str, bool]:
        """Resolve script type for an ambiguous plain xpub from actual wallet history.

        ypub/zpub are unambiguous. A plain xpub is not: many descriptor wallets
        serialize BIP49/BIP84/BIP86 account keys with the ordinary xpub version.
        In Auto mode we probe at least the standard 20-address bootstrap window
        on receive/change and pick the script family with real historical activity.
        This also repairs monitors created by older builds whose UI defaulted the
        configured gap to 2. Current balance is never used for this decision.
        """
        requested = str(monitor.get("address_type") or "auto").strip().lower()
        extpub = str(monitor.get("value") or "")
        root = _parse_extpub(extpub)
        if requested != "auto":
            return requested, True
        if not extpub.lower().startswith("xpub"):
            return root.script_type, True
        candidates = list(_XPUB_AUTO_CANDIDATES)
        scores = {item: 0 for item in candidates}
        # Probe one script family at a time instead of bursting all four
        # candidates at once. With the 20-address bootstrap this bounds each
        # Electrum batch to 40 calls (receive + change), then yields back to HA.
        for candidate_index, script_type in enumerate(candidates):
            addresses: list[str] = []
            for branch, gap_key in ((0, "receive_count"), (1, "change_count")):
                configured = max(0, int(monitor.get(gap_key) or 0))
                if configured <= 0:
                    continue
                count = min(
                    MAX_DERIVED_PER_BRANCH,
                    max(configured, HD_DISCOVERY_BOOTSTRAP_ADDRESSES),
                )
                for index in range(count):
                    row = derive_extpub_branch_address(
                        extpub, branch, index, address_type=script_type
                    )
                    addresses.append(str(row["address"]))

            if electrum_client is not None:
                calls = [
                    ("blockchain.scripthash.subscribe", [_electrum_scripthash(address)])
                    for address in addresses
                ]
                results = await self._electrum_calls_chunked(
                    electrum_client, calls, chunk_size=ELECTRUM_STATUS_BATCH_SIZE
                )
                for status in results:
                    if status not in {None, ""}:
                        scores[script_type] += 1
            else:
                # HTTP/Esplora fallback is intentionally conservative and only
                # used when no Electrum source is configured. Sentinel normally
                # prefers Fulcrum/electrs for watch-only HD discovery.
                for address in addresses:
                    if await self._probe_gap_address_used(source, address):
                        scores[script_type] += 1

            if candidate_index + 1 < len(candidates):
                await asyncio.sleep(GAP_DISCOVERY_YIELD_SECONDS)
        best = max(candidates, key=lambda item: (scores[item], -candidates.index(item)))
        if scores[best] <= 0:
            # No history exists inside the configured gap. Native SegWit is the
            # modern default; the UI exposes an explicit override for new/empty
            # wallets where history cannot identify the script family.
            return "p2wpkh", False
        return best, True

    async def _probe_gap_address_used(
        self, source: dict[str, Any], address: str, *, electrum_client: _ElectrumRPCClient | None = None
    ) -> bool:
        if electrum_client is not None:
            history = await electrum_client.call(
                "blockchain.scripthash.get_history", [_electrum_scripthash(address)]
            )
            if not isinstance(history, list):
                raise ValueError("Electrum returned invalid address history during gap discovery")
            return bool(history)
        snapshot = await self._address_snapshot(source, address, False)
        return _address_summary_used(snapshot["summary"])

    async def _discover_gap_addresses(
        self, config: dict[str, Any], source: dict[str, Any], *, monitor_ids: set[str] | None = None
    ) -> None:
        """Resolve each HD branch as used addresses + N consecutive unused gap addresses.

        ``receive_count`` and ``change_count`` are gap limits, not total address
        counts.  Discovery is independent for receive (/0) and change (/1).
        A concrete-address standby pool is kept device-bound/encrypted so the
        watcher can extend the active gap while the password vault is locked.
        Public watch-only material is already kept in that device-bound runtime
        vault for owner-authorized locked editing; no spend keys are stored.
        """
        old_rows = [row for row in self.runtime_store.data.get("addresses", []) if isinstance(row, dict)]
        old_by_key = {
            (str(row.get("monitor_id") or ""), str(row.get("address") or "")): row
            for row in old_rows
        }
        target_ids = None if monitor_ids is None else {str(value) for value in monitor_ids}
        rebuilt: list[dict[str, Any]] = []
        # Keep monitors that are not part of this focused refresh unchanged.
        if target_ids is not None:
            rebuilt.extend(deepcopy(row) for row in old_rows if str(row.get("monitor_id") or "") not in target_ids)

        source_type = str(source.get("watch_source_type") or "mempool")
        client_cm = _ElectrumRPCClient(self, source) if source_type == "electrum" else None
        client = await client_cm.__aenter__() if client_cm is not None else None
        try:
            for monitor_slot, monitor in enumerate(config.get("monitors", []), start=1):
                monitor_id = str(monitor.get("id") or "")
                if target_ids is not None and monitor_id not in target_ids:
                    continue
                if not monitor.get("enabled", True):
                    continue
                if monitor.get("kind") == "address":
                    derived = {"address": monitor["value"], "branch": "fixed", "index": None}
                    row = self._runtime_row_from_monitor(monitor, monitor_slot, derived, active=True, used=None)
                    rebuilt.append(self._merge_runtime_row_state(row, old_by_key.get((monitor_id, row["address"]))))
                    continue

                monitor = deepcopy(monitor)
                if monitor.get("kind") == "xpub":
                    resolved_type, resolved_verified = await self._resolve_xpub_address_type(
                        monitor, source, electrum_client=client
                    )
                    monitor["_resolved_address_type"] = resolved_type
                    monitor["_resolved_address_type_verified"] = bool(resolved_verified)

                for branch, branch_name, gap_limit in (
                    (0, "receive", int(monitor.get("receive_count") or 0)),
                    (1, "change", int(monitor.get("change_count") or 0)),
                ):
                    if gap_limit <= 0:
                        continue
                    consecutive_unused = 0
                    seen_used = False
                    stop_index: int | None = None
                    branch_rows: list[dict[str, Any]] = []
                    bootstrap_floor = min(
                        MAX_GAP_DISCOVERY_ADDRESSES_PER_BRANCH,
                        max(gap_limit, HD_DISCOVERY_BOOTSTRAP_ADDRESSES),
                    )
                    for index in range(MAX_GAP_DISCOVERY_ADDRESSES_PER_BRANCH):
                        derived = self._derive_monitor_address(monitor, branch, index)
                        if derived is None:
                            break
                        last_error: Exception | None = None
                        for attempt in range(2):
                            try:
                                used = await self._probe_gap_address_used(
                                    source, str(derived["address"]), electrum_client=client
                                )
                                last_error = None
                                break
                            except (TimeoutError, asyncio.TimeoutError, ConnectionError) as err:
                                last_error = err
                                if attempt == 0:
                                    await asyncio.sleep(0.25)
                        if last_error is not None:
                            raise last_error
                        # Discovery is background work, not a benchmark. Pace
                        # local Fulcrum/electrs probes so a large historical XPUB
                        # cannot monopolize a Proxmox host shared with Home Assistant.
                        await asyncio.sleep(GAP_DISCOVERY_YIELD_SECONDS)
                        row = self._runtime_row_from_monitor(
                            monitor, monitor_slot, derived, active=True, used=used
                        )
                        row = self._merge_runtime_row_state(
                            row, old_by_key.get((monitor_id, row["address"]))
                        )
                        row["active"] = True
                        row["used"] = used
                        branch_rows.append(row)
                        if used:
                            seen_used = True
                            consecutive_unused = 0
                        else:
                            consecutive_unused += 1
                        if seen_used and consecutive_unused >= gap_limit:
                            stop_index = index
                            break
                        if not seen_used and index + 1 >= bootstrap_floor:
                            # Nothing was used inside the recovery look-ahead.
                            # Keep the configured active gap (not all 20 probes)
                            # and turn the following concrete addresses into the
                            # encrypted standby pool as before.
                            branch_rows = branch_rows[:gap_limit]
                            stop_index = max(0, gap_limit - 1)
                            break
                    if stop_index is None and branch_rows:
                        raise ValueError(
                            f"Sats Sentinel {branch_name} gap discovery reached the safety limit of "
                            f"{MAX_GAP_DISCOVERY_ADDRESSES_PER_BRANCH} addresses without finding "
                            f"{gap_limit} consecutive unused addresses"
                        )
                    rebuilt.extend(branch_rows)
                    if stop_index is None:
                        continue
                    # Concrete-address standby: allows automatic gap extension
                    # while the password vault is locked without further derivation
                    # during ordinary polling.
                    for offset in range(1, GAP_STANDBY_ADDRESSES_PER_BRANCH + 1):
                        derived = self._derive_monitor_address(monitor, branch, stop_index + offset)
                        if derived is None:
                            break
                        row = self._runtime_row_from_monitor(
                            monitor, monitor_slot, derived, active=False, used=None
                        )
                        row = self._merge_runtime_row_state(
                            row, old_by_key.get((monitor_id, row["address"]))
                        )
                        row["active"] = False
                        row["used"] = None
                        rebuilt.append(row)
        finally:
            if client_cm is not None:
                await client_cm.__aexit__(None, None, None)

        if len(rebuilt) > MAX_RUNTIME_ADDRESSES:
            raise ValueError(f"Sats Sentinel runtime address limit is {MAX_RUNTIME_ADDRESSES}")
        self.runtime_store.data["addresses"] = rebuilt
        # Remember the auto-detected script family without storing any additional
        # private material. This also invalidates pre-rc20 naked-xpub caches that
        # were derived as legacy merely because the serialization prefix was xpub.
        resolved_by_monitor: dict[str, tuple[str, bool]] = {}
        for row in rebuilt:
            if not isinstance(row, dict):
                continue
            resolved = str(row.get("resolved_address_type") or "")
            monitor_id = str(row.get("monitor_id") or "")
            if monitor_id and resolved in _XPUB_AUTO_CANDIDATES:
                resolved_by_monitor[monitor_id] = (resolved, bool(row.get("resolved_address_type_verified")))
        for item in self.runtime_store.data.get("monitor_catalog") or []:
            if not isinstance(item, dict):
                continue
            monitor_id = str(item.get("id") or "")
            if monitor_id in resolved_by_monitor:
                resolved, verified = resolved_by_monitor[monitor_id]
                item["resolved_address_type"] = resolved
                item["resolved_address_type_verified"] = verified
        await self.runtime_store.async_save()

    async def _maintain_gap_from_standby(self, source: dict[str, Any]) -> bool:
        """Activate standby addresses only when a branch actually lost its gap.

        The previous implementation opened and handshook a new Electrum/Fulcrum
        connection on every Sentinel poll even when every branch already had its
        configured unused reserve. On a local node that produced needless CPU,
        socket and TLS work. First determine whether any branch needs expansion;
        only then touch the network.
        """
        rows = [row for row in self.runtime_store.data.get("addresses", []) if isinstance(row, dict)]
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in rows:
            branch = str(row.get("branch") or "")
            if branch not in {"receive", "change"}:
                continue
            groups.setdefault((str(row.get("monitor_id") or ""), branch), []).append(row)

        pending: list[tuple[str, str, list[dict[str, Any]], int, int]] = []
        exhausted: list[str] = []
        for (monitor_id, branch), branch_rows in groups.items():
            branch_rows.sort(key=lambda item: int(item.get("index") or 0))
            active = [row for row in branch_rows if bool(row.get("active", True))]
            if not active:
                continue
            gap_limit = max(0, int(active[-1].get("gap_limit") or 0))
            if gap_limit <= 0:
                continue
            consecutive_unused = 0
            for row in reversed(active):
                if row.get("used") is False:
                    consecutive_unused += 1
                else:
                    break
            if consecutive_unused >= gap_limit:
                continue
            if not any(not bool(row.get("active", True)) for row in branch_rows):
                exhausted.append(f"{monitor_id}:{branch}")
                continue
            pending.append((monitor_id, branch, branch_rows, gap_limit, consecutive_unused))

        if not pending:
            if exhausted:
                self.runtime_store.data["last_warning"] = (
                    "Sats Sentinel gap standby exhausted for " + ", ".join(exhausted[:8]) +
                    ". Unlock the vault once to replenish pre-derived addresses."
                )[:500]
                await self._async_save_runtime_if_due(force=True)
            return False

        source_type = str(source.get("watch_source_type") or "mempool")
        client_cm = _ElectrumRPCClient(self, source) if source_type == "electrum" else None
        client = await client_cm.__aenter__() if client_cm is not None else None
        changed = False
        try:
            for monitor_id, branch, branch_rows, gap_limit, consecutive_unused in pending:
                while consecutive_unused < gap_limit:
                    candidate = next((row for row in branch_rows if not bool(row.get("active", True))), None)
                    if candidate is None:
                        exhausted.append(f"{monitor_id}:{branch}")
                        break
                    used = await self._probe_gap_address_used(
                        source, str(candidate.get("address") or ""), electrum_client=client
                    )
                    candidate["active"] = True
                    candidate["used"] = used
                    candidate["baseline_complete"] = False
                    changed = True
                    consecutive_unused = 0 if used else consecutive_unused + 1
                    # Be a polite local-node client. A hot Fulcrum instance can
                    # otherwise answer hundreds of gap probes per second and
                    # create host-wide CPU/I/O pressure.
                    await asyncio.sleep(GAP_DISCOVERY_YIELD_SECONDS)
        finally:
            if client_cm is not None:
                await client_cm.__aexit__(None, None, None)
        if exhausted:
            self.runtime_store.data["last_warning"] = (
                "Sats Sentinel gap standby exhausted for " + ", ".join(exhausted[:8]) +
                ". Unlock the vault once to replenish pre-derived addresses."
            )[:500]
        if changed or exhausted:
            await self._async_save_runtime_if_due(force=True)
        return changed

    def _runtime_matches_full_config(self, config: dict[str, Any]) -> bool:
        """Return True when the encrypted runtime cache already represents config.

        This lets restart/unlock recovery reuse a fully discovered XPUB instead
        of collapsing it to the raw gap counts and rescanning from index zero.
        No XPUB is stored in the runtime cache: we validate HD monitors by
        deriving only index 0 from the authoritative unlocked config and matching
        that concrete address against the encrypted runtime rows.
        """
        data = self.runtime_store.data
        if bool(data.get("enabled")) != bool(config.get("enabled")):
            return False
        source_keys = (
            "query_source", "electrum_kind", "electrum_host", "electrum_port",
            "electrum_tls", "electrum_verify_ssl", "electrum_pinned_cert_sha256",
            "allow_public_tor",
        )
        for key in source_keys:
            if data.get(key) != config.get(key):
                return False
        rows = [row for row in data.get("addresses", []) if isinstance(row, dict)]
        enabled_monitors = [m for m in config.get("monitors", []) if isinstance(m, dict) and m.get("enabled", True)]
        expected_ids = {str(m.get("id") or "") for m in enabled_monitors if str(m.get("id") or "")}
        runtime_ids = {str(r.get("monitor_id") or "") for r in rows if str(r.get("monitor_id") or "")}
        if expected_ids != runtime_ids:
            return False
        by_monitor: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_monitor.setdefault(str(row.get("monitor_id") or ""), []).append(row)
        catalog_by_id = {
            str(item.get("id") or ""): item
            for item in (data.get("monitor_catalog") or [])
            if isinstance(item, dict) and str(item.get("id") or "")
        }
        for monitor in enabled_monitors:
            monitor_id = str(monitor.get("id") or "")
            owned = by_monitor.get(monitor_id, [])
            if not owned:
                return False
            kind = str(monitor.get("kind") or "")
            if (
                kind == "xpub"
                and str(monitor.get("address_type") or "auto") == "auto"
                and str(monitor.get("value") or "").lower().startswith("xpub")
            ):
                resolved = str((catalog_by_id.get(monitor_id) or {}).get("resolved_address_type") or "")
                if resolved not in _XPUB_AUTO_CANDIDATES:
                    # Pre-rc20 runtime caches did not record which script family
                    # they used. Force one discovery pass so an old legacy-derived
                    # xpub cannot be silently reused with 0 BTC / Receive 2 / Change 2.
                    return False
            if kind == "address":
                if not any(str(row.get("address") or "") == str(monitor.get("value") or "") for row in owned):
                    return False
                continue
            for branch, gap_key in ((0, "receive_count"), (1, "change_count")):
                if int(monitor.get(gap_key) or 0) <= 0:
                    continue
                branch_name = "receive" if branch == 0 else "change"
                candidate_addresses: set[str] = set()
                if kind == "xpub" and str(monitor.get("address_type") or "auto") == "auto" and str(monitor.get("value") or "").lower().startswith("xpub"):
                    for script_type in _XPUB_AUTO_CANDIDATES:
                        candidate_addresses.add(str(derive_extpub_branch_address(
                            str(monitor.get("value") or ""), branch, 0, address_type=script_type
                        )["address"]))
                else:
                    derived = self._derive_monitor_address(monitor, branch, 0)
                    if derived is None:
                        return False
                    candidate_addresses.add(str(derived.get("address") or ""))
                if not any(
                    str(row.get("branch") or "") == branch_name
                    and int(row.get("index") or 0) == 0
                    and str(row.get("address") or "") in candidate_addresses
                    for row in owned
                ):
                    return False
        return True

    async def async_recover_unlocked_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Recover a richer watch-only runtime config before an unlocked read.

        The separately encrypted Sentinel runtime vault is deliberately capable
        of surviving portfolio auto-locks and Home Assistant restarts.  Older
        release candidates could leave the password-vault copy incomplete while
        the runtime vault still contained the real watch catalog, discovered HD
        addresses and Fulcrum/electrs endpoint.  Never let that older/emptier
        copy wipe the richer runtime state on the next unlock.

        Recovery is intentionally conservative: runtime monitors replace the
        password-vault list only for pending locked edits or when the password
        vault has no monitors at all.  Fulcrum/electrs settings are recovered only
        when the password-vault endpoint is empty and the runtime endpoint is
        present.  Explicit non-empty password-vault settings remain authoritative.
        """
        normalized = normalize_watch_config(config)
        data = self.runtime_store.data
        changed = False
        pending_sync = bool(data.get("pending_vault_sync"))

        runtime_monitors: list[dict[str, Any]] = []
        if data.get("monitor_catalog"):
            try:
                runtime_monitors = deepcopy(self._runtime_management_config().get("monitors") or [])
            except ValueError:
                # Pre-rc8 caches can have aggregate/address state without raw
                # watch-only material.  Those caches remain useful for status but
                # cannot safely reconstruct an editable XPUB/descriptor row.
                runtime_monitors = []

        if runtime_monitors and (pending_sync or not normalized.get("monitors")):
            normalized["monitors"] = runtime_monitors
            changed = True
            if not normalized.get("enabled") and bool(data.get("enabled")):
                normalized["enabled"] = True

        runtime_host = str(data.get("electrum_host") or "").strip()
        vault_host = str(normalized.get("electrum_host") or "").strip()

        # Runtime enabled state is authoritative when it contains actual Sentinel
        # watch/source material. This repairs the contradictory UI state where the
        # header said AKTIV while the settings checkbox was reset after unlock.
        if bool(data.get("enabled")) and not bool(normalized.get("enabled")) and (runtime_monitors or runtime_host or data.get("addresses")):
            normalized["enabled"] = True
            changed = True

        if runtime_host and not vault_host:
            for key in (
                "query_source", "electrum_kind", "electrum_host", "electrum_port",
                "electrum_tls", "electrum_verify_ssl", "electrum_pinned_cert_sha256",
                "allow_public_tor",
            ):
                normalized[key] = deepcopy(data.get(key))
            if not normalized.get("enabled") and bool(data.get("enabled")):
                normalized["enabled"] = True
            changed = True

        normalized = normalize_watch_config(normalized)
        if changed:
            await self.ledger_store.async_set_wallet_watch_config(normalized)
        if pending_sync and runtime_monitors:
            self.runtime_store.data["pending_vault_sync"] = False
            await self.runtime_store.async_save()
        return normalized

    async def async_restore_full_config(
        self, config: dict[str, Any], *, poll: bool = False
    ) -> dict[str, Any]:
        """Recover Sentinel after restart/unlock without a synchronous XPUB rescan."""
        try:
            normalized = await self.async_recover_unlocked_config(config)
        except Exception as err:
            # Recovery must never make the portfolio vault unusable.  Preserve
            # the runtime state and keep the warning visible instead of replacing
            # the cache with an incomplete password-vault snapshot.
            self.runtime_store.data["last_warning"] = (
                f"Sats Sentinel runtime recovery pending: {type(err).__name__}: {err}"
            )[:500]
            await self.runtime_store.async_save()
            return self.public_status(include_addresses=True)
        self.cancel_background_refresh()
        if self._runtime_matches_full_config(normalized):
            return self.public_status(include_addresses=True)
        purged_activity_count = await self.runtime_store.async_replace_from_full_config(normalized)
        if normalized["enabled"]:
            self.schedule_background_refresh(normalized, poll=poll)
        status = self.public_status(include_addresses=True)
        status["purged_activity_count"] = purged_activity_count
        return status

    async def async_update_settings(self, config: dict[str, Any]) -> dict[str, Any]:
        """Persist server/global Sentinel settings without touching watch targets.

        The monitor list stored in the password vault is authoritative. Browser
        drafts are allowed to change Fulcrum/electrs/Tor/poll/notification target
        settings, but they can never delete or rewrite existing addresses/xpubs.
        Existing per-wallet notification_detail values are preserved exactly; the
        server-level value is only the default used when a new monitor is created.

        Source persistence is deliberately defensive: an empty/stale browser Host
        field must never erase an already saved Fulcrum/electrs endpoint. This can
        otherwise happen after lock -> unlock when a reduced runtime form is still
        visible for a moment. Explicitly selecting a mempool source still changes
        the active source, but the saved Electrum endpoint is retained for a later
        switch back to Auto/Fulcrum/electrs.
        """
        incoming = normalize_watch_config(config)
        stored = await self.async_recover_unlocked_config(
            normalize_watch_config(self.ledger_store.wallet_watch_config)
        )
        incoming["monitors"] = deepcopy(stored.get("monitors") or [])

        # Never treat an empty host from a stale/partially rehydrated browser form
        # as an instruction to delete the saved Electrum endpoint. Keeping the
        # endpoint is harmless even when mempool_own/mempool_public is selected,
        # because _select_watch_source honours that explicit mode. A dedicated
        # server-delete action can be added later if intentional removal is needed.
        if not str(incoming.get("electrum_host") or "").strip() and str(stored.get("electrum_host") or "").strip():
            for key in (
                "electrum_kind", "electrum_host", "electrum_port", "electrum_tls",
                "electrum_verify_ssl", "electrum_pinned_cert_pem",
                "electrum_pinned_cert_sha256",
            ):
                incoming[key] = deepcopy(stored.get(key))
            # Preserve an explicit Fulcrum/electrs choice if the stale form fell
            # back to Auto. Explicit mempool choices remain explicit.
            if str(incoming.get("query_source") or "auto") == "auto" and str(stored.get("query_source") or "auto") in _ALLOWED_ELECTRUM_KINDS:
                incoming["query_source"] = str(stored.get("query_source"))

        normalized = normalize_watch_config(incoming)
        await self.ledger_store.async_set_wallet_watch_config(normalized)
        refresh_needed = await self.runtime_store.async_update_settings_from_config(normalized)
        # Only a real source change (or enabling Sentinel) replaces a currently
        # running discovery task. Pure UI/default/notification saves leave any
        # in-progress HD scan untouched. Even when discovery restarts, the already
        # found address set remains visible until the refreshed scan catches up.
        if normalized.get("enabled") and refresh_needed:
            self.schedule_background_refresh(normalized, poll=True)
        return {
            "saved": True,
            "config": normalized,
            "status": self.public_status(include_addresses=True),
        }

    async def async_apply_full_config(
        self, config: dict[str, Any], *, poll: bool = True
    ) -> dict[str, Any]:
        """Apply the encrypted Sentinel configuration and restore HD gap coverage.

        A full settings save historically rebuilt the runtime cache from the raw
        ``receive_count``/``change_count`` values. Since those values are gap
        limits (not total address counts), that silently collapsed an already
        discovered XPUB/descriptor back to e.g. Receive 2 + Change 2. Re-run the
        causal gap discovery whenever the full encrypted configuration is
        activated so balance, UTXOs and transaction history cover all used
        addresses plus the configured unused reserve on both branches.
        """
        normalized = normalize_watch_config(config)
        self.cancel_background_refresh()
        purged_activity_count = await self.runtime_store.async_replace_from_full_config(normalized)
        if normalized["enabled"]:
            source = _select_watch_source(self.entry, normalized)
            if source is not None:
                try:
                    await self._discover_gap_addresses(normalized, source)
                    self.runtime_store.data["last_warning"] = None
                    self.runtime_store.data["partial_failures"] = 0
                    await self.runtime_store.async_save()
                except Exception as err:
                    # Keep the encrypted configuration saved even if the node is
                    # temporarily unavailable. The next explicit save/startup can
                    # retry discovery; never invent a clearnet/provider fallback.
                    self.runtime_store.data["last_warning"] = (
                        f"Sats Sentinel gap discovery pending: {type(err).__name__}: {err}"
                    )[:500]
                    await self.runtime_store.async_save()
            if poll:
                await self.async_poll(force=True)
        status = self.public_status(include_addresses=True)
        status["purged_activity_count"] = purged_activity_count
        return status

    async def async_upsert_monitor(self, monitor: dict[str, Any]) -> dict[str, Any]:
        """Add or update one watch target without rewriting source settings.

        The encrypted backend configuration remains authoritative for Fulcrum,
        TLS, Tor and notification settings. Only the requested monitor row is
        replaced/added, so saving a watch target cannot wipe an unsaved node
        form draft in the browser or change the selected source.
        """
        if not isinstance(monitor, dict):
            raise ValueError("Sats Sentinel watch entry is missing")
        monitor_id = str(monitor.get("id") or "").strip()
        if not monitor_id:
            raise ValueError("Sats Sentinel monitor ID is missing")
        # Cancel a stale scan before the first persistence await. Otherwise an
        # older discovery task could finish while this newer monitor is being
        # saved and overwrite the just-updated runtime address set.
        self.cancel_background_refresh()
        old_config = normalize_watch_config(self.ledger_store.wallet_watch_config)
        monitor = deepcopy(monitor)
        # Editing a runtime-recovered watch card may intentionally send an empty
        # value so the raw XPUB/descriptor/address never has to be exposed to the
        # browser.  Preserve the existing watch-only value from the password vault
        # or, if that copy is incomplete, from the encrypted runtime catalog.
        if not str(monitor.get("value") or "").strip():
            existing_value = next((
                str(item.get("value") or "")
                for item in old_config.get("monitors", [])
                if str(item.get("id") or "") == monitor_id
            ), "")
            if not existing_value:
                try:
                    existing_value = next((
                        str(item.get("value") or "")
                        for item in self._runtime_management_config().get("monitors", [])
                        if str(item.get("id") or "") == monitor_id
                    ), "")
                except ValueError:
                    existing_value = ""
            if not existing_value:
                raise ValueError("Sats Sentinel watch value is missing")
            monitor["value"] = existing_value
        new_config = deepcopy(old_config)
        rows = list(new_config.get("monitors", []))
        replaced = False
        for index, item in enumerate(rows):
            if str(item.get("id") or "") == monitor_id:
                rows[index] = deepcopy(monitor)
                replaced = True
                break
        if not replaced:
            rows.append(deepcopy(monitor))
        new_config["monitors"] = rows
        new_config = normalize_watch_config(new_config)
        runtime_backup = deepcopy(self.runtime_store.data)
        try:
            await self.ledger_store.async_set_wallet_watch_config(new_config)
            await self.runtime_store.async_replace_from_full_config(new_config)
        except Exception:
            self.runtime_store.data = runtime_backup
            try:
                await self.runtime_store.async_save()
            except Exception:
                pass
            try:
                await self.ledger_store.async_set_wallet_watch_config(old_config)
            except Exception:
                pass
            raise
        # Persist first, then discover the complete used+gap address range in a
        # Home Assistant background task. A long XPUB history must never keep the
        # panel HTTP request open until Fulcrum scanning finishes.
        self.schedule_background_refresh(
            new_config, monitor_ids={monitor_id}, poll=True
        )
        return {
            "saved": True,
            "monitor_id": monitor_id,
            "config": new_config,
            "status": self.public_status(include_addresses=True),
        }

    async def async_remove_monitor(self, monitor_id: str) -> dict[str, Any]:
        """Remove one saved watch target without rewriting source settings from a browser draft.

        The full stored Sentinel config is authoritative. This avoids a delete action
        accidentally changing Fulcrum/Tor/TLS settings because a stale form happened
        to contain different values. Journal rows for the monitor are purged from the
        encrypted runtime cache as part of the same operation.
        """
        monitor_id = str(monitor_id or "").strip()
        if not monitor_id:
            raise ValueError("Sats Sentinel monitor ID is missing")
        old_config = normalize_watch_config(self.ledger_store.wallet_watch_config)
        if not any(str(item.get("id") or "") == monitor_id for item in old_config.get("monitors", [])):
            raise ValueError("Sats Sentinel watch entry was not found")
        new_config = deepcopy(old_config)
        new_config["monitors"] = [
            item for item in new_config.get("monitors", [])
            if str(item.get("id") or "") != monitor_id
        ]
        runtime_backup = deepcopy(self.runtime_store.data)
        try:
            await self.ledger_store.async_set_wallet_watch_config(new_config)
            purged_activity_count = await self.runtime_store.async_replace_from_full_config(new_config)
        except Exception:
            # Best-effort rollback. Most importantly, never leave the in-memory
            # source selection changed by a failed delete operation.
            self.runtime_store.data = runtime_backup
            try:
                await self.runtime_store.async_save()
            except Exception:
                pass
            try:
                await self.ledger_store.async_set_wallet_watch_config(old_config)
            except Exception:
                pass
            raise
        status = self.public_status(include_addresses=True)
        status["purged_activity_count"] = purged_activity_count
        return {"removed": True, "monitor_id": monitor_id, "config": new_config, "status": status}

    async def async_test_source(self, config: dict[str, Any]) -> dict[str, Any]:
        """Probe exactly the source selected in the supplied Sentinel config.

        This is intentionally a connection/capability test only. It does not
        touch wallet baselines, activity history, or notification state and it
        never falls back to a second provider.
        """
        normalized = normalize_watch_config(config)
        source = _select_watch_source(self.entry, normalized)
        if source is None:
            mode = str(normalized.get("query_source") or "auto")
            raise ValueError(
                f"No Sats Sentinel data source is available for selection '{mode}'"
            )
        source_type = str(source.get("watch_source_type") or "mempool")
        if source_type == "electrum":
            async with asyncio.timeout(ELECTRUM_REQUEST_TIMEOUT_SECONDS):
                async with _ElectrumRPCClient(self, source) as client:
                    version = client.server_version
            host = str(source.get("host") or "")
            port = int(source.get("port") or 0)
            return {
                "ok": True,
                "source_type": "electrum",
                "label": str(source.get("label") or "Electrum"),
                "route": str(source.get("route") or "direct"),
                "endpoint": f"{host}:{port}",
                "server_version": version,
                "tls": bool(source.get("tls")),
                "certificate_pinned": bool(str(source.get("pinned_cert_sha256") or "")),
            }

        height_text = await self._request_text(source, "/api/blocks/tip/height")
        try:
            height = int(str(height_text).strip())
        except ValueError as err:
            raise ValueError("Mempool source returned an invalid block height") from err
        return {
            "ok": True,
            "source_type": "mempool",
            "label": str(source.get("label") or "Mempool"),
            "route": "tor" if mempool_source_uses_tor(source) else "direct",
            "endpoint": _canonical_mempool_base_url(source.get(CONF_BASE_URL)),
            "block_height": height,
        }

    def public_status(self, *, include_addresses: bool = False) -> dict[str, Any]:
        data = self.runtime_store.data
        addresses = [
            row for row in data.get("addresses", [])
            if isinstance(row, dict) and bool(row.get("active", True))
        ]
        monitor_summaries: dict[str, dict[str, Any]] = {}
        total_balance_sats = 0
        total_utxo_count = 0
        baseline_complete = bool(addresses)
        for row in addresses:
            total_balance_sats += int(row.get("balance_sats") or 0)
            total_utxo_count += int(row.get("utxo_count") or 0)
            baseline_complete = baseline_complete and bool(row.get("baseline_complete"))
            monitor_id = str(row.get("monitor_id") or "")
            if not monitor_id:
                continue
            summary = monitor_summaries.setdefault(
                monitor_id,
                {
                    "address_count": 0,
                    "receive_address_count": 0,
                    "change_address_count": 0,
                    "receive_used_count": 0,
                    "change_used_count": 0,
                    "balance_sats": 0,
                    "utxo_count": 0,
                    "baseline_complete": True,
                    "resolved_address_type": "",
                    "resolved_address_type_verified": False,
                },
            )
            summary["address_count"] += 1
            branch = str(row.get("branch") or "")
            if branch == "receive":
                summary["receive_address_count"] += 1
                if row.get("used") is True:
                    summary["receive_used_count"] += 1
            elif branch == "change":
                summary["change_address_count"] += 1
                if row.get("used") is True:
                    summary["change_used_count"] += 1
            summary["balance_sats"] += int(row.get("balance_sats") or 0)
            summary["utxo_count"] += int(row.get("utxo_count") or 0)
            if row.get("resolved_address_type"):
                summary["resolved_address_type"] = str(row.get("resolved_address_type") or "")
                summary["resolved_address_type_verified"] = bool(row.get("resolved_address_type_verified"))
            summary["baseline_complete"] = bool(summary["baseline_complete"]) and bool(
                row.get("baseline_complete")
            )

        activity_rows = [item for item in data.get("activity_log", []) if isinstance(item, dict)]
        last_activity_by_monitor: dict[str, dict[str, Any]] = {}
        last_activity_at: str | None = None
        for item in activity_rows:
            monitor_id = str(item.get("monitor_id") or "")
            detected_at = str(item.get("detected_at") or "")
            if not monitor_id or not detected_at:
                continue
            if last_activity_at is None or detected_at > last_activity_at:
                last_activity_at = detected_at
            current = last_activity_by_monitor.get(monitor_id)
            if current is None or detected_at > str(current.get("detected_at") or ""):
                last_activity_by_monitor[monitor_id] = {
                    "detected_at": detected_at,
                    "direction": str(item.get("direction") or ""),
                    "amount_sats": int(item.get("amount_sats") or 0),
                    "confirmed": bool(item.get("confirmed")),
                }
        own_mempool = _own_mempool_source(self.entry)
        public_mempool = _public_mempool_source(self.entry)
        selected = _select_watch_source(self.entry, data)
        selected_type = str(selected.get("watch_source_type") or "") if selected else ""
        if selected_type == "electrum":
            selected_label = str(selected.get("label") or "Electrum")
            selected_route = "tor" if str(selected.get("route")) == "tor" else "direct"
        elif selected_type == "mempool":
            selected_label = str(selected.get("label") or "Mempool")
            selected_route = "tor" if mempool_source_uses_tor(selected) else "direct"
        else:
            selected_label = ""
            selected_route = ""
        result = {
            "enabled": bool(data.get("enabled")),
            "poll_interval_seconds": int(data.get("poll_interval_seconds") or DEFAULT_POLL_SECONDS),
            "query_source": str(data.get("query_source") or "auto"),
            "electrum_configured": bool(str(data.get("electrum_host") or "")),
            "electrum_certificate_pinned": bool(str(data.get("electrum_pinned_cert_sha256") or "")),
            "electrum_kind": str(data.get("electrum_kind") or "fulcrum"),
            "selected_source_type": selected_type,
            "selected_source_label": selected_label,
            "selected_source_route": selected_route,
            "allow_public_tor": bool(data.get("allow_public_tor")),
            "own_mempool_configured": bool(own_mempool),
            "own_mempool_onion": bool(own_mempool and is_onion_url(str(own_mempool.get(CONF_BASE_URL) or ""))),
            "configured_public_mempool": bool(public_mempool),
            "public_tor_effective": bool(selected_type == "mempool" and selected_route == "tor" and not bool(own_mempool)),
            "address_count": len(addresses),
            "baseline_complete": baseline_complete,
            "balance_sats": total_balance_sats,
            "utxo_count": total_utxo_count,
            "last_poll_at": data.get("last_poll_at"),
            "last_success_at": data.get("last_success_at"),
            "activity_log_count": len(activity_rows),
            "last_activity_at": last_activity_at,
            # Privacy-safe per-monitor aggregates are always returned, even when
            # concrete addresses are intentionally omitted from the lightweight
            # status endpoint. This keeps each watch card's balance/address/UTXO
            # counts correct without exposing address material while the vault is
            # locked or forcing the historical transaction view to be opened.
            "monitor_summaries": monitor_summaries,
            # Labels/type/gap settings are copied from the password vault only
            # into the device-bound encrypted runtime cache. The raw watch key
            # (address/xpub/descriptor) is never included here. This lets the
            # owner keep a read-only Sats Sentinel overview after auto-lock.
            # Owner-safe management metadata stays available while the main
            # portfolio vault is locked. Raw watch-only keys are never returned;
            # only a short mask is exposed for orientation/editing.
            "monitor_catalog": self.public_locked_management_config().get("monitors", []),
            "last_activity_by_monitor": last_activity_by_monitor,
            "last_error": data.get("last_error"),
            "last_warning": data.get("last_warning"),
            "scan_in_progress": bool(
                self._refresh_task is not None and not self._refresh_task.done()
            ),
            "partial_failures": int(data.get("partial_failures") or 0),
            "last_partial_at": data.get("last_partial_at"),
            "error_streak": int(data.get("error_streak") or 0),
            "route_policy": "explicit source is fail-closed; automatic selection is configuration-based only; own/local direct, onion/public through Tor; no runtime provider fallback",
            "xpub_in_runtime": any(str(item.get("kind") or "") == "xpub" and bool(item.get("watch_value")) for item in (data.get("monitor_catalog") or []) if isinstance(item, dict)),
            "descriptor_in_runtime": any(str(item.get("kind") or "") == "descriptor" and bool(item.get("watch_value")) for item in (data.get("monitor_catalog") or []) if isinstance(item, dict)),
            "runtime_cache_encrypted": True,
            "locked_runtime_summary_available": bool(data.get("monitor_catalog") or addresses),
            "watch_material_password_vault": True,
            "watch_material_runtime_encrypted": True,
            "pending_vault_sync": bool(data.get("pending_vault_sync")),
            "historical_tx_overview_persisted": False,
            "external_notification_targets": sum(1 for item in data.get("notification_targets", []) if isinstance(item, dict) and item.get("enabled", True)),
            "last_notification_success_at": data.get("last_notification_success_at"),
            "last_notification_error": data.get("last_notification_error"),
            "notification_delivery_failures": int(data.get("notification_delivery_failures") or 0),
        }
        if include_addresses:
            result["addresses"] = [
                {
                    "monitor_id": row.get("monitor_id"), "monitor_slot": row.get("monitor_slot"), "address": row.get("address"),
                    "branch": row.get("branch"), "index": row.get("index"),
                    "gap_limit": int(row.get("gap_limit") or 0),
                    "used": row.get("used"),
                    "baseline_complete": bool(row.get("baseline_complete")),
                    "balance_sats": int(row.get("balance_sats") or 0),
                    "utxo_count": int(row.get("utxo_count") or 0),
                    "last_activity_at": row.get("last_activity_at"),
                }
                for row in addresses
            ]
        return result

    async def _request_text(self, source: dict[str, Any], path: str) -> str:
        settings = effective_settings(self.entry)
        base = _canonical_mempool_base_url(source.get(CONF_BASE_URL))
        target = f"{base}{path}"
        uses_tor = mempool_source_uses_tor(source)
        async with async_routed_session(
            self.hass,
            target_url=target,
            proxy_url=tor_proxy_from_settings(settings) if uses_tor else None,
            allow_local_direct=not uses_tor,
            verify_ssl=bool(source.get(CONF_VERIFY_SSL, True)),
        ) as (session, kwargs):
            async with asyncio.timeout(SUMMARY_REQUEST_TIMEOUT_SECONDS):
                response = await session.get(target, headers={"Accept": "text/plain"}, **kwargs)
                response.raise_for_status()
                raw = await response.content.read(256)
                if len(raw) >= 256:
                    raise ValueError("Mempool text response exceeds Sentinel safety limit")
                return raw.decode("utf-8", errors="strict")

    async def _request_json(self, source: dict[str, Any], path: str) -> Any:
        settings = effective_settings(self.entry)
        base = _canonical_mempool_base_url(source.get(CONF_BASE_URL))
        target = f"{base}{path}"
        uses_tor = mempool_source_uses_tor(source)
        async with async_routed_session(
            self.hass,
            target_url=target,
            proxy_url=tor_proxy_from_settings(settings) if uses_tor else None,
            allow_local_direct=not uses_tor,
            verify_ssl=bool(source.get(CONF_VERIFY_SSL, True)),
        ) as (session, kwargs):
            request_timeout = TX_REQUEST_TIMEOUT_SECONDS if "/txs" in path else SUMMARY_REQUEST_TIMEOUT_SECONDS
            async with asyncio.timeout(request_timeout):
                response = await session.get(target, headers={"Accept": "application/json"}, **kwargs)
                response.raise_for_status()
                return await async_json_limited(response)

    async def _address_api_json(
        self, source: dict[str, Any], address: str, suffix: str = ""
    ) -> Any:
        """Read one address endpoint from the exact same configured node.

        Standard mempool/nginx exposes Esplora at ``/api/address``.  Some
        self-hosted/simple deployments expose the compatible route through the
        backend namespace ``/api/v1/address`` instead.  A 404 may therefore
        retry only that path variant on the *same base URL*.  No host/provider
        fallback is permitted here.
        """
        encoded = quote(address, safe="")
        base = _canonical_mempool_base_url(source.get(CONF_BASE_URL))
        cached = self._address_api_prefix_by_base.get(base)
        prefixes = [cached] if cached else []
        prefixes += [item for item in ("/api/address", "/api/v1/address") if item not in prefixes]
        last_error: Exception | None = None
        for prefix in prefixes:
            try:
                payload = await self._request_json(source, f"{prefix}/{encoded}{suffix}")
                self._address_api_prefix_by_base[base] = prefix
                return payload
            except Exception as err:
                last_error = err
                # Only a route-not-found is eligible for the same-node path
                # compatibility retry. Network/TLS/auth/etc. failures stop.
                if getattr(err, "status", None) == 404:
                    continue
                raise
        if last_error is not None:
            raise last_error
        raise ValueError("mempool address API path could not be resolved")

    async def _address_snapshot(self, source: dict[str, Any], address: str, need_txs: bool) -> dict[str, Any]:
        """Read only address summary + transaction history from the own node.

        `/address/:address/utxo` is deliberately not required. Some self-hosted
        mempool deployments expose address and transaction routes but omit the
        UTXO route. Balance and output count are derived from chain_stats and
        mempool_stats instead.
        """
        summary = await self._address_api_json(source, address)
        if not isinstance(summary, dict):
            raise ValueError("mempool address endpoint returned invalid data")
        result = {
            "summary": summary,
            "txs": None,
            "utxo_count": _utxo_count_from_summary(summary),
        }
        if need_txs:
            txs = await self._address_api_json(source, address, "/txs")
            if not isinstance(txs, list):
                raise ValueError("mempool address transaction endpoint returned invalid data")
            # Esplora /address/:address/txs already returns up to 50 mempool
            # transactions plus the newest confirmed transactions, so one
            # endpoint is enough for normal polling and initial baseline.
            result["txs"] = txs[:75]
        return result

    async def _poll_electrum_source(
        self, source: dict[str, Any], addresses: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Poll one explicit Fulcrum/electrs endpoint without burst-loading HA.

        All concrete addresses still receive a lightweight subscription/status
        check on every Sentinel cycle, but requests are split into small batches
        with cooperative yields. Expensive baseline work is spread across cycles,
        and routine balance reconciliation is low-frequency and staggered.
        """
        activities: list[dict[str, Any]] = []
        partial_errors: list[str] = []
        now_unix = int(datetime.now(timezone.utc).timestamp())
        async with _ElectrumRPCClient(self, source) as client:
            meta: list[tuple[dict[str, Any], str]] = []
            for row in addresses:
                address = str(row.get("address") or "")
                meta.append((row, _electrum_scripthash(address)))

            status_results = await self._electrum_calls_chunked(
                client,
                [("blockchain.scripthash.subscribe", [scripthash]) for _row, scripthash in meta],
                chunk_size=ELECTRUM_STATUS_BATCH_SIZE,
            )

            baseline_rows: list[tuple[dict[str, Any], str, str]] = []
            changed_rows: list[tuple[dict[str, Any], str, str]] = []
            reconcile_candidates: list[tuple[dict[str, Any], str, str]] = []
            for (row, scripthash), status in zip(meta, status_results):
                row["used"] = status not in {None, ""}
                signature = f"electrum:{status or ''}"
                if not row.get("baseline_complete"):
                    baseline_rows.append((row, scripthash, signature))
                    continue
                if signature != str(row.get("summary_signature") or ""):
                    changed_rows.append((row, scripthash, signature))
                    continue
                last_balance = int(row.get("last_balance_refresh_unix") or 0)
                if now_unix - last_balance >= ELECTRUM_BALANCE_RECONCILE_SECONDS:
                    reconcile_candidates.append((row, scripthash, signature))

            # A newly discovered large XPUB can contain hundreds of addresses.
            # Baseline them over several poll cycles instead of issuing 3N+ RPCs
            # immediately after discovery. Oldest/stalest rows are reconciled in
            # the same staggered fashion.
            baseline_batch = baseline_rows[:ELECTRUM_BASELINE_BATCH_SIZE]
            reconcile_candidates.sort(key=lambda item: int(item[0].get("last_balance_refresh_unix") or 0))
            reconcile_rows = reconcile_candidates[:ELECTRUM_RECONCILE_BATCH_SIZE]
            detail_rows = changed_rows + baseline_batch

            if detail_rows:
                balance_results = await self._electrum_calls_chunked(
                    client,
                    [("blockchain.scripthash.get_balance", [scripthash]) for _row, scripthash, _sig in detail_rows],
                )
                unspent_results = await self._electrum_calls_chunked(
                    client,
                    [("blockchain.scripthash.listunspent", [scripthash]) for _row, scripthash, _sig in detail_rows],
                )
                valid_detail: list[tuple[dict[str, Any], str, str]] = []
                for (row, scripthash, signature), balance, unspent in zip(detail_rows, balance_results, unspent_results):
                    if not isinstance(balance, dict) or not isinstance(unspent, list):
                        partial_errors.append(
                            f"Wallet {row.get('monitor_slot', '?')}: invalid Electrum balance/UTXO response"
                        )
                        continue
                    row["balance_sats"] = int(balance.get("confirmed") or 0) + int(balance.get("unconfirmed") or 0)
                    row["utxo_count"] = len(unspent)
                    row["last_balance_refresh_unix"] = now_unix
                    valid_detail.append((row, scripthash, signature))
                detail_rows = valid_detail

            # Safety reconciliation for unchanged subscriptions only needs the
            # balance call. If it differs unexpectedly, promote that row to the
            # detailed path on the next cycle rather than fetching UTXOs/history
            # for every unchanged address every 15 minutes.
            if reconcile_rows:
                reconcile_balances = await self._electrum_calls_chunked(
                    client,
                    [("blockchain.scripthash.get_balance", [scripthash]) for _row, scripthash, _sig in reconcile_rows],
                    chunk_size=ELECTRUM_RECONCILE_BATCH_SIZE,
                )
                for (row, _scripthash, _signature), balance in zip(reconcile_rows, reconcile_balances):
                    if not isinstance(balance, dict):
                        partial_errors.append(
                            f"Wallet {row.get('monitor_slot', '?')}: invalid Electrum reconcile response"
                        )
                        continue
                    new_balance = int(balance.get("confirmed") or 0) + int(balance.get("unconfirmed") or 0)
                    if new_balance != int(row.get("balance_sats") or 0):
                        # Preserve the new balance immediately and force a full
                        # detail refresh next cycle without fabricating a tx event.
                        row["balance_sats"] = new_balance
                        row["baseline_complete"] = False
                    row["last_balance_refresh_unix"] = now_unix

            if not detail_rows:
                return activities, partial_errors

            history_results = await self._electrum_calls_chunked(
                client,
                [("blockchain.scripthash.get_history", [scripthash]) for _row, scripthash, _sig in detail_rows],
            )
            new_entries: list[tuple[dict[str, Any], str, int]] = []
            for (row, _scripthash, signature), history in zip(detail_rows, history_results):
                if not isinstance(history, list):
                    partial_errors.append(f"Wallet {row.get('monitor_slot', '?')}: invalid Electrum history response")
                    continue
                normalized_history = [
                    item for item in history
                    if isinstance(item, dict) and re.fullmatch(r"[0-9a-fA-F]{64}", str(item.get("tx_hash") or ""))
                ]
                latest = normalized_history[-75:]
                txids = [str(item.get("tx_hash") or "").lower() for item in latest]
                known = set(str(item).lower() for item in row.get("known_txids", []))
                if row.get("baseline_complete"):
                    for item in latest:
                        txid = str(item.get("tx_hash") or "").lower()
                        if txid and txid not in known:
                            new_entries.append((row, txid, int(item.get("height") or 0)))
                row["known_txids"] = txids
                row["summary_signature"] = signature
                row["baseline_complete"] = True

            if not new_entries:
                return activities, partial_errors

            unique_txids = list(dict.fromkeys(txid for _row, txid, _height in new_entries))
            raw_results = await self._electrum_calls_chunked(
                client, [("blockchain.transaction.get", [txid, False]) for txid in unique_txids]
            )
            parsed_by_txid: dict[str, dict[str, Any]] = {}
            for txid, raw in zip(unique_txids, raw_results):
                if isinstance(raw, str):
                    parsed_by_txid[txid] = _parse_raw_transaction(raw)
            prev_txids = list(dict.fromkeys(
                str(txin.get("txid") or "")
                for tx in parsed_by_txid.values()
                for txin in tx.get("inputs", [])
                if str(txin.get("txid") or "") and str(txin.get("txid") or "") != "0" * 64
            ))
            prev_by_txid: dict[str, dict[str, Any]] = {}
            if prev_txids:
                prev_raw = await self._electrum_calls_chunked(
                    client, [("blockchain.transaction.get", [txid, False]) for txid in prev_txids]
                )
                for txid, raw in zip(prev_txids, prev_raw):
                    if isinstance(raw, str):
                        prev_by_txid[txid] = _parse_raw_transaction(raw)

            for row, txid, height in new_entries:
                parsed = parsed_by_txid.get(txid)
                if not parsed:
                    partial_errors.append(f"Wallet {row.get('monitor_slot', '?')}: Electrum transaction {txid[:12]} unavailable")
                    continue
                event = _electrum_event_from_parsed(
                    txid, parsed, prev_by_txid, str(row.get("address") or ""), height
                )
                if event["spent_sats"] or event["received_sats"]:
                    activities.append({"row": row, "event": event})
                    row["last_activity_at"] = datetime.now(timezone.utc).isoformat()
        return activities, partial_errors

    async def _electrum_calls_chunked(
        self, client: _ElectrumRPCClient, calls: list[tuple[str, list[Any]]], *,
        chunk_size: int = ELECTRUM_STATUS_BATCH_SIZE,
        yield_seconds: float = ELECTRUM_BATCH_YIELD_SECONDS,
    ) -> list[Any]:
        """Run Electrum RPCs in bounded bursts and yield back to Home Assistant."""
        results: list[Any] = []
        size = max(1, int(chunk_size))
        for offset in range(0, len(calls), size):
            results.extend(await client.call_many(calls[offset:offset + size]))
            if offset + size < len(calls):
                await asyncio.sleep(max(0.0, float(yield_seconds)))
        return results


    async def _electrum_overview_calls_resilient(
        self, client: _ElectrumRPCClient, calls: list[tuple[str, list[Any]]], *, label: str
    ) -> tuple[list[Any], list[str]]:
        """Run user-requested overview RPCs without failing the whole wallet on a Core timeout.

        Fulcrum/electrs can return JSON-RPC -32603 when its Bitcoin Core backend
        times out while fetching an old/raw transaction.  Historical overview is
        non-alerting, so retry the affected call once and then return a partial
        result with a warning instead of turning one backend timeout into a hard
        Home Assistant UI error.  Other RPC/network errors stay fail-closed.
        """
        results: list[Any] = []
        warnings: list[str] = []
        for method, params in calls:
            value: Any = None
            timed_out = False
            for attempt in range(2):
                try:
                    value = await client.call(method, params)
                    timed_out = False
                    break
                except RuntimeError as err:
                    text = str(err).lower()
                    if "bitcoind request timed out" not in text:
                        raise
                    timed_out = True
                    if attempt == 0:
                        await asyncio.sleep(0.35)
            results.append(None if timed_out else value)
            if timed_out:
                warnings.append(
                    f"{label}: Fulcrum/electrs Bitcoin Core backend timed out; partial overview shown"
                )
            # Historical overview is user-triggered; always yield so it cannot
            # monopolize Home Assistant while walking older wallet history.
            await asyncio.sleep(0)
        return results, warnings

    def _sentinel_detected_txids(self, monitor_id: str) -> dict[str, str]:
        detected: dict[str, str] = {}
        for item in self.runtime_store.data.get("activity_log", []) or []:
            if not isinstance(item, dict) or str(item.get("monitor_id") or "") != monitor_id:
                continue
            txid = str(item.get("txid") or "").lower()
            if re.fullmatch(r"[0-9a-f]{64}", txid):
                detected[txid] = str(item.get("detected_at") or "")
        return detected

    def _finalize_monitor_overview(
        self,
        *,
        config: dict[str, Any],
        monitor: dict[str, Any],
        source: dict[str, Any],
        rows: list[dict[str, Any]],
        transactions: list[dict[str, Any]],
        balance_sats: int,
        known_transaction_count: int,
        warnings: list[str] | None = None,
        page: int = 1,
        unlimited: bool = False,
        has_more: bool = False,
    ) -> dict[str, Any]:
        monitor_id = str(monitor.get("id") or "")
        detected = self._sentinel_detected_txids(monitor_id)
        loaded_in = 0
        loaded_out = 0
        loaded_tx_inputs = 0
        loaded_tx_outputs = 0
        loaded_fees = 0
        complete_input_totals = True
        for item in transactions:
            txid = str(item.get("txid") or "").lower()
            item["sentinel_detected"] = txid in detected
            item["sentinel_detected_at"] = detected.get(txid) or None
            if item.get("direction") == "outgoing":
                loaded_out += int(item.get("amount_sats") or 0)
            else:
                loaded_in += int(item.get("amount_sats") or 0)
            if item.get("tx_total_input_sats") is None:
                complete_input_totals = False
            else:
                loaded_tx_inputs += int(item.get("tx_total_input_sats") or 0)
            loaded_tx_outputs += int(item.get("tx_total_output_sats") or 0)
            if item.get("fee_sats") is not None:
                loaded_fees += int(item.get("fee_sats") or 0)
        explorer = _explorer_mempool_source(self.entry, bool(config.get("allow_public_tor")))
        source_type = str(source.get("watch_source_type") or "mempool")
        source_route = "tor" if (str(source.get("route")) == "tor" or (source_type == "mempool" and mempool_source_uses_tor(source))) else "direct"
        return {
            "monitor_id": monitor_id,
            "monitor_label": str(monitor.get("label") or monitor_id),
            "monitor_kind": str(monitor.get("kind") or "address"),
            "history_limit": int(monitor.get("history_limit") or DEFAULT_TX_OVERVIEW_LIMIT),
            "derived_address_count": len(rows),
            "balance_sats": int(balance_sats),
            "utxo_count": sum(int(row.get("utxo_count") or 0) for row in rows),
            "known_transaction_count": int(known_transaction_count),
            "loaded_transaction_count": len(transactions),
            "history_unlimited": bool(unlimited),
            "page": max(1, int(page)),
            "page_size": TX_OVERVIEW_PAGE_SIZE if unlimited else len(transactions),
            "pages": ((int(known_transaction_count) + TX_OVERVIEW_PAGE_SIZE - 1) // TX_OVERVIEW_PAGE_SIZE) if unlimited and int(known_transaction_count) >= 0 else 1,
            "has_more": bool(has_more),
            "loaded_in_sats": loaded_in,
            "loaded_out_sats": loaded_out,
            "loaded_tx_total_input_sats": loaded_tx_inputs if complete_input_totals else None,
            "loaded_tx_total_output_sats": loaded_tx_outputs,
            "loaded_fee_sats": loaded_fees,
            "address_balances": [
                {
                    "address": str(row.get("address") or ""),
                    "branch": str(row.get("branch") or ""),
                    "index": row.get("index"),
                    "balance_sats": int(row.get("balance_sats") or 0),
                    "utxo_count": int(row.get("utxo_count") or 0),
                }
                for row in rows
            ],
            "transactions": transactions,
            "source_label": str(source.get("label") or ""),
            "source_type": source_type,
            "source_route": source_route,
            "explorer_base_url": _canonical_mempool_base_url(explorer.get(CONF_BASE_URL)) if explorer else "",
            "warnings": list(warnings or []),
            "overview_only": True,
            "alerts_generated": False,
            # Historical overview rows are intentionally ephemeral: unlike the
            # Sentinel journal they are not written to HA Store at all.
            "transaction_overview_persisted": False,
            "runtime_addresses_encrypted": True,
            "journal_encrypted": True,
            "watch_material_password_vault": True,
        }

    async def _monitor_overview_electrum(
        self,
        *,
        config: dict[str, Any],
        monitor: dict[str, Any],
        source: dict[str, Any],
        rows: list[dict[str, Any]],
        limit: int,
        page: int = 1,
    ) -> dict[str, Any]:
        watched_addresses = {str(row.get("address") or "") for row in rows if str(row.get("address") or "")}
        warnings: list[str] = []
        # Balance/UTXO are already maintained by Sentinel's normal lightweight
        # polling path.  Re-querying them when the user merely opens historical
        # TX creates avoidable Fulcrum -> bitcoind pressure and used to make the
        # overview fail even though the current wallet balance was already known.
        balance_sats = sum(int(row.get("balance_sats") or 0) for row in rows)
        async with _ElectrumRPCClient(self, source) as client:
            meta = [(row, _electrum_scripthash(str(row.get("address") or ""))) for row in rows]
            # Normally the current balance is already present from Sentinel's
            # lightweight poll. Only fill it here when a fresh runtime row has
            # not completed its baseline yet; never re-query every address just
            # because the user opened historical TX.
            missing_balance_meta = [(row, scripthash) for row, scripthash in meta if not bool(row.get("baseline_complete"))]
            if missing_balance_meta:
                missing_balances, balance_warnings = await self._electrum_overview_calls_resilient(
                    client,
                    [("blockchain.scripthash.get_balance", [scripthash]) for _row, scripthash in missing_balance_meta],
                    label="Balance",
                )
                warnings.extend(balance_warnings)
                for (row, _scripthash), balance in zip(missing_balance_meta, missing_balances):
                    if isinstance(balance, dict):
                        row["balance_sats"] = int(balance.get("confirmed") or 0) + int(balance.get("unconfirmed") or 0)
                balance_sats = sum(int(row.get("balance_sats") or 0) for row in rows)
            history_results, history_warnings = await self._electrum_overview_calls_resilient(
                client,
                [("blockchain.scripthash.get_history", [scripthash]) for _row, scripthash in meta],
                label="History",
            )
            warnings.extend(history_warnings)
            history_by_txid: dict[str, int] = {}
            for (row, _scripthash), history in zip(meta, history_results):
                if history is None:
                    continue
                if not isinstance(history, list):
                    warnings.append(f"Wallet {row.get('monitor_slot', '?')}: invalid Electrum history response")
                    continue
                for item in history:
                    if not isinstance(item, dict):
                        continue
                    txid = str(item.get("tx_hash") or "").lower()
                    if not re.fullmatch(r"[0-9a-f]{64}", txid):
                        continue
                    height = int(item.get("height") or 0)
                    previous = history_by_txid.get(txid)
                    if previous is None or (height > 0 and (previous <= 0 or height > previous)):
                        history_by_txid[txid] = height

            ordered_all = sorted(
                history_by_txid.items(),
                key=lambda item: (1 if int(item[1]) <= 0 else 0, int(item[1]) if int(item[1]) > 0 else 2**31),
                reverse=True,
            )
            unlimited = int(limit) == 0
            page = max(1, int(page or 1))
            if unlimited:
                start = (page - 1) * TX_OVERVIEW_PAGE_SIZE
                ordered = ordered_all[start:start + TX_OVERVIEW_PAGE_SIZE]
            else:
                ordered = ordered_all[:limit]
            txids = [txid for txid, _height in ordered]
            raw_results, raw_warnings = await self._electrum_overview_calls_resilient(
                client,
                [("blockchain.transaction.get", [txid, False]) for txid in txids],
                label="Transaction",
            )
            warnings.extend(raw_warnings)
            parsed_by_txid: dict[str, dict[str, Any]] = {}
            for txid, raw in zip(txids, raw_results):
                if isinstance(raw, str):
                    parsed_by_txid[txid] = _parse_raw_transaction(raw)

            watched_scripts = {_address_scriptpubkey(address) for address in watched_addresses}
            prev_txids: list[str] = []
            for txid, tx in parsed_by_txid.items():
                tx_inputs = [
                    str(txin.get("txid") or "")
                    for txin in tx.get("inputs", [])
                    if str(txin.get("txid") or "") and str(txin.get("txid") or "") != "0" * 64
                ]
                receives_to_wallet = any(output.get("script") in watched_scripts for output in tx.get("outputs", []))
                if receives_to_wallet and len(tx_inputs) > TX_OVERVIEW_MAX_PREVOUT_TXS_PER_TRANSACTION:
                    warnings.append(
                        f"Transaction {txid[:12]}… has {len(tx_inputs)} inputs; prevout expansion skipped "
                        "to protect Fulcrum/Bitcoin Core. Incoming amount remains available; sender/fee detail may be incomplete."
                    )
                    continue
                prev_txids.extend(tx_inputs)
            prev_txids = list(dict.fromkeys(prev_txids))
            prev_by_txid: dict[str, dict[str, Any]] = {}
            if prev_txids:
                prev_raw, prev_warnings = await self._electrum_overview_calls_resilient(
                    client,
                    [("blockchain.transaction.get", [txid, False]) for txid in prev_txids],
                    label="Previous transaction",
                )
                warnings.extend(prev_warnings)
                for txid, raw in zip(prev_txids, prev_raw):
                    if isinstance(raw, str):
                        prev_by_txid[txid] = _parse_raw_transaction(raw)

            heights = sorted({int(height) for _txid, height in ordered if int(height) > 0})
            block_times: dict[int, int] = {}
            if heights:
                headers, header_warnings = await self._electrum_overview_calls_resilient(
                    client,
                    [("blockchain.block.header", [height]) for height in heights],
                    label="Block header",
                )
                warnings.extend(header_warnings)
                for height, header in zip(heights, headers):
                    stamp = _electrum_header_time(header)
                    if stamp:
                        block_times[height] = stamp

            transactions: list[dict[str, Any]] = []
            for txid, height in ordered:
                parsed = parsed_by_txid.get(txid)
                if not parsed:
                    continue
                event = _monitor_event_from_parsed(
                    txid, parsed, prev_by_txid, watched_addresses, int(height), block_times.get(int(height))
                )
                if event.get("spent_sats") or event.get("received_sats"):
                    transactions.append(event)

        # Avoid flooding the UI with the same timeout text for many inputs.
        warnings = list(dict.fromkeys(warnings))
        return self._finalize_monitor_overview(
            config=config, monitor=monitor, source=source, rows=rows, transactions=transactions,
            balance_sats=balance_sats, known_transaction_count=len(history_by_txid), warnings=warnings,
            page=page, unlimited=unlimited,
            has_more=(page * TX_OVERVIEW_PAGE_SIZE < len(history_by_txid)) if unlimited else False,
        )

    async def _monitor_overview_mempool(
        self,
        *,
        config: dict[str, Any],
        monitor: dict[str, Any],
        source: dict[str, Any],
        rows: list[dict[str, Any]],
        limit: int,
        page: int = 1,
    ) -> dict[str, Any]:
        watched_addresses = {str(row.get("address") or "") for row in rows if str(row.get("address") or "")}
        tx_by_id: dict[str, dict[str, Any]] = {}
        balance_sats = 0
        warnings: list[str] = []
        first_pages: dict[str, list[dict[str, Any]]] = {}
        semaphore = asyncio.Semaphore(4)

        async def first_page(row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | Exception]:
            async with semaphore:
                try:
                    return row, await self._address_snapshot(source, str(row.get("address") or ""), True)
                except Exception as err:  # keep other derived addresses usable
                    return row, err

        results = await asyncio.gather(*(first_page(row) for row in rows))
        for row, result in results:
            if isinstance(result, Exception):
                warnings.append(f"Wallet {row.get('monitor_slot', '?')}: {type(result).__name__}: {result}")
                continue
            summary = result.get("summary") if isinstance(result, dict) else None
            txs = result.get("txs") if isinstance(result, dict) else None
            if not isinstance(summary, dict) or not isinstance(txs, list):
                warnings.append(f"Wallet {row.get('monitor_slot', '?')}: invalid mempool overview response")
                continue
            current_balance = _balance_sats(summary)
            row["balance_sats"] = current_balance
            row["utxo_count"] = int(result.get("utxo_count") or 0)
            balance_sats += current_balance
            address = str(row.get("address") or "")
            normalized = [tx for tx in txs if isinstance(tx, dict) and re.fullmatch(r"[0-9a-fA-F]{64}", str(tx.get("txid") or ""))]
            first_pages[address] = normalized
            for tx in normalized:
                tx_by_id[str(tx.get("txid") or "").lower()] = tx

        unlimited = int(limit) == 0
        page = max(1, int(page or 1))
        target_count = page * TX_OVERVIEW_PAGE_SIZE if unlimited else int(limit)
        cursors: dict[str, str] = {}
        # A single heavily reused address can need Esplora chain pagination.
        # In unlimited mode we only walk far enough to fill the requested page;
        # the browser never asks Core to materialize the entire history at once.
        if len(tx_by_id) < target_count:
            for address, first_page_rows in first_pages.items():
                confirmed = [tx for tx in first_page_rows if bool((tx.get("status") or {}).get("confirmed"))]
                if len(confirmed) >= 25:
                    cursors[address] = str(confirmed[-1].get("txid") or "")
            rounds = 0
            while cursors and len(tx_by_id) < target_count:
                rounds += 1
                next_cursors: dict[str, str] = {}
                for address, cursor in list(cursors.items()):
                    try:
                        page = await self._address_api_json(source, address, f"/txs/chain/{quote(cursor, safe='')}")
                    except Exception as err:
                        warnings.append(f"{address[:12]}… history: {type(err).__name__}: {err}")
                        continue
                    if not isinstance(page, list):
                        continue
                    normalized = [tx for tx in page if isinstance(tx, dict) and re.fullmatch(r"[0-9a-fA-F]{64}", str(tx.get("txid") or ""))]
                    for tx in normalized:
                        tx_by_id[str(tx.get("txid") or "").lower()] = tx
                    if len(normalized) >= 25:
                        next_cursors[address] = str(normalized[-1].get("txid") or "")
                    if len(tx_by_id) >= target_count:
                        break
                cursors = next_cursors

        def tx_sort_key(tx: dict[str, Any]) -> tuple[int, int, int]:
            status = tx.get("status") if isinstance(tx.get("status"), dict) else {}
            confirmed = bool(status.get("confirmed"))
            return (1 if not confirmed else 0, int(status.get("block_time") or 0), int(status.get("block_height") or 0))

        ordered_txs = sorted(tx_by_id.values(), key=tx_sort_key, reverse=True)
        if unlimited:
            start = (page - 1) * TX_OVERVIEW_PAGE_SIZE
            selected = ordered_txs[start:start + TX_OVERVIEW_PAGE_SIZE]
        else:
            selected = ordered_txs[:limit]
        transactions = [
            _monitor_event_from_esplora(tx, watched_addresses) for tx in selected
        ]
        transactions = [tx for tx in transactions if tx.get("spent_sats") or tx.get("received_sats")]
        return self._finalize_monitor_overview(
            config=config, monitor=monitor, source=source, rows=rows, transactions=transactions,
            balance_sats=balance_sats, known_transaction_count=len(tx_by_id), warnings=warnings,
            page=page, unlimited=unlimited,
            has_more=(bool(cursors) or len(ordered_txs) > page * TX_OVERVIEW_PAGE_SIZE) if unlimited else False,
        )

    async def async_monitor_transactions(
        self, config: dict[str, Any], *, monitor_id: str, limit: int | None = None, page: int = 1
    ) -> dict[str, Any]:
        """Load a non-alerting historical transaction overview for one monitor.

        The selected Sentinel source is used exactly as configured. There is no
        provider fallback, and inspecting historical transactions never mutates
        the alert baseline, journal or notification state.
        """
        monitor = next((item for item in config.get("monitors", []) if str(item.get("id") or "") == str(monitor_id or "")), None)
        if not isinstance(monitor, dict):
            raise ValueError("Sats Sentinel watch entry was not found")
        configured_limit = int(monitor.get("history_limit", DEFAULT_TX_OVERVIEW_LIMIT))
        requested_limit = configured_limit if limit is None else int(limit)
        safe_limit = requested_limit if requested_limit in ALLOWED_TX_OVERVIEW_LIMITS else configured_limit
        if safe_limit not in ALLOWED_TX_OVERVIEW_LIMITS:
            safe_limit = DEFAULT_TX_OVERVIEW_LIMIT
        rows = [
            row for row in self.runtime_store.data.get("addresses", [])
            if isinstance(row, dict)
            and str(row.get("monitor_id") or "") == str(monitor_id or "")
            and bool(row.get("active", True))
        ]
        if not rows:
            raise ValueError("Sats Sentinel watch entry has no derived runtime addresses; save the watch configuration first")
        source = _select_watch_source(self.entry, config)
        if source is None:
            raise ValueError("No Sats Sentinel data source is available for this watch entry")
        if str(source.get("watch_source_type") or "mempool") == "electrum":
            return await self._monitor_overview_electrum(
                config=config, monitor=monitor, source=source, rows=rows, limit=safe_limit, page=page
            )
        return await self._monitor_overview_mempool(
            config=config, monitor=monitor, source=source, rows=rows, limit=safe_limit, page=page
        )

    def _notification_amount_sats(self, event: dict[str, Any]) -> int:
        if event.get("amount_sats") is not None:
            return max(0, int(event.get("amount_sats") or 0))
        if str(event.get("direction") or "") == "outgoing":
            return max(0, int(event.get("spent_sats") or 0) - int(event.get("received_sats") or 0))
        return max(0, int(event.get("received_sats") or 0))

    async def _append_activity_log(self, row: dict[str, Any], event: dict[str, Any]) -> None:
        """Persist every detected movement before any per-monitor alert filtering."""
        if event.get("simulated"):
            return
        txid = str(event.get("txid") or "")
        monitor_id = str(row.get("monitor_id") or "")
        if not txid or not monitor_id:
            return
        log = [item for item in self.runtime_store.data.get("activity_log", []) if isinstance(item, dict)]
        key = f"{monitor_id}:{txid}"
        existing = next((item for item in log if str(item.get("key") or "") == key), None)
        record = {
            "key": key,
            "monitor_id": monitor_id,
            "category": str(row.get("category") or "other"),
            "txid": txid,
            "direction": str(event.get("direction") or "activity"),
            "amount_sats": self._notification_amount_sats(event),
            "net_sats": int(event.get("net_sats") or 0),
            "confirmed": bool(event.get("confirmed")),
            "rbf": bool(event.get("rbf")),
            "block_height": event.get("block_height"),
            "block_time": event.get("block_time"),
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "counterparties": [
                {"address": str(item.get("address") or ""), "value_sats": int(item.get("value_sats") or 0)}
                for item in (event.get("counterparties") or [])[:12]
                if isinstance(item, dict) and str(item.get("address") or "")
            ],
            "watched_addresses": [
                str(address)
                for address in dict.fromkeys(event.get("watched_addresses") or [row.get("address")])
                if str(address or "")
            ][:12],
        }
        if existing is None:
            log.append(record)
        else:
            # Keep the original detection time while allowing confirmation/RBF and
            # counterparty metadata to become more complete on later observations.
            record["detected_at"] = existing.get("detected_at") or record["detected_at"]
            existing.clear()
            existing.update(record)
        if len(log) > MAX_STORED_ACTIVITY_LOG:
            log.sort(key=lambda item: str(item.get("detected_at") or ""))
            dropped = len(log) - MAX_STORED_ACTIVITY_LOG
            log = log[-MAX_STORED_ACTIVITY_LOG:]
            self.runtime_store.data["activity_log_trimmed_total"] = int(
                self.runtime_store.data.get("activity_log_trimmed_total") or 0
            ) + dropped
        self.runtime_store.data["activity_log"] = log

    def public_activity_log(
        self, config: dict[str, Any], *, page: int = 1, category: str = "all", page_size: int = DEFAULT_LOG_PAGE_SIZE
    ) -> dict[str, Any]:
        """Return the owner-visible journal with display filtering but no deletion."""
        monitors = {str(item.get("id") or ""): item for item in config.get("monitors", []) if isinstance(item, dict)}
        runtime_addresses = [row for row in self.runtime_store.data.get("addresses", []) if isinstance(row, dict)]
        address_owner: dict[str, str] = {}
        monitor_runtime_addresses: dict[str, list[str]] = {}
        for address_row in runtime_addresses:
            address = str(address_row.get("address") or "")
            monitor_id = str(address_row.get("monitor_id") or "")
            if not address or not monitor_id:
                continue
            address_owner[address] = monitor_id
            monitor_runtime_addresses.setdefault(monitor_id, []).append(address)
        rows = [dict(item) for item in self.runtime_store.data.get("activity_log", []) if isinstance(item, dict)]
        rows.sort(key=lambda item: str(item.get("detected_at") or ""), reverse=True)
        mode = str(config.get("log_display_mode") or "days")
        if mode == "count":
            rows = rows[: max(1, int(config.get("log_display_count") or 100))]
        elif mode == "days":
            cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(config.get("log_display_days") or 30)))
            filtered = []
            for item in rows:
                try:
                    stamp = datetime.fromisoformat(str(item.get("detected_at") or "").replace("Z", "+00:00"))
                except ValueError:
                    continue
                if stamp >= cutoff:
                    filtered.append(item)
            rows = filtered
        selected_category = str(category or "all").lower()
        enriched = []
        for item in rows:
            monitor = monitors.get(str(item.get("monitor_id") or ""), {})
            current_category = str(monitor.get("category") or item.get("category") or "other")
            if selected_category != "all" and current_category != selected_category:
                continue
            counterparties = []
            for entry in item.get("counterparties", []):
                if not isinstance(entry, dict):
                    continue
                cp = dict(entry)
                cp_address = str(cp.get("address") or "")
                cp_monitor_id = address_owner.get(cp_address, "")
                cp_monitor = monitors.get(cp_monitor_id, {}) if cp_monitor_id else {}
                if cp_monitor:
                    cp["monitor_id"] = cp_monitor_id
                    cp["monitor_label"] = str(cp_monitor.get("label") or cp_monitor_id or "Wallet")
                    cp["category"] = str(cp_monitor.get("category") or "other")
                counterparties.append(cp)
            watched_addresses = [
                str(address) for address in (item.get("watched_addresses") or []) if str(address or "")
            ]
            if not watched_addresses:
                if str(monitor.get("kind") or "") == "address" and str(monitor.get("value") or ""):
                    watched_addresses = [str(monitor.get("value"))]
                else:
                    legacy_addresses = list(dict.fromkeys(monitor_runtime_addresses.get(str(item.get("monitor_id") or ""), [])))
                    watched_addresses = legacy_addresses if len(legacy_addresses) == 1 else []
            enriched.append({
                **item,
                "category": current_category,
                "monitor_label": str(monitor.get("label") or item.get("monitor_id") or "Wallet"),
                "monitor_kind": str(monitor.get("kind") or "address"),
                "watched_addresses": list(dict.fromkeys(watched_addresses))[:12],
                "counterparties": counterparties[:12],
            })
        total = len(enriched)
        requested_page_size = int(page_size or DEFAULT_LOG_PAGE_SIZE)
        safe_page_size = min(LOG_PAGE_SIZE, max(1, requested_page_size))
        pages = max(1, (total + safe_page_size - 1) // safe_page_size)
        safe_page = max(1, min(int(page or 1), pages))
        start = (safe_page - 1) * safe_page_size
        explorer_source = _explorer_mempool_source(self.entry, bool(config.get("allow_public_tor")))
        explorer_base_url = ""
        if explorer_source:
            explorer_base_url = _canonical_mempool_base_url(explorer_source.get(CONF_BASE_URL))
        return {
            "items": enriched[start:start + safe_page_size],
            "page": safe_page,
            "page_size": safe_page_size,
            "pages": pages,
            "total": total,
            "stored_total": len(self.runtime_store.data.get("activity_log", []) or []),
            "stored_limit": MAX_STORED_ACTIVITY_LOG,
            "trimmed_total": int(self.runtime_store.data.get("activity_log_trimmed_total") or 0),
            "display_mode": mode,
            "explorer_base_url": explorer_base_url,
        }

    def _notification_text(self, row: dict[str, Any], event: dict[str, Any], detail: str) -> tuple[str, str, dict[str, Any]]:
        """Render a push message and the matching privacy-scoped webhook payload."""
        mode = detail if detail in {"discreet", "normal", "detailed"} else "discreet"
        direction = str(event.get("direction") or "activity")
        direction_label = "Ausgang" if direction == "outgoing" else "Eingang"
        simulated = bool(event.get("simulated"))
        event_name = "wallet_activity_test" if simulated else "wallet_activity"
        if mode == "discreet":
            # BlueWallet-style private push: no direction, amount, txid, address,
            # monitor id or confirmation data leaves the trusted server.
            return (
                "🧪 Sats Sentinel Test" if simulated else "🛡️ Sats Sentinel",
                "TEST: Simulierte Bitcoin-Bewegung erkannt. Keine Blockchain-Daten wurden verändert." if simulated else "Bitcoin-Bewegung erkannt. Öffne Bitcoin Stack Tracker für Details.",
                {"event": "wallet_activity_test", "simulated": True} if simulated else {"event": "wallet_activity"},
            )

        amount = (
            self._notification_amount_sats(event)
        )
        title = f"🧪 Sats Sentinel Test · {direction_label}" if simulated else f"🚨 Sats Sentinel · {direction_label} erkannt"
        if mode == "normal":
            amount_label = "Netto-Abgang" if direction == "outgoing" else "Eingang"
            message = (
                f"Wallet #{row.get('monitor_slot', '?')} · {amount_label} {amount:,} sats · "
                f"{'bestätigt' if event.get('confirmed') else 'unbestätigt'}"
            ).replace(",", ".")
            return title, message, {
                "event": event_name,
                "simulated": simulated,
                "direction": direction,
                "amount_sats": amount,
                "confirmed": bool(event.get("confirmed")),
            }

        txid = str(event.get("txid") or "")
        message = (
            f"Wallet #{row.get('monitor_slot', '?')} · Netto {event.get('net_sats', 0):,} sats · "
            f"Inputs {event.get('spent_sats', 0):,} · Outputs zurück {event.get('received_sats', 0):,} · "
            f"{'bestätigt' if event.get('confirmed') else 'unbestätigt'} · "
            f"RBF {'ja' if event.get('rbf') else 'nein'} · TX {txid[:12]}…"
        ).replace(",", ".")
        return title, message, {
            "event": event_name,
            "simulated": simulated,
            "monitor_id": row.get("monitor_id"),
            "direction": direction,
            "spent_sats": int(event.get("spent_sats") or 0),
            "received_sats": int(event.get("received_sats") or 0),
            "net_sats": int(event.get("net_sats") or 0),
            "confirmed": bool(event.get("confirmed")),
            "rbf": bool(event.get("rbf")),
            "txid": txid,
        }

    async def _send_external_target(
        self,
        target: dict[str, Any],
        *,
        title: str,
        message: str,
        payload: dict[str, Any],
        priority: str = "high",
    ) -> None:
        """Send one ntfy/webhook notification with local-direct-or-Tor-only routing."""
        url = str(target.get("url") or "")
        local_direct = is_private_or_local_url(url) and not is_onion_url(url)
        settings = effective_settings(self.entry)
        proxy = None if local_direct else tor_proxy_from_settings(settings)
        headers: dict[str, str] = {
            "User-Agent": "Bitcoin-Stack-Tracker/0.21.0.15",
        }
        token = str(target.get("token") or "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        kind = str(target.get("kind") or "")

        async with async_routed_session(
            self.hass,
            target_url=url,
            proxy_url=proxy,
            allow_local_direct=local_direct,
            verify_ssl=bool(target.get("verify_ssl", True)),
        ) as (session, kwargs):
            async with asyncio.timeout(15):
                if kind == "ntfy":
                    headers.update({
                        "Title": title,
                        "Priority": "urgent" if priority == "urgent" else "high",
                        "Tags": "bitcoin,warning" if priority == "urgent" else "bitcoin",
                        "Content-Type": "text/plain; charset=utf-8",
                    })
                    response = await session.post(url, data=message.encode("utf-8"), headers=headers, **kwargs)
                elif kind == "webhook":
                    headers["Content-Type"] = "application/json"
                    body = {
                        "source": "bitcoin_stack_tracker",
                        "title": title,
                        "message": message,
                        **payload,
                    }
                    response = await session.post(
                        url,
                        data=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                        headers=headers,
                        **kwargs,
                    )
                else:
                    raise ValueError("Unsupported notification target type")
                if response.status < 200 or response.status >= 300:
                    # Do not include response bodies or target URLs in errors; both can contain secrets.
                    raise ValueError(f"Notification target returned HTTP {response.status}")
                response.release()

    async def _dispatch_external(
        self,
        *,
        row: dict[str, Any] | None,
        event: dict[str, Any] | None,
        outage_message: str | None = None,
        test: bool = False,
    ) -> list[dict[str, Any]]:
        """Fan out to every enabled external target; one target cannot block the others."""
        targets = [
            item for item in self.runtime_store.data.get("notification_targets", [])
            if isinstance(item, dict) and item.get("enabled", True)
        ]
        results: list[dict[str, Any]] = []

        async def send_one(target: dict[str, Any]) -> dict[str, Any]:
            # Wallet-level detail is authoritative for wallet activity. The
            # server setting is only the default copied into newly created
            # monitors. External targets never override an individual wallet.
            detail = (
                str(row.get("notification_detail") or self.runtime_store.data.get("notification_detail") or "discreet")
                if row is not None and event is not None
                else str(self.runtime_store.data.get("notification_detail") or "discreet")
            )
            if test:
                title = "✅ Sats Sentinel Test"
                message = "Testbenachrichtigung erfolgreich ausgelöst. Es wurden keine Walletdaten übertragen."
                payload = {"event": "wallet_watch_test"}
                priority = "high"
            elif outage_message is not None:
                title = "⚠️ Sats Sentinel offline"
                message = "Wallet-Überwachung derzeit nicht möglich. Kein Clearnet-Fallback wurde verwendet."
                if detail != "discreet":
                    message = outage_message
                payload = {"event": "wallet_watch_offline"}
                priority = "urgent"
            else:
                assert row is not None and event is not None
                title, message, payload = self._notification_text(row, event, detail)
                priority = "urgent" if str(event.get("direction")) == "outgoing" else "high"
            try:
                await self._send_external_target(
                    target,
                    title=title,
                    message=message,
                    payload=payload,
                    priority=priority,
                )
                return {"id": target.get("id"), "kind": target.get("kind"), "ok": True}
            except Exception as err:  # isolated provider failure
                return {
                    "id": target.get("id"),
                    "kind": target.get("kind"),
                    "ok": False,
                    "error": f"{type(err).__name__}: {err}"[:240],
                }

        if targets:
            results = list(await asyncio.gather(*(send_one(target) for target in targets)))
            failures = [result for result in results if not result.get("ok")]
            self.runtime_store.data["last_notification_error"] = failures[0].get("error") if failures else None
            self.runtime_store.data["notification_delivery_failures"] = int(
                self.runtime_store.data.get("notification_delivery_failures") or 0
            ) + len(failures)
            if not failures:
                self.runtime_store.data["last_notification_success_at"] = datetime.now(timezone.utc).isoformat()
        return results

    async def _notify_activity(self, row: dict[str, Any], event: dict[str, Any]) -> None:
        if event["direction"] == "incoming" and not row.get("notify_incoming", True):
            return
        if event["direction"] == "outgoing" and not row.get("notify_outgoing", True):
            return
        amount = self._notification_amount_sats(event)
        if amount < int(row.get("min_notify_sats") or 0):
            return
        now = datetime.now(timezone.utc).isoformat()
        minimal = {
            "config_entry_id": self.entry.entry_id,
            "monitor_id": row.get("monitor_id"),
            "direction": event["direction"],
            "amount_sats": amount,
            "confirmed": event.get("confirmed"),
            "simulated": bool(event.get("simulated")),
            "detected_at": now,
        }
        if row.get("notify_ha_event", True):
            self.hass.bus.async_fire(WATCH_TEST_EVENT if event.get("simulated") else WATCH_EVENT, minimal)

        detail = str(row.get("notification_detail") or self.runtime_store.data.get("notification_detail") or "discreet")
        title, message, _payload = self._notification_text(row, event, detail)
        if self.runtime_store.data.get("persistent_notification", True) and row.get("notify_persistent", True):
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {"title": title, "message": message, "notification_id": f"bst_wallet_watch_{row.get('monitor_id')}_{event.get('txid','')[:16]}"},
                blocking=False,
            )
        if row.get("notify_services", True):
            available = self.hass.services.async_services().get("notify", {})
            for service in self.runtime_store.data.get("notification_services", []):
                if service in available:
                    service_message = message
                    if event.get("simulated"):
                        service_message = f"{message}\n\nTEST-Ziel: notify.{service}"
                    await self.hass.services.async_call("notify", service, {"title": title, "message": service_message}, blocking=False)
        if row.get("notify_external", True):
            await self._dispatch_external(row=row, event=event)

    async def _notify_outage(self, message: str) -> None:
        self.hass.bus.async_fire(WATCH_STATUS_EVENT, {
            "config_entry_id": self.entry.entry_id, "status": "offline", "detected_at": datetime.now(timezone.utc).isoformat()
        })
        local_message = message
        if self.runtime_store.data.get("persistent_notification", True):
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {"title": "⚠️ Sats Sentinel offline", "message": local_message, "notification_id": f"bst_wallet_watch_offline_{self.entry.entry_id}"},
                blocking=False,
            )
        available = self.hass.services.async_services().get("notify", {})
        for service in self.runtime_store.data.get("notification_services", []):
            if service in available:
                await self.hass.services.async_call("notify", service, {"title": "⚠️ Sats Sentinel offline", "message": local_message}, blocking=False)
        await self._dispatch_external(row=None, event=None, outage_message=message)

    async def async_simulate_activity(
        self,
        *,
        monitor_id: str = "",
        direction: str = "outgoing",
        amount_sats: int = 100_000,
        confirmed: bool = False,
        rbf: bool = False,
    ) -> dict[str, Any]:
        """Run a non-mutating wallet-activity simulation through the real alert path."""
        direction = str(direction or "outgoing").lower()
        if direction not in {"incoming", "outgoing"}:
            raise ValueError("Simulation direction must be incoming or outgoing")
        amount = int(amount_sats)
        if amount < 1 or amount > 2_100_000_000_000_000:
            raise ValueError("Simulation amount is outside the valid satoshi range")

        addresses = [row for row in self.runtime_store.data.get("addresses", []) if isinstance(row, dict)]
        row = next((item for item in addresses if str(item.get("monitor_id") or "") == str(monitor_id or "")), None)
        if row is None and addresses and not monitor_id:
            row = addresses[0]
        if row is None:
            # This synthetic row contains no address or wallet material; it exists only
            # so notification routing can be tested before a real monitor is added.
            row = {
                "monitor_id": "simulation",
                "monitor_slot": "TEST",
                "notify_incoming": True,
                "notify_outgoing": True,
            }
        if direction == "incoming" and not row.get("notify_incoming", True):
            raise ValueError("Incoming notifications are disabled for the selected monitor")
        if direction == "outgoing" and not row.get("notify_outgoing", True):
            raise ValueError("Outgoing notifications are disabled for the selected monitor")
        event = {
            "txid": f"simulation-{os.urandom(8).hex()}",
            "direction": direction,
            "spent_sats": amount if direction == "outgoing" else 0,
            "received_sats": amount if direction == "incoming" else 0,
            "net_sats": -amount if direction == "outgoing" else amount,
            "confirmed": bool(confirmed),
            "block_height": None,
            "block_time": None,
            "rbf": bool(rbf),
            "simulated": True,
        }
        await self._notify_activity(row, event)
        return {
            "ok": True,
            "simulated": True,
            "monitor_id": row.get("monitor_id"),
            "direction": direction,
            "amount_sats": amount,
            "confirmed": bool(confirmed),
            "rbf": bool(rbf),
        }

    async def async_live_test_transaction(self, *, txid: str, direction: str = "outgoing") -> dict[str, Any]:
        """Parse one real public transaction through an allowed mempool route, then emit a TEST alert."""
        txid = str(txid or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", txid):
            raise ValueError("Live test requires a 64-character Bitcoin transaction ID")
        direction = str(direction or "outgoing").lower()
        if direction not in {"incoming", "outgoing"}:
            raise ValueError("Live-test direction must be incoming or outgoing")
        sources = _mempool_sources(self.entry, bool(self.runtime_store.data.get("allow_public_tor")))
        if not sources:
            raise ValueError("No Sats Sentinel mempool source is available. Configure an own/custom mempool source, or configure a public mempool source and explicitly allow it through Tor.")
        tx: dict[str, Any] | None = None
        last_error: Exception | None = None
        for source in sources:
            try:
                candidate = await self._request_json(source, f"/api/tx/{txid}")
                if isinstance(candidate, dict) and str(candidate.get("txid") or "").lower() == txid:
                    tx = candidate
                    break
            except Exception as err:
                last_error = err
        if tx is None:
            raise ValueError(f"Transaction could not be loaded through an allowed source: {type(last_error).__name__ if last_error else 'not found'}")

        address = ""
        if direction == "outgoing":
            for vin in tx.get("vin", []):
                prevout = vin.get("prevout") if isinstance(vin, dict) and isinstance(vin.get("prevout"), dict) else {}
                candidate = str(prevout.get("scriptpubkey_address") or "")
                if candidate:
                    address = candidate
                    break
        else:
            for vout in tx.get("vout", []):
                candidate = str(vout.get("scriptpubkey_address") or "") if isinstance(vout, dict) else ""
                if candidate:
                    address = candidate
                    break
        if not address:
            raise ValueError("Transaction has no standard address suitable for the selected live-test perspective")
        event = _tx_activity(tx, address)
        if direction == "outgoing" and int(event.get("spent_sats") or 0) <= 0:
            raise ValueError("Could not derive an outgoing amount from the selected transaction")
        if direction == "incoming" and int(event.get("received_sats") or 0) <= 0:
            raise ValueError("Could not derive an incoming amount from the selected transaction")
        event["direction"] = direction
        event["simulated"] = True
        amount = (
            max(0, int(event.get("spent_sats") or 0) - int(event.get("received_sats") or 0))
            if direction == "outgoing" else int(event.get("received_sats") or 0)
        )
        row = {
            "monitor_id": "live-test",
            "monitor_slot": "TEST",
            "notify_incoming": True,
            "notify_outgoing": True,
        }
        await self._notify_activity(row, event)
        return {
            "ok": True,
            "simulated": True,
            "live_transaction": True,
            "direction": direction,
            "amount_sats": amount,
            "confirmed": bool(event.get("confirmed")),
            "rbf": bool(event.get("rbf")),
            "txid": txid,
        }

    async def async_test_notifications(self) -> dict[str, Any]:
        """Send a privacy-safe test to all configured notification channels."""
        title = "✅ Sats Sentinel Test"
        message = "Testbenachrichtigung erfolgreich ausgelöst. Es wurden keine Walletdaten übertragen."
        delivered: list[str] = []
        errors: list[str] = []
        if self.runtime_store.data.get("persistent_notification", True):
            try:
                await self.hass.services.async_call(
                    "persistent_notification", "create",
                    {"title": title, "message": message, "notification_id": f"bst_wallet_watch_test_{self.entry.entry_id}"},
                    blocking=False,
                )
                delivered.append("persistent_notification")
            except Exception as err:
                errors.append(f"persistent_notification: {type(err).__name__}")
        available = self.hass.services.async_services().get("notify", {})
        for service in self.runtime_store.data.get("notification_services", []):
            if service not in available:
                errors.append(f"notify.{service}: unavailable")
                continue
            try:
                service_message = f"{message}\n\nZiel: notify.{service}"
                await self.hass.services.async_call("notify", service, {"title": title, "message": service_message}, blocking=False)
                delivered.append(f"notify.{service}")
            except Exception as err:
                errors.append(f"notify.{service}: {type(err).__name__}")
        external = await self._dispatch_external(row=None, event=None, test=True)
        for result in external:
            label = f"{result.get('kind')}.{result.get('id')}"
            if result.get("ok"):
                delivered.append(label)
            else:
                errors.append(f"{label}: {result.get('error')}")
        await self.runtime_store.async_save()
        return {"ok": not errors, "delivered": delivered, "errors": errors}

    async def async_poll(self, *, force: bool = False) -> dict[str, Any]:
        del force
        if self._lock.locked():
            return self.public_status()
        async with self._lock:
            self._last_poll_monotonic = asyncio.get_running_loop().time()
            data = self.runtime_store.data
            if not data.get("enabled"):
                return self.public_status()
            addresses = [
                row for row in data.get("addresses", [])
                if isinstance(row, dict) and bool(row.get("active", True))
            ]
            if not addresses:
                data["last_error"] = "Sats Sentinel is enabled but no addresses are configured"
                data["last_warning"] = None
                data["partial_failures"] = 0
                await self._async_save_runtime_if_due()
                return self.public_status()
            source_used = _select_watch_source(self.entry, data)
            if source_used is None:
                mode = str(data.get("query_source") or "auto")
                data["last_error"] = (
                    f"No Sats Sentinel data source is available for selection '{mode}'. "
                    "Configure the selected Fulcrum/electrs endpoint, an own Mempool instance, "
                    "or explicitly allow a configured public Mempool source through Tor."
                )
                data["last_warning"] = None
                data["partial_failures"] = 0
                data["error_streak"] = int(data.get("error_streak") or 0) + 1
                if data["error_streak"] >= 3 and not data.get("outage_notified"):
                    data["outage_notified"] = True
                    await self._notify_outage(data["last_error"])
                await self._async_save_runtime_if_due(force=data["error_streak"] in {1, 3})
                return self.public_status()

            data["last_poll_at"] = datetime.now(timezone.utc).isoformat()
            activities: list[dict[str, Any]] = []
            partial_errors: list[str] = []
            source_type = str(source_used.get("watch_source_type") or "mempool")
            if source_type == "electrum":
                try:
                    activities, partial_errors = await self._poll_electrum_source(source_used, addresses)
                except Exception as err:
                    data["error_streak"] = int(data.get("error_streak") or 0) + 1
                    data["last_error"] = f"Sats Sentinel {source_used.get('label', 'Electrum')} source unavailable: {type(err).__name__}: {err}"[:500]
                    data["last_warning"] = None
                    data["partial_failures"] = 0
                    if data["error_streak"] >= 3 and not data.get("outage_notified"):
                        data["outage_notified"] = True
                        await self._notify_outage(
                            f"Sats Sentinel kann die explizit ausgewählte Quelle {source_used.get('label', 'Electrum')} nicht erreichen. Es gibt absichtlich keinen Provider-Fallback."
                        )
                    await self._async_save_runtime_if_due(force=data["error_streak"] in {1, 3})
                    return self.public_status()
            else:
                first_probe: dict[str, Any] | None = None
                try:
                    first_probe = await self._address_snapshot(source_used, addresses[0]["address"], False)
                except Exception as err:
                    last_error: Exception = err
                    # Same-node diagnosis only. This does not change provider,
                    # host, port or route and therefore preserves fail-closed.
                    try:
                        await self._request_json(source_used, "/api/v1/prices")
                    except Exception:
                        pass
                    else:
                        last_error = ValueError(
                            f"mempool is reachable, but its address API failed: {type(err).__name__}: {err}"
                        )
                    data["error_streak"] = int(data.get("error_streak") or 0) + 1
                    data["last_error"] = f"Sats Sentinel source unavailable: {type(last_error).__name__}: {last_error}"[:500]
                    data["last_warning"] = None
                    data["partial_failures"] = 0
                    if data["error_streak"] >= 3 and not data.get("outage_notified"):
                        data["outage_notified"] = True
                        await self._notify_outage("Sats Sentinel kann die explizit/automatisch ausgewählte Mempool-Datenquelle nicht erreichen. Es gibt absichtlich keinen Provider-Fallback.")
                    await self._async_save_runtime_if_due(force=data["error_streak"] in {1, 3})
                    return self.public_status()

                for row_index, row in enumerate(addresses):
                    address = str(row.get("address") or "")
                    monitor_slot = row.get("monitor_slot", "?")
                    try:
                        first = first_probe if row_index == 0 and first_probe is not None else await self._address_snapshot(source_used, address, False)
                    except Exception as err:
                        partial_errors.append(f"Wallet {monitor_slot}: summary {type(err).__name__}: {err}")
                        continue

                    row["used"] = _address_summary_used(first["summary"])
                    sig = _summary_signature(first["summary"])
                    changed = sig != row.get("summary_signature")
                    if changed or not row.get("baseline_complete"):
                        try:
                            detail = await self._address_snapshot(source_used, address, True)
                        except Exception as err:
                            row["balance_sats"] = _balance_sats(first["summary"])
                            row["utxo_count"] = int(first.get("utxo_count") or 0)
                            partial_errors.append(f"Wallet {monitor_slot}: txs {type(err).__name__}: {err}")
                            continue
                        txs = [tx for tx in detail["txs"] if isinstance(tx, dict) and tx.get("txid")]
                        txids = [str(tx["txid"]) for tx in txs]
                        known = set(str(x) for x in row.get("known_txids", []))
                        if row.get("baseline_complete"):
                            for tx in reversed(txs):
                                if str(tx.get("txid")) not in known:
                                    event = _tx_activity(tx, address)
                                    if event["spent_sats"] or event["received_sats"]:
                                        activities.append({"row": row, "event": event})
                                        row["last_activity_at"] = datetime.now(timezone.utc).isoformat()
                        row["known_txids"] = txids[:75]
                        row["summary_signature"] = sig
                        row["balance_sats"] = _balance_sats(detail["summary"])
                        row["utxo_count"] = int(detail.get("utxo_count") or 0)
                        row["baseline_complete"] = True
                    else:
                        row["balance_sats"] = _balance_sats(first["summary"])
                        row["utxo_count"] = int(first.get("utxo_count") or 0)

            try:
                gap_extended = await self._maintain_gap_from_standby(source_used)
            except Exception as err:
                partial_errors.append(f"Gap reserve: {type(err).__name__}: {err}")
                gap_extended = False
            if gap_extended:
                addresses = [
                    row for row in data.get("addresses", [])
                    if isinstance(row, dict) and bool(row.get("active", True))
                ]

            aggregated: dict[tuple[str, str], dict[str, Any]] = {}
            for activity in activities:
                row = activity["row"]
                event = activity["event"]
                key = (str(row.get("monitor_id") or ""), str(event.get("txid") or ""))
                current = aggregated.get(key)
                if current is None:
                    first_event = dict(event)
                    first_event["watched_addresses"] = [str(row.get("address") or "")] if str(row.get("address") or "") else []
                    aggregated[key] = {"row": row, "event": first_event}
                    continue
                merged = current["event"]
                merged["spent_sats"] = int(merged.get("spent_sats") or 0) + int(event.get("spent_sats") or 0)
                merged["received_sats"] = int(merged.get("received_sats") or 0) + int(event.get("received_sats") or 0)
                merged["net_sats"] = int(merged["received_sats"]) - int(merged["spent_sats"])
                merged["direction"] = "outgoing" if int(merged["spent_sats"]) > 0 else "incoming"
                merged["rbf"] = bool(merged.get("rbf") or event.get("rbf"))
                merged["confirmed"] = bool(merged.get("confirmed") and event.get("confirmed"))
                merged["input_candidates"] = list(merged.get("input_candidates") or []) + list(event.get("input_candidates") or [])
                merged["output_candidates"] = list(merged.get("output_candidates") or []) + list(event.get("output_candidates") or [])
                watched_addresses = list(merged.get("watched_addresses") or [])
                current_address = str(row.get("address") or "")
                if current_address and current_address not in watched_addresses:
                    watched_addresses.append(current_address)
                merged["watched_addresses"] = watched_addresses[:12]

            monitor_addresses: dict[str, set[str]] = {}
            for address_row in addresses:
                monitor_addresses.setdefault(str(address_row.get("monitor_id") or ""), set()).add(str(address_row.get("address") or ""))
            for activity in aggregated.values():
                row = activity["row"]
                event = activity["event"]
                own_set = monitor_addresses.get(str(row.get("monitor_id") or ""), set())
                candidates = event.get("output_candidates") if event.get("direction") == "outgoing" else event.get("input_candidates")
                combined: dict[str, int] = {}
                for candidate in candidates or []:
                    if not isinstance(candidate, dict):
                        continue
                    candidate_address = str(candidate.get("address") or "")
                    if not candidate_address or candidate_address in own_set:
                        continue
                    combined[candidate_address] = combined.get(candidate_address, 0) + int(candidate.get("value_sats") or 0)
                counterparties = [
                    {"address": address, "value_sats": value}
                    for address, value in sorted(combined.items(), key=lambda item: item[1], reverse=True)[:12]
                ]
                event["counterparties"] = counterparties
                if event.get("direction") == "outgoing":
                    external_amount = sum(int(item.get("value_sats") or 0) for item in counterparties)
                    event["amount_sats"] = external_amount if external_amount > 0 else max(0, -int(event.get("net_sats") or 0))
                else:
                    event["amount_sats"] = max(0, int(event.get("received_sats") or 0))
                await self._append_activity_log(row, event)
                await self._notify_activity(row, event)

            recovered = bool(data.get("outage_notified"))
            now_iso = datetime.now(timezone.utc).isoformat()
            data["last_error"] = None
            data["error_streak"] = 0
            data["outage_notified"] = False
            if partial_errors:
                data["last_warning"] = (
                    f"Sats Sentinel partial check: {len(partial_errors)} address request(s) incomplete; "
                    + " | ".join(partial_errors[:3])
                )[:700]
                data["partial_failures"] = len(partial_errors)
                data["last_partial_at"] = now_iso
            else:
                data["last_success_at"] = now_iso
                data["last_warning"] = None
                data["partial_failures"] = 0
                data["last_partial_at"] = None
            await self._async_save_runtime_if_due(
                force=bool(aggregated or gap_extended or recovered)
            )
            if recovered:
                self.hass.bus.async_fire(WATCH_STATUS_EVENT, {
                    "config_entry_id": self.entry.entry_id, "status": "online", "detected_at": data["last_success_at"]
                })
            return {**self.public_status(), "activity_count": len(aggregated)}
