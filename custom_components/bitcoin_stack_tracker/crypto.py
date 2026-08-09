"""Authenticated encryption for Bitcoin Stack Tracker vaults and backups.

Current local-vault format (v3) uses envelope encryption:

* Argon2id derives a 256-bit password key.
* A separate 256-bit Home Assistant Core device secret is mixed with that
  password key through HKDF-SHA-512 to derive a key-encryption key (KEK).
* A fresh random 256-bit data-encryption key (DEK) encrypts the ledger with
  AES-256-GCM.  The DEK is itself wrapped with AES-256-GCM under the KEK.
* The device secret is never stored in the ledger envelope and never belongs in
  the Tor/network add-on.  Copying only the encrypted ledger is therefore not
  enough for an offline password attack.

Portable backups cannot be device-bound because they must be restorable on a
new Home Assistant installation.  They still use a random DEK and an Argon2id
password-derived KEK.

Legacy scrypt-v1 and Argon2id-v2 envelopes remain readable and are migrated to
v3 after a successful unlock.
"""

from __future__ import annotations

import base64
from copy import deepcopy
import json
import os
from typing import Any

from argon2.exceptions import HashingError
from argon2.low_level import ARGON2_VERSION, Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

# Legacy names are AAD-bound and must never change.
PASSWORD_ENVELOPE_MODE_V1 = "password-scrypt-v1"
BACKUP_ENVELOPE_MODE_V1 = "portable-backup-scrypt-v1"
PASSWORD_ENVELOPE_MODE_V2 = "password-argon2id-v2"
BACKUP_ENVELOPE_MODE_V2 = "portable-backup-argon2id-v2"

# Current v3 envelope-encryption formats.
PASSWORD_ENVELOPE_MODE = "password-argon2id-envelope-v3"
BACKUP_ENVELOPE_MODE = "portable-backup-argon2id-envelope-v3"
PASSWORD_FORMAT = "AES-256-GCM"
KDF_ARGON2ID = "argon2id"
KDF_SCRYPT = "scrypt"
PASSWORD_KDF = KDF_ARGON2ID
PASSWORD_SCHEMA_VERSION = 3
BACKUP_SCHEMA_VERSION = 3

_KEY_BYTES = 32               # AES-256 / 256-bit DEK / 256-bit KEK
_NONCE_BYTES = 12             # 96-bit GCM IV recommended for GCM
_GCM_TAG_BITS = 128           # cryptography AESGCM uses a 128-bit tag
_SALT_BYTES = 32              # 256-bit random Argon2id salt
_DEVICE_SECRET_BYTES = 32     # 256-bit local second secret

# Deliberately stronger than OWASP's minimum, while still interactive on HAOS.
_ARGON2_MEMORY_KIB = 128 * 1024
_ARGON2_TIME_COST = 3
_ARGON2_PARALLELISM = 1
_ARGON2_VERSION = ARGON2_VERSION

_MIN_PASSWORD_LENGTH = 16
_MAX_PASSWORD_LENGTH = 1024


class PasswordValidationError(ValueError):
    """Raised when a new password does not meet requirements."""


class PasswordDecryptionError(ValueError):
    """Raised when a password/key is wrong or encrypted data is damaged."""


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value.encode("ascii"))
    except Exception as err:
        raise PasswordDecryptionError("Invalid base64 in encrypted data") from err


def validate_new_password(password: str) -> None:
    if not isinstance(password, str):
        raise PasswordValidationError("Password must be text")
    length = len(password)
    if length < _MIN_PASSWORD_LENGTH:
        raise PasswordValidationError(
            f"Use at least {_MIN_PASSWORD_LENGTH} characters for the password"
        )
    if length > _MAX_PASSWORD_LENGTH:
        raise PasswordValidationError("Password is too long")


def new_device_secret() -> bytes:
    """Return a fresh 256-bit device-binding secret."""
    return os.urandom(_DEVICE_SECRET_BYTES)


def _validate_device_secret(device_secret: bytes | bytearray | None) -> bytes:
    if not isinstance(device_secret, (bytes, bytearray)):
        raise PasswordDecryptionError("Home Assistant device-binding key is required")
    value = bytes(device_secret)
    if len(value) != _DEVICE_SECRET_BYTES:
        raise PasswordDecryptionError("Invalid Home Assistant device-binding key")
    return value


def _validate_scrypt_kdf(kdf: dict[str, Any]) -> dict[str, Any]:
    try:
        salt = _unb64(str(kdf["salt"]))
        n = int(kdf["n"])
        r = int(kdf["r"])
        p = int(kdf["p"])
        length = int(kdf.get("length", _KEY_BYTES))
    except (KeyError, TypeError, ValueError) as err:
        raise PasswordDecryptionError("Invalid scrypt parameters") from err
    if not 8 <= len(salt) <= 64:
        raise PasswordDecryptionError("Invalid password salt")
    if n < 2**14 or n > 2**18 or n & (n - 1):
        raise PasswordDecryptionError("Unsafe scrypt work factor")
    if r < 1 or r > 32 or p < 1 or p > 8 or length != _KEY_BYTES:
        raise PasswordDecryptionError("Unsafe scrypt parameters")
    return {"name": KDF_SCRYPT, "salt": salt, "n": n, "r": r, "p": p, "length": length}


def _validate_argon2id_kdf(kdf: dict[str, Any]) -> dict[str, Any]:
    try:
        salt = _unb64(str(kdf["salt"]))
        memory_kib = int(kdf["memory_kib"])
        time_cost = int(kdf["time_cost"])
        parallelism = int(kdf["parallelism"])
        length = int(kdf.get("length", _KEY_BYTES))
        version = int(kdf.get("version", _ARGON2_VERSION))
    except (KeyError, TypeError, ValueError) as err:
        raise PasswordDecryptionError("Invalid Argon2id parameters") from err
    if not 16 <= len(salt) <= 64:
        raise PasswordDecryptionError("Invalid password salt")
    if memory_kib < 7 * 1024 or memory_kib > 256 * 1024:
        raise PasswordDecryptionError("Unsafe Argon2id memory cost")
    if time_cost < 1 or time_cost > 8:
        raise PasswordDecryptionError("Unsafe Argon2id time cost")
    if parallelism < 1 or parallelism > 8 or length != _KEY_BYTES:
        raise PasswordDecryptionError("Unsafe Argon2id parameters")
    if version != _ARGON2_VERSION:
        raise PasswordDecryptionError("Unsupported Argon2 version")
    return {
        "name": KDF_ARGON2ID,
        "salt": salt,
        "memory_kib": memory_kib,
        "time_cost": time_cost,
        "parallelism": parallelism,
        "length": length,
        "version": version,
    }


def _validate_kdf(kdf: dict[str, Any]) -> dict[str, Any]:
    name = str(kdf.get("name") or "")
    if name == KDF_ARGON2ID:
        return _validate_argon2id_kdf(kdf)
    if name == KDF_SCRYPT:
        return _validate_scrypt_kdf(kdf)
    raise PasswordDecryptionError("Unsupported password KDF")


def _derive_key(password: str, kdf: dict[str, Any]) -> bytes:
    if not isinstance(password, str) or not password:
        raise PasswordDecryptionError("Password is required")
    params = _validate_kdf(kdf)
    password_bytes = password.encode("utf-8")
    if params["name"] == KDF_ARGON2ID:
        try:
            return hash_secret_raw(
                secret=password_bytes,
                salt=params["salt"],
                time_cost=params["time_cost"],
                memory_cost=params["memory_kib"],
                parallelism=params["parallelism"],
                hash_len=_KEY_BYTES,
                type=Type.ID,
                version=params["version"],
            )
        except HashingError as err:
            raise PasswordDecryptionError("Argon2id key derivation failed") from err
    return Scrypt(
        salt=params["salt"], length=_KEY_BYTES,
        n=params["n"], r=params["r"], p=params["p"],
    ).derive(password_bytes)


def _derive_kek(password_key: bytes, *, binding_secret: bytes, context: str) -> bytes:
    """Domain-separate password KDF output from the long-lived data key.

    The local vault uses a random 256-bit device secret as HKDF salt. Portable
    backups use their own random envelope binding value so the format remains
    self-contained and portable.
    """
    if len(password_key) != _KEY_BYTES or len(binding_secret) != _DEVICE_SECRET_BYTES:
        raise PasswordDecryptionError("Invalid envelope key material")
    return HKDF(
        algorithm=hashes.SHA512(),
        length=_KEY_BYTES,
        salt=binding_secret,
        info=f"bitcoin_stack_tracker:kek:v3:{context}".encode("utf-8"),
    ).derive(password_key)


def _aad(mode: str, context: str, purpose: str = "data") -> bytes:
    return f"bitcoin_stack_tracker:{mode}:{context}:{purpose}".encode("utf-8")


def new_kdf_metadata() -> dict[str, Any]:
    return {
        "name": KDF_ARGON2ID,
        "salt": _b64(os.urandom(_SALT_BYTES)),
        "memory_kib": _ARGON2_MEMORY_KIB,
        "time_cost": _ARGON2_TIME_COST,
        "parallelism": _ARGON2_PARALLELISM,
        "length": _KEY_BYTES,
        "version": _ARGON2_VERSION,
    }


def kdf_security_profile(kdf: dict[str, Any]) -> dict[str, Any]:
    params = _validate_kdf(kdf)
    if params["name"] == KDF_ARGON2ID:
        current = (
            params["memory_kib"] >= _ARGON2_MEMORY_KIB
            and params["time_cost"] >= _ARGON2_TIME_COST
            and params["parallelism"] >= _ARGON2_PARALLELISM
            and params["version"] == _ARGON2_VERSION
        )
        return {
            "name": KDF_ARGON2ID,
            "memory_kib": params["memory_kib"],
            "estimated_memory_mib": round(params["memory_kib"] / 1024, 1),
            "time_cost": params["time_cost"],
            "parallelism": params["parallelism"],
            "version": params["version"],
            "salt_bits": len(params["salt"]) * 8,
            "current_profile": current,
            "profile": "high-security-128MiB-t3-p1" if current else "custom-argon2id",
        }
    memory_mib = round((128 * params["n"] * params["r"]) / (1024 * 1024), 1)
    return {
        "name": KDF_SCRYPT,
        "n": params["n"], "r": params["r"], "p": params["p"],
        "estimated_memory_mib": memory_mib,
        "salt_bits": len(params["salt"]) * 8,
        "current_profile": False,
        "profile": "legacy-scrypt",
    }


def password_kdf_needs_upgrade(kdf: dict[str, Any]) -> bool:
    params = _validate_kdf(kdf)
    if params["name"] != KDF_ARGON2ID:
        return True
    return not (
        params["memory_kib"] >= _ARGON2_MEMORY_KIB
        and params["time_cost"] >= _ARGON2_TIME_COST
        and params["parallelism"] >= _ARGON2_PARALLELISM
        and params["version"] == _ARGON2_VERSION
    )


def password_envelope_needs_upgrade(envelope: dict[str, Any]) -> bool:
    """Return True for every pre-v3 format or weaker Argon2 profile."""
    if str(envelope.get("encryption_mode") or "") != PASSWORD_ENVELOPE_MODE:
        return True
    kdf = envelope.get("kdf")
    return not isinstance(kdf, dict) or password_kdf_needs_upgrade(kdf)


def password_encryption_mode_for_kdf(kdf: dict[str, Any]) -> str:
    """Legacy helper retained for reading/saving v1/v2 compatibility tests."""
    params = _validate_kdf(kdf)
    return PASSWORD_ENVELOPE_MODE_V2 if params["name"] == KDF_ARGON2ID else PASSWORD_ENVELOPE_MODE_V1


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _validate_v3_envelope(envelope: dict[str, Any], *, expected_mode: str) -> None:
    if envelope.get("encrypted") is not True:
        raise PasswordDecryptionError("Data is not encrypted")
    if str(envelope.get("encryption_mode") or "") != expected_mode:
        raise PasswordDecryptionError("Unexpected encryption mode")
    if str(envelope.get("format") or "") != PASSWORD_FORMAT:
        raise PasswordDecryptionError("Unsupported encryption format")
    if int(envelope.get("version", 0) or 0) != 3:
        raise PasswordDecryptionError("Unsupported encryption version")
    kdf = envelope.get("kdf")
    if not isinstance(kdf, dict):
        raise PasswordDecryptionError("Password KDF metadata is missing")
    _validate_kdf(kdf)
    key_wrap = envelope.get("key_wrap")
    data = envelope.get("data")
    if not isinstance(key_wrap, dict) or not isinstance(data, dict):
        raise PasswordDecryptionError("Envelope encryption metadata is missing")
    if str(key_wrap.get("algorithm") or "") != PASSWORD_FORMAT:
        raise PasswordDecryptionError("Unsupported key-wrap algorithm")
    if str(data.get("algorithm") or "") != PASSWORD_FORMAT:
        raise PasswordDecryptionError("Unsupported data algorithm")


def _build_v3_envelope(
    payload: dict[str, Any], *, password: str, mode: str, context: str,
    binding_secret: bytes, device_bound: bool, existing_dek: bytes | None = None,
) -> tuple[dict[str, Any], bytes]:
    validate_new_password(password)
    kdf = new_kdf_metadata()
    pdk = _derive_key(password, kdf)
    kek = _derive_kek(pdk, binding_secret=binding_secret, context=context)
    dek = bytes(existing_dek) if existing_dek is not None else os.urandom(_KEY_BYTES)
    if len(dek) != _KEY_BYTES:
        raise ValueError("Invalid AES-256 data key length")

    wrap_nonce = os.urandom(_NONCE_BYTES)
    wrapped_dek = AESGCM(kek).encrypt(
        wrap_nonce, dek, _aad(mode, context, "key-wrap")
    )
    data_nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(dek).encrypt(
        data_nonce, _json_bytes(payload), _aad(mode, context, "ledger-data")
    )
    envelope = {
        "encrypted": True,
        "format": PASSWORD_FORMAT,
        "encryption_mode": mode,
        "version": 3,
        "kdf": deepcopy(kdf),
        "key_wrap": {
            "algorithm": PASSWORD_FORMAT,
            "nonce": _b64(wrap_nonce),
            "ciphertext": _b64(wrapped_dek),
            "kek_bits": 256,
            "wrapped_key_bits": 256,
            "hkdf": "HKDF-SHA-512",
            "device_bound": bool(device_bound),
        },
        "data": {
            "algorithm": PASSWORD_FORMAT,
            "nonce": _b64(data_nonce),
            "ciphertext": _b64(ciphertext),
            "key_bits": 256,
            "nonce_bits": 96,
            "tag_bits": 128,
            "aad": True,
        },
        "aead": {
            "key_bits": 256,
            "nonce_bits": 96,
            "tag_bits": 128,
            "aad": True,
            "envelope_encryption": True,
        },
    }
    return envelope, dek


def encrypt_v3_payload_with_dek(
    payload: dict[str, Any], *, envelope: dict[str, Any], dek: bytes, context: str
) -> dict[str, Any]:
    """Re-encrypt payload under the current random DEK with a fresh GCM nonce."""
    mode = str(envelope.get("encryption_mode") or "")
    if mode != PASSWORD_ENVELOPE_MODE:
        raise ValueError("Current local vault envelope is required")
    _validate_v3_envelope(envelope, expected_mode=mode)
    if len(dek) != _KEY_BYTES:
        raise ValueError("Invalid AES-256 data key length")
    result = deepcopy(envelope)
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(dek).encrypt(
        nonce, _json_bytes(payload), _aad(mode, context, "ledger-data")
    )
    result["data"] = {
        "algorithm": PASSWORD_FORMAT,
        "nonce": _b64(nonce),
        "ciphertext": _b64(ciphertext),
        "key_bits": 256,
        "nonce_bits": 96,
        "tag_bits": 128,
        "aad": True,
    }
    return result


def _decrypt_v3_envelope(
    envelope: dict[str, Any], *, password: str, expected_mode: str,
    context: str, binding_secret: bytes,
) -> tuple[dict[str, Any], bytes]:
    _validate_v3_envelope(envelope, expected_mode=expected_mode)
    kdf = envelope["kdf"]
    pdk = _derive_key(password, kdf)
    kek = _derive_kek(pdk, binding_secret=binding_secret, context=context)
    try:
        key_wrap = envelope["key_wrap"]
        wrap_nonce = _unb64(str(key_wrap["nonce"]))
        if len(wrap_nonce) != _NONCE_BYTES:
            raise PasswordDecryptionError("Invalid AES-GCM key-wrap nonce length")
        dek = AESGCM(kek).decrypt(
            wrap_nonce,
            _unb64(str(key_wrap["ciphertext"])),
            _aad(expected_mode, context, "key-wrap"),
        )
        if len(dek) != _KEY_BYTES:
            raise PasswordDecryptionError("Invalid decrypted data key")
        data = envelope["data"]
        nonce = _unb64(str(data["nonce"]))
        if len(nonce) != _NONCE_BYTES:
            raise PasswordDecryptionError("Invalid AES-GCM data nonce length")
        plaintext = AESGCM(dek).decrypt(
            nonce,
            _unb64(str(data["ciphertext"])),
            _aad(expected_mode, context, "ledger-data"),
        )
        result = json.loads(plaintext.decode("utf-8"))
    except PasswordDecryptionError:
        raise
    except (InvalidTag, KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise PasswordDecryptionError("Wrong password/device key or damaged encrypted data") from err
    if not isinstance(result, dict):
        raise PasswordDecryptionError("Decrypted payload is not a JSON object")
    return deepcopy(result), bytes(dek)


# ---- Legacy v1/v2 helpers -------------------------------------------------

def encrypt_with_key(
    payload: dict[str, Any], *, key: bytes, kdf: dict[str, Any], mode: str, context: str,
) -> dict[str, Any]:
    """Legacy single-key AEAD writer retained for compatibility tests/migration."""
    if len(key) != _KEY_BYTES:
        raise ValueError("Invalid AES-256 key length")
    _validate_kdf(kdf)
    if mode not in {
        PASSWORD_ENVELOPE_MODE_V1, PASSWORD_ENVELOPE_MODE_V2,
        BACKUP_ENVELOPE_MODE_V1, BACKUP_ENVELOPE_MODE_V2,
    }:
        raise ValueError("Unsupported legacy encryption mode")
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, _json_bytes(payload), _aad(mode, context, "data"))
    version = 2 if mode in {PASSWORD_ENVELOPE_MODE_V2, BACKUP_ENVELOPE_MODE_V2} else 1
    return {
        "encrypted": True,
        "format": PASSWORD_FORMAT,
        "encryption_mode": mode,
        "version": version,
        "kdf": deepcopy(kdf),
        "nonce": _b64(nonce),
        "ciphertext": _b64(ciphertext),
        "aead": {"key_bits": 256, "nonce_bits": 96, "tag_bits": 128, "aad": True},
    }


def _decrypt_legacy_envelope(
    envelope: dict[str, Any], *, password: str, expected_mode: str, context: str
) -> tuple[dict[str, Any], bytes]:
    if envelope.get("encrypted") is not True or str(envelope.get("encryption_mode")) != expected_mode:
        raise PasswordDecryptionError("Unexpected encryption mode")
    if str(envelope.get("format")) != PASSWORD_FORMAT:
        raise PasswordDecryptionError("Unsupported encryption format")
    kdf = envelope.get("kdf")
    if not isinstance(kdf, dict):
        raise PasswordDecryptionError("Password KDF metadata is missing")
    key = _derive_key(password, kdf)
    try:
        nonce = _unb64(str(envelope["nonce"]))
        if len(nonce) != _NONCE_BYTES:
            raise PasswordDecryptionError("Invalid AES-GCM nonce length")
        # Legacy envelopes used an AAD without the explicit purpose suffix. Accept it
        # first; then accept the purpose form used by this compatibility writer.
        ciphertext = _unb64(str(envelope["ciphertext"]))
        try:
            plaintext = AESGCM(key).decrypt(
                nonce, ciphertext,
                f"bitcoin_stack_tracker:{expected_mode}:{context}".encode("utf-8"),
            )
        except InvalidTag:
            plaintext = AESGCM(key).decrypt(
                nonce, ciphertext, _aad(expected_mode, context, "data")
            )
        result = json.loads(plaintext.decode("utf-8"))
    except PasswordDecryptionError:
        raise
    except (InvalidTag, KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise PasswordDecryptionError("Wrong password or damaged encrypted data") from err
    if not isinstance(result, dict):
        raise PasswordDecryptionError("Decrypted payload is not a JSON object")
    return deepcopy(result), key


# ---- Public vault API -----------------------------------------------------

def create_password_envelope(
    payload: dict[str, Any], *, password: str, entry_id: str, device_secret: bytes
) -> tuple[dict[str, Any], bytes]:
    secret = _validate_device_secret(device_secret)
    return _build_v3_envelope(
        payload, password=password, mode=PASSWORD_ENVELOPE_MODE,
        context=f"ledger:{entry_id}", binding_secret=secret, device_bound=True,
    )


def decrypt_password_envelope(
    envelope: dict[str, Any], *, password: str, entry_id: str,
    device_secret: bytes | None = None,
) -> tuple[dict[str, Any], bytes]:
    mode = str(envelope.get("encryption_mode") or "")
    if mode == PASSWORD_ENVELOPE_MODE:
        return _decrypt_v3_envelope(
            envelope, password=password, expected_mode=mode,
            context=f"ledger:{entry_id}",
            binding_secret=_validate_device_secret(device_secret),
        )
    if mode in {PASSWORD_ENVELOPE_MODE_V1, PASSWORD_ENVELOPE_MODE_V2}:
        return _decrypt_legacy_envelope(
            envelope, password=password, expected_mode=mode,
            context=f"ledger:{entry_id}",
        )
    raise PasswordDecryptionError("Unexpected encryption mode")


def reencrypt_password_payload(
    payload: dict[str, Any], *, password: str, entry_id: str, device_secret: bytes
) -> tuple[dict[str, Any], bytes]:
    return create_password_envelope(
        payload, password=password, entry_id=entry_id, device_secret=device_secret
    )


def rewrap_password_envelope(
    payload: dict[str, Any], *, dek: bytes, new_password: str,
    entry_id: str, device_secret: bytes,
) -> dict[str, Any]:
    secret = _validate_device_secret(device_secret)
    envelope, _ = _build_v3_envelope(
        payload, password=new_password, mode=PASSWORD_ENVELOPE_MODE,
        context=f"ledger:{entry_id}", binding_secret=secret, device_bound=True,
        existing_dek=dek,
    )
    return envelope


def password_kdf_from_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    kdf = envelope.get("kdf")
    if not isinstance(kdf, dict):
        raise PasswordDecryptionError("Password KDF metadata is missing")
    _validate_kdf(kdf)
    return deepcopy(kdf)


# ---- Portable backup API -------------------------------------------------

def create_backup_envelope(payload: dict[str, Any], *, password: str) -> dict[str, Any]:
    # Portable backups cannot depend on a machine-only secret. A random 256-bit
    # binding value is stored in the envelope and is used only for domain/key
    # separation; offline resistance is provided by Argon2id + the password.
    binding = os.urandom(_DEVICE_SECRET_BYTES)
    envelope, _dek = _build_v3_envelope(
        payload, password=password, mode=BACKUP_ENVELOPE_MODE,
        context="portable-backup-v3", binding_secret=binding, device_bound=False,
    )
    envelope["portable_binding"] = _b64(binding)
    envelope["backup_format"] = "bitcoin-stack-tracker-backup"
    envelope["backup_version"] = BACKUP_SCHEMA_VERSION
    return envelope


def decrypt_backup_envelope(envelope: dict[str, Any], *, password: str) -> dict[str, Any]:
    if envelope.get("backup_format") != "bitcoin-stack-tracker-backup":
        raise PasswordDecryptionError("Not a Bitcoin Stack Tracker backup")
    try:
        version = int(envelope.get("backup_version", 0))
    except (TypeError, ValueError) as err:
        raise PasswordDecryptionError("Unsupported backup version") from err
    mode = str(envelope.get("encryption_mode") or "")
    if version == 3 and mode == BACKUP_ENVELOPE_MODE:
        binding = _unb64(str(envelope.get("portable_binding") or ""))
        if len(binding) != _DEVICE_SECRET_BYTES:
            raise PasswordDecryptionError("Portable backup binding is invalid")
        payload, _dek = _decrypt_v3_envelope(
            envelope, password=password, expected_mode=mode,
            context="portable-backup-v3", binding_secret=binding,
        )
        return payload
    if version == 2 and mode == BACKUP_ENVELOPE_MODE_V2:
        payload, _ = _decrypt_legacy_envelope(
            envelope, password=password, expected_mode=mode,
            context="portable-backup-v2",
        )
        return payload
    if version == 1 and mode == BACKUP_ENVELOPE_MODE_V1:
        payload, _ = _decrypt_legacy_envelope(
            envelope, password=password, expected_mode=mode,
            context="portable-backup-v1",
        )
        return payload
    raise PasswordDecryptionError("Unsupported backup version")


def is_password_envelope(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and value.get("encrypted") is True
        and value.get("encryption_mode") in {
            PASSWORD_ENVELOPE_MODE, PASSWORD_ENVELOPE_MODE_V2, PASSWORD_ENVELOPE_MODE_V1
        }
    )


def is_backup_envelope(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and value.get("encrypted") is True
        and value.get("encryption_mode") in {
            BACKUP_ENVELOPE_MODE, BACKUP_ENVELOPE_MODE_V2, BACKUP_ENVELOPE_MODE_V1
        }
        and value.get("backup_format") == "bitcoin-stack-tracker-backup"
    )
