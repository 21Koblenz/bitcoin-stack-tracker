"""Home Assistant user allowlist and legacy installation-key compatibility."""

from __future__ import annotations

import asyncio
import base64
from copy import deepcopy
import json
import os
from time import monotonic
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    SECURITY_SCHEMA_VERSION,
    SECURITY_STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
)

ENCRYPTION_NONE = "none"
ENCRYPTION_PASSWORD = "password"
ENCRYPTION_LEGACY = "installation_key_legacy"
VALID_ENCRYPTION_MODES = {ENCRYPTION_NONE, ENCRYPTION_PASSWORD, ENCRYPTION_LEGACY}

_ROOT_KEY_BYTES = 32
_VAULT_KEY_BYTES = 32
_NONCE_BYTES = 12


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


class VaultAccessDenied(PermissionError):
    """Raised when a Home Assistant user is not allowed to use the vault."""


class VaultLockedError(PermissionError):
    """Raised when a password-protected vault is locked for this user."""


class VaultDecryptionError(ValueError):
    """Raised when legacy encrypted vault data cannot be decrypted."""


class BitcoinSecurityStore:
    """Persist access policy and track volatile per-user unlock state.

    The allowlist is always enforced. Password unlock state exists only in RAM
    and is cleared on every Home Assistant restart. The older beta's random
    installation-key scheme is retained only so existing ledgers can be opened
    and migrated.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._store = Store[dict[str, Any]](
            hass, STORAGE_VERSION, f"{SECURITY_STORAGE_KEY_PREFIX}.{entry_id}"
        )
        self._root_key_path = Path(hass.config.path(".storage", f"{DOMAIN}.root_key"))
        self._lock = asyncio.Lock()
        self._root_key: bytes | None = None
        self._legacy_vault_key: bytes | None = None
        self._unlocked_user_ids: set[str] = set()
        # Volatile Core-side session expiry. Nothing here is persisted, so every
        # Home Assistant restart starts locked. A timeout of 0 deliberately means
        # "disabled" for long setup sessions.
        self._unlock_timeouts: dict[str, int] = {}
        self._unlock_deadlines: dict[str, float | None] = {}
        self._data: dict[str, Any] = {
            "schema_version": SECURITY_SCHEMA_VERSION,
            "owner_user_id": None,
            "allowed_user_ids": [],
            "expose_sensitive_sensors": False,
            "encryption_mode": ENCRYPTION_NONE,
            "key_slots": {},
        }

    async def async_load(self, default_encryption_mode: str | None = None) -> None:
        """Load access settings and normalize the owner/allowlist."""
        async with self._lock:
            loaded = await self._store.async_load()
            if isinstance(loaded, dict):
                self._data.update(loaded)

            users = [
                user
                for user in await self.hass.auth.async_get_users()
                if not getattr(user, "system_generated", False)
            ]
            owner = next((u for u in users if getattr(u, "is_owner", False)), None)
            owner = owner or next((u for u in users if getattr(u, "is_admin", False)), None)
            owner = owner or (users[0] if users else None)
            if owner is None:
                raise RuntimeError("No Home Assistant user exists for portfolio ownership")

            valid_ids = {str(user.id) for user in users}
            owner_id = str(self._data.get("owner_user_id") or owner.id)
            if owner_id not in valid_ids:
                owner_id = str(owner.id)
            self._data["owner_user_id"] = owner_id

            allowed = {
                str(user_id)
                for user_id in self._data.get("allowed_user_ids", [])
                if str(user_id) in valid_ids
            }
            allowed.add(owner_id)
            self._data["allowed_user_ids"] = sorted(allowed)
            self._data["expose_sensitive_sensors"] = bool(
                self._data.get("expose_sensitive_sensors", False)
            )

            slots = self._data.get("key_slots")
            if not isinstance(slots, dict):
                slots = {}
                self._data["key_slots"] = slots

            mode = str(self._data.get("encryption_mode") or "")
            if mode not in VALID_ENCRYPTION_MODES:
                mode = ENCRYPTION_LEGACY if slots else (default_encryption_mode or ENCRYPTION_NONE)
            if mode == ENCRYPTION_NONE and default_encryption_mode in {
                ENCRYPTION_NONE,
                ENCRYPTION_PASSWORD,
            } and loaded is None:
                mode = default_encryption_mode
            self._data["encryption_mode"] = mode
            self._data["schema_version"] = SECURITY_SCHEMA_VERSION

            if mode == ENCRYPTION_LEGACY or slots:
                self._root_key = await self.hass.async_add_executor_job(
                    self._load_or_create_root_key
                )
                self._legacy_vault_key = await self.hass.async_add_executor_job(
                    self._unwrap_any_slot,
                    slots,
                    set(str(user_id) for user_id in slots) | allowed,
                )
                if self._legacy_vault_key is None:
                    self._legacy_vault_key = os.urandom(_VAULT_KEY_BYTES)
                vault_key = self._legacy_vault_key
                self._data["key_slots"] = await self.hass.async_add_executor_job(
                    self._wrap_slots, sorted(allowed), vault_key
                )

            self._unlocked_user_ids.clear()
            self._unlock_timeouts.clear()
            self._unlock_deadlines.clear()
            await self._store.async_save(self._data)

    def _load_or_create_root_key(self) -> bytes:
        self._root_key_path.parent.mkdir(parents=True, exist_ok=True)
        if self._root_key_path.exists():
            key = _unb64(self._root_key_path.read_text(encoding="ascii").strip())
            if len(key) != _ROOT_KEY_BYTES:
                raise ValueError("Invalid Bitcoin Stack Tracker root key length")
            try:
                os.chmod(self._root_key_path, 0o600)
            except OSError:
                pass
            return key
        key = os.urandom(_ROOT_KEY_BYTES)
        temp = self._root_key_path.with_suffix(".tmp")
        temp.write_text(_b64(key), encoding="ascii")
        os.chmod(temp, 0o600)
        temp.replace(self._root_key_path)
        return key

    def _derive_user_key(self, user_id: str) -> bytes:
        if self._root_key is None:
            raise RuntimeError("Legacy root key is unavailable")
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.entry_id.encode("utf-8"),
            info=f"{DOMAIN}:user-key:{user_id}".encode("utf-8"),
        ).derive(self._root_key)

    def _wrap_vault_key(self, user_id: str, vault_key: bytes) -> dict[str, str]:
        nonce = os.urandom(_NONCE_BYTES)
        aad = f"{DOMAIN}:{self.entry_id}:{user_id}:slot-v1".encode("utf-8")
        ciphertext = AESGCM(self._derive_user_key(user_id)).encrypt(nonce, vault_key, aad)
        return {
            "algorithm": "AES-256-GCM",
            "nonce": _b64(nonce),
            "ciphertext": _b64(ciphertext),
        }

    def _unwrap_slot(self, user_id: str, slot: dict[str, Any]) -> bytes:
        aad = f"{DOMAIN}:{self.entry_id}:{user_id}:slot-v1".encode("utf-8")
        try:
            return AESGCM(self._derive_user_key(user_id)).decrypt(
                _unb64(str(slot["nonce"])),
                _unb64(str(slot["ciphertext"])),
                aad,
            )
        except (InvalidTag, KeyError, ValueError) as err:
            raise VaultDecryptionError("Unable to decrypt legacy user key slot") from err

    def _unwrap_any_slot(
        self, slots: dict[str, Any], allowed_user_ids: set[str]
    ) -> bytes | None:
        for user_id in allowed_user_ids:
            slot = slots.get(user_id)
            if not isinstance(slot, dict):
                continue
            try:
                key = self._unwrap_slot(user_id, slot)
            except VaultDecryptionError:
                continue
            if len(key) == _VAULT_KEY_BYTES:
                return key
        return None

    def _wrap_slots(
        self, user_ids: list[str], vault_key: bytes
    ) -> dict[str, dict[str, str]]:
        """Build legacy AES key slots in an executor worker."""
        return {
            user_id: self._wrap_vault_key(user_id, vault_key)
            for user_id in user_ids
        }

    @property
    def owner_user_id(self) -> str:
        return str(self._data.get("owner_user_id") or "")

    @property
    def allowed_user_ids(self) -> list[str]:
        return list(self._data.get("allowed_user_ids", []))

    @property
    def expose_sensitive_sensors(self) -> bool:
        return bool(self._data.get("expose_sensitive_sensors", False))

    @property
    def encryption_mode(self) -> str:
        mode = str(self._data.get("encryption_mode") or ENCRYPTION_NONE)
        return mode if mode in VALID_ENCRYPTION_MODES else ENCRYPTION_NONE

    def is_allowed(self, user_id: str | None) -> bool:
        return bool(user_id and str(user_id) in set(self.allowed_user_ids))

    def is_owner(self, user_id: str | None) -> bool:
        return bool(user_id and str(user_id) == self.owner_user_id)

    @staticmethod
    def _validate_auto_lock_minutes(minutes: int) -> int:
        value = int(minutes)
        if value not in {0, 5, 15, 30, 60, 120}:
            raise ValueError("Auto-lock must be 0, 5, 15, 30, 60 or 120 minutes")
        return value

    def _expire_user_if_due(self, user_id: str) -> bool:
        deadline = self._unlock_deadlines.get(user_id)
        if deadline is None or user_id not in self._unlocked_user_ids:
            return False
        if monotonic() < deadline:
            return False
        self._unlocked_user_ids.discard(user_id)
        self._unlock_timeouts.pop(user_id, None)
        self._unlock_deadlines.pop(user_id, None)
        return True

    def expire_unlock_sessions(self) -> list[str]:
        """Expire Core-side password sessions and return expired user IDs."""
        expired: list[str] = []
        for user_id in list(self._unlocked_user_ids):
            if self._expire_user_if_due(user_id):
                expired.append(user_id)
        return expired

    def is_user_unlocked(self, user_id: str | None) -> bool:
        if self.encryption_mode != ENCRYPTION_PASSWORD:
            return self.is_allowed(user_id)
        if not user_id:
            return False
        value = str(user_id)
        self._expire_user_if_due(value)
        return value in self._unlocked_user_ids

    def require_allowed(self, user_id: str | None) -> None:
        if not self.is_allowed(user_id):
            raise VaultAccessDenied("This Home Assistant user is not allowed to access the portfolio")

    def require_owner(self, user_id: str | None) -> None:
        if not self.is_owner(user_id):
            raise VaultAccessDenied("Only the portfolio owner can change access settings")

    def require_unlocked(self, user_id: str | None) -> None:
        self.require_allowed(user_id)
        if not self.is_user_unlocked(user_id):
            raise VaultLockedError("The password-protected portfolio is locked for this user")

    def mark_user_unlocked(self, user_id: str, auto_lock_minutes: int = 15) -> None:
        self.require_allowed(user_id)
        value = str(user_id)
        timeout = self._validate_auto_lock_minutes(auto_lock_minutes)
        self._unlocked_user_ids.add(value)
        self._unlock_timeouts[value] = timeout
        self._unlock_deadlines[value] = None if timeout == 0 else monotonic() + timeout * 60

    def configure_user_auto_lock(self, user_id: str, minutes: int, *, touch: bool = True) -> None:
        """Set volatile Core-side auto-lock for one already-unlocked HA user."""
        self.require_unlocked(user_id)
        value = str(user_id)
        timeout = self._validate_auto_lock_minutes(minutes)
        self._unlock_timeouts[value] = timeout
        if timeout == 0:
            self._unlock_deadlines[value] = None
        elif touch or self._unlock_deadlines.get(value) is None:
            self._unlock_deadlines[value] = monotonic() + timeout * 60

    def touch_user_unlock(self, user_id: str) -> None:
        """Refresh a finite Core-side unlock deadline after real user activity."""
        self.require_unlocked(user_id)
        value = str(user_id)
        timeout = int(self._unlock_timeouts.get(value, 15))
        if timeout > 0:
            self._unlock_deadlines[value] = monotonic() + timeout * 60

    def user_auto_lock_minutes(self, user_id: str | None) -> int | None:
        if not user_id or not self.is_user_unlocked(user_id):
            return None
        return int(self._unlock_timeouts.get(str(user_id), 15))

    def user_unlock_expires_in_seconds(self, user_id: str | None) -> int | None:
        if not user_id or not self.is_user_unlocked(user_id):
            return None
        deadline = self._unlock_deadlines.get(str(user_id))
        if deadline is None:
            return None
        return max(0, int(deadline - monotonic()))

    def lock_user(self, user_id: str) -> None:
        value = str(user_id)
        self._unlocked_user_ids.discard(value)
        self._unlock_timeouts.pop(value, None)
        self._unlock_deadlines.pop(value, None)

    def lock_all_users(self) -> None:
        self._unlocked_user_ids.clear()
        self._unlock_timeouts.clear()
        self._unlock_deadlines.clear()

    @property
    def unlocked_user_count(self) -> int:
        self.expire_unlock_sessions()
        return len(self._unlocked_user_ids)

    async def async_user_directory(self) -> list[dict[str, Any]]:
        users = await self.hass.auth.async_get_users()
        allowed = set(self.allowed_user_ids)
        return [
            {
                "id": str(user.id),
                "name": str(user.name or user.id),
                "is_owner": bool(getattr(user, "is_owner", False)),
                "is_admin": bool(getattr(user, "is_admin", False)),
                "system_generated": bool(getattr(user, "system_generated", False)),
                "allowed": str(user.id) in allowed,
                "unlocked": self.is_user_unlocked(str(user.id)),
            }
            for user in users
            if not getattr(user, "system_generated", False)
        ]

    async def async_allowed_user_snapshot(self) -> list[dict[str, Any]]:
        directory = await self.async_user_directory()
        return [
            {"id": item["id"], "name": item["name"]}
            for item in directory
            if item["allowed"]
        ]

    async def async_set_allowed_users(
        self, actor_user_id: str, allowed_user_ids: list[str]
    ) -> dict[str, Any]:
        self.require_owner(actor_user_id)
        async with self._lock:
            users = {
                str(user.id): user
                for user in await self.hass.auth.async_get_users()
                if not getattr(user, "system_generated", False)
            }
            selected = {str(uid) for uid in allowed_user_ids if str(uid) in users}
            selected.add(self.owner_user_id)
            self._data["allowed_user_ids"] = sorted(selected)
            self._unlocked_user_ids.intersection_update(selected)
            self._unlock_timeouts = {uid: value for uid, value in self._unlock_timeouts.items() if uid in selected}
            self._unlock_deadlines = {uid: value for uid, value in self._unlock_deadlines.items() if uid in selected}
            if self.encryption_mode == ENCRYPTION_LEGACY:
                if self._legacy_vault_key is None:
                    raise RuntimeError("Legacy vault key is unavailable")
                self._data["key_slots"] = await self.hass.async_add_executor_job(
                    self._wrap_slots, sorted(selected), self._legacy_vault_key
                )
            else:
                self._data["key_slots"] = {}
            await self._store.async_save(self._data)
            return self.public_status(actor_user_id)

    async def async_restore_allowed_users(
        self,
        actor_user_id: str,
        requested_user_ids: list[str],
        *,
        expose_sensitive_sensors: bool | None = None,
    ) -> dict[str, Any]:
        """Restore only IDs that exist on this Home Assistant installation."""
        self.require_owner(actor_user_id)
        result = await self.async_set_allowed_users(actor_user_id, requested_user_ids)
        if expose_sensitive_sensors is not None:
            result = await self.async_set_sensitive_sensors(
                actor_user_id, expose_sensitive_sensors
            )
        return result

    async def async_set_sensitive_sensors(
        self, actor_user_id: str, enabled: bool
    ) -> dict[str, Any]:
        self.require_owner(actor_user_id)
        if enabled and self.encryption_mode == ENCRYPTION_PASSWORD:
            raise ValueError(
                "Sensitive Home Assistant entities cannot be enabled while password encryption is active"
            )
        async with self._lock:
            self._data["expose_sensitive_sensors"] = bool(enabled)
            await self._store.async_save(self._data)
            return self.public_status(actor_user_id)

    async def async_set_encryption_mode(self, mode: str) -> None:
        if mode not in VALID_ENCRYPTION_MODES:
            raise ValueError("Unsupported encryption mode")
        async with self._lock:
            self._data["encryption_mode"] = mode
            if mode == ENCRYPTION_PASSWORD:
                # Entity states and recorder history are not user-private.
                self._data["expose_sensitive_sensors"] = False
            if mode != ENCRYPTION_LEGACY:
                self._data["key_slots"] = {}
                self._legacy_vault_key = None
            self._unlocked_user_ids.clear()
            await self._store.async_save(self._data)

    async def async_remove(self) -> None:
        """Remove access-policy storage after config-entry deletion."""
        await self._store.async_remove()

    def public_status(self, user_id: str | None) -> dict[str, Any]:
        mode = self.encryption_mode
        return {
            "encryption_mode": mode,
            "encryption": "AES-256-GCM" if mode != ENCRYPTION_NONE else "none",
            "password_kdf": "argon2id" if mode == ENCRYPTION_PASSWORD else None,
            "encrypted_at_rest": mode != ENCRYPTION_NONE,
            "password_protected": mode == ENCRYPTION_PASSWORD,
            "allowed": self.is_allowed(user_id),
            "owner": self.is_owner(user_id),
            "user_unlocked": self.is_user_unlocked(user_id),
            "auto_lock_minutes": self.user_auto_lock_minutes(user_id),
            "unlock_expires_in_seconds": self.user_unlock_expires_in_seconds(user_id),
            "unlocked_user_count": self.unlocked_user_count if self.is_owner(user_id) else None,
            "owner_user_id": self.owner_user_id if self.is_owner(user_id) else None,
            "allowed_user_ids": self.allowed_user_ids if self.is_owner(user_id) else [],
            "expose_sensitive_sensors": self.expose_sensitive_sensors,
            "threat_model": (
                "Access is denied to unapproved Home Assistant users. Password mode also "
                "protects ledger files and backups. A host/root administrator remains trusted."
            ),
        }

    # Legacy beta encryption compatibility. New password mode does not use this.
    def encrypt_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._legacy_vault_key is None:
            raise RuntimeError("Legacy vault key is unavailable")
        nonce = os.urandom(_NONCE_BYTES)
        aad = f"{DOMAIN}:{self.entry_id}:ledger-v1".encode("utf-8")
        plaintext = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        ciphertext = AESGCM(self._legacy_vault_key).encrypt(nonce, plaintext, aad)
        return {
            "encrypted": True,
            "format": "AES-256-GCM",
            "version": 1,
            "nonce": _b64(nonce),
            "ciphertext": _b64(ciphertext),
        }

    def decrypt_payload(self, envelope: dict[str, Any]) -> dict[str, Any]:
        if self._legacy_vault_key is None:
            raise RuntimeError("Legacy vault key is unavailable")
        aad = f"{DOMAIN}:{self.entry_id}:ledger-v1".encode("utf-8")
        try:
            plaintext = AESGCM(self._legacy_vault_key).decrypt(
                _unb64(str(envelope["nonce"])),
                _unb64(str(envelope["ciphertext"])),
                aad,
            )
            result = json.loads(plaintext.decode("utf-8"))
        except (InvalidTag, KeyError, ValueError, json.JSONDecodeError) as err:
            raise VaultDecryptionError(
                "The legacy encrypted Bitcoin ledger could not be authenticated"
            ) from err
        if not isinstance(result, dict):
            raise VaultDecryptionError("The decrypted ledger is not a JSON object")
        return deepcopy(result)
