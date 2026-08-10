"""Local ledger and public daily-price storage for Bitcoin Stack Tracker."""

from __future__ import annotations

import asyncio
import base64
import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    ALL_DEPOTS,
    DEFAULT_DEPOT_ID,
    DEFAULT_LONG_TERM_DAYS,
    DEFAULT_TAX_NOTE,
    HISTORY_STORAGE_KEY_PREFIX,
    STORAGE_KEY_PREFIX,
    STORAGE_SCHEMA_VERSION,
    STORAGE_VERSION,
)
from .crypto import (
    PasswordDecryptionError,
    PASSWORD_ENVELOPE_MODE,
    create_password_envelope,
    decrypt_password_envelope,
    encrypt_v3_payload_with_dek,
    is_password_envelope,
    password_kdf_from_envelope,
    password_envelope_needs_upgrade,
    kdf_security_profile,
    new_device_secret,
    reencrypt_password_payload,
    rewrap_password_envelope,
)
from .limits import (
    MAX_DEPOTS,
    MAX_GOALS,
    MAX_LEDGER_ENTRIES,
    MAX_NAME_LENGTH,
    MAX_NOTE_LENGTH,
    MAX_HISTORY_CURRENCIES,
    MAX_STATISTIC_POINTS_PER_SERIES,
)
from .fifo import fifo_result
from .migrations import migrate_ledger_data
from .models import btc_string, decimal_value, money_string, slugify
from .security import (
    BitcoinSecurityStore,
    ENCRYPTION_LEGACY,
    ENCRYPTION_NONE,
    ENCRYPTION_PASSWORD,
    VaultLockedError,
)


def _build_fifo_cache(
    entries: list[dict[str, Any]], depots: list[dict[str, Any]], long_term_days: int
) -> dict[str, dict[str, Any]]:
    """Build FIFO summaries in a worker thread, once per ledger revision."""
    cache = {
        ALL_DEPOTS: fifo_result(
            entries, None, long_term_days=long_term_days
        )
    }
    for depot in depots:
        depot_id = str(depot.get("id") or DEFAULT_DEPOT_ID)
        cache[depot_id] = fifo_result(
            entries, depot_id, long_term_days=long_term_days
        )
    return cache


def _normalized_utc_timestamp(value: Any) -> str:
    """Normalize a ledger timestamp to one canonical UTC ISO-8601 value."""
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _ledger_sort_key(row: dict[str, Any]) -> tuple[datetime, int, str]:
    try:
        parsed = datetime.fromisoformat(str(row.get("timestamp") or "").replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        parsed = datetime.max.replace(tzinfo=timezone.utc)
    return (
        parsed,
        1 if row.get("type") in {"sale", "expense"} else 0,
        str(row.get("id", "")),
    )


def _transaction_fingerprint(item: dict[str, Any]) -> tuple[str, ...]:
    """Return a stable duplicate key without retaining import-file metadata."""
    timestamp = str(item.get("timestamp") or "")
    try:
        timestamp = _normalized_utc_timestamp(timestamp)
    except (TypeError, ValueError):
        pass
    return (
        str(item.get("type") or ""),
        timestamp,
        str(item.get("depot_id") or DEFAULT_DEPOT_ID),
        btc_string(decimal_value(item.get("amount_btc"))),
        str(item.get("currency") or "").upper(),
        money_string(decimal_value(item.get("price"))),
        money_string(decimal_value(item.get("fee"))),
    )


class BitcoinLedgerStore:
    """Persist ledger, depots, goals, and holding-period settings.

    Password mode keeps the master password out of Home Assistant storage. The
    current format uses envelope encryption: a random AES-256 data key exists in
    RAM while unlocked; the password-derived key is used only to unwrap that data
    key. A separate 256-bit device-binding secret lives in Home Assistant Core's
    private .storage area and never belongs to the Tor/network add-on.
    """

    def __init__(
        self, hass: HomeAssistant, entry_id: str, security: BitcoinSecurityStore
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._store = Store[dict[str, Any]](
            hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}.{entry_id}"
        )
        self.security = security
        self._lock = asyncio.Lock()
        self._data: dict[str, Any] = self._empty_data()
        self._loaded = False
        self._locked = False
        self._setup_required = False
        self._session_key: bytes | None = None
        self._password_kdf: dict[str, Any] | None = None
        self._password_envelope: dict[str, Any] | None = None
        self._device_secret: bytes | None = None
        self._device_key_path = Path(
            hass.config.path(
                ".storage", "bitcoin_stack_tracker_device_keys", f"{entry_id}.key"
            )
        )
        self._fifo_cache: dict[str, dict[str, Any]] = {}

    def _read_device_secret(self) -> bytes:
        """Read the local 256-bit binding key without silently replacing it."""
        if not self._device_key_path.exists():
            raise PasswordDecryptionError(
                "The local device-binding key is missing; restore the matching Home Assistant backup"
            )
        try:
            value = base64.urlsafe_b64decode(
                self._device_key_path.read_text(encoding="ascii").strip().encode("ascii")
            )
        except Exception as err:
            raise PasswordDecryptionError("The local device-binding key is damaged") from err
        if len(value) != 32:
            raise PasswordDecryptionError("The local device-binding key has an invalid length")
        try:
            os.chmod(self._device_key_path, 0o600)
        except OSError:
            pass
        return value

    def _create_device_secret(self) -> bytes:
        """Create a per-portfolio device-binding key atomically with mode 0600."""
        self._device_key_path.parent.mkdir(parents=True, exist_ok=True)
        if self._device_key_path.exists():
            return self._read_device_secret()
        value = new_device_secret()
        encoded = base64.urlsafe_b64encode(value).decode("ascii")
        try:
            fd = os.open(
                self._device_key_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            return self._read_device_secret()
        try:
            with os.fdopen(fd, "w", encoding="ascii") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            self._device_key_path.unlink(missing_ok=True)
            raise
        return value

    async def _async_device_secret(self, *, create: bool) -> bytes:
        if self._device_secret is None:
            loader = self._create_device_secret if create else self._read_device_secret
            self._device_secret = await self.hass.async_add_executor_job(loader)
        return self._device_secret

    async def _async_remove_device_secret(self) -> None:
        self._device_secret = None
        path = self._device_key_path
        await self.hass.async_add_executor_job(lambda: path.unlink(missing_ok=True))

    @staticmethod
    def _empty_data() -> dict[str, Any]:
        return {
            "schema_version": STORAGE_SCHEMA_VERSION,
            "entries": [],
            "depots": [{"id": DEFAULT_DEPOT_ID, "name": "Main"}],
            "goals": [],
            "tax_settings": {
                "long_term_days": DEFAULT_LONG_TERM_DAYS,
                "note": DEFAULT_TAX_NOTE,
            },
            # Sensitive chart values are part of the ledger so password mode
            # encrypts them together with transactions, depots and goals.
            "chart_cache": {"revision": None, "data": {}},
        }

    @property
    def is_locked(self) -> bool:
        return self._locked

    @property
    def setup_required(self) -> bool:
        return self._setup_required

    @property
    def encryption_mode(self) -> str:
        return self.security.encryption_mode

    def require_unlocked(self) -> None:
        if self._locked:
            raise VaultLockedError("The Bitcoin portfolio vault is locked")

    async def async_load(
        self,
        *,
        initial_mode: str | None = None,
        initial_password: str | None = None,
    ) -> None:
        """Load the ledger, initialize an empty vault, or remain password-locked."""
        async with self._lock:
            if self._loaded:
                return
            loaded = await self._store.async_load()
            mode = initial_mode or self.security.encryption_mode

            if is_password_envelope(loaded):
                self._password_envelope = deepcopy(loaded)
                self._password_kdf = password_kdf_from_envelope(loaded)
                self._locked = True
                self._setup_required = False
                if self.security.encryption_mode != ENCRYPTION_PASSWORD:
                    await self.security.async_set_encryption_mode(ENCRYPTION_PASSWORD)
                if initial_password:
                    await self._async_unlock_without_lock(initial_password)
            elif isinstance(loaded, dict) and loaded.get("encrypted") is True:
                # Compatibility with 0.3's installation-key encryption.
                self._data = await self.hass.async_add_executor_job(
                    self.security.decrypt_payload, loaded
                )
                self._locked = False
                self._setup_required = False
                if self.security.encryption_mode != ENCRYPTION_LEGACY:
                    await self.security.async_set_encryption_mode(ENCRYPTION_LEGACY)
            elif isinstance(loaded, dict):
                self._data = loaded
                self._locked = False
                self._setup_required = False
                if mode == ENCRYPTION_PASSWORD and initial_password:
                    await self.security.async_set_encryption_mode(ENCRYPTION_PASSWORD)
                    await self._async_set_new_password_without_lock(initial_password)
                else:
                    if self.security.encryption_mode != ENCRYPTION_NONE:
                        await self.security.async_set_encryption_mode(ENCRYPTION_NONE)
            else:
                self._data = self._empty_data()
                if mode == ENCRYPTION_PASSWORD:
                    await self.security.async_set_encryption_mode(ENCRYPTION_PASSWORD)
                    if initial_password:
                        await self._async_set_new_password_without_lock(initial_password)
                    else:
                        self._locked = True
                        self._setup_required = True
                else:
                    await self.security.async_set_encryption_mode(ENCRYPTION_NONE)
                    self._locked = False

            if not self._locked:
                changed = self._normalize()
                if changed or loaded is None or initial_password:
                    await self._async_save()
                else:
                    await self._async_refresh_fifo_cache_without_lock()
            self._loaded = True

    async def _async_unlock_without_lock(self, password: str) -> None:
        """Authenticate the vault and keep only the random DEK in session RAM."""
        if self._password_envelope is None:
            raise PasswordDecryptionError("Encrypted ledger is missing")

        mode = str(self._password_envelope.get("encryption_mode") or "")
        device_secret: bytes | None = None
        if mode == PASSWORD_ENVELOPE_MODE:
            # Never silently create a replacement for an already-bound vault.
            device_secret = await self._async_device_secret(create=False)

        data, session_key = await self.hass.async_add_executor_job(
            partial(
                decrypt_password_envelope,
                self._password_envelope,
                password=password,
                entry_id=self.entry_id,
                device_secret=device_secret,
            )
        )
        self._data = data

        if password_envelope_needs_upgrade(self._password_envelope):
            # Only after successful legacy authentication create the independent
            # device secret and migrate to envelope encryption. This prevents a
            # copied old ledger from causing an unrelated binding key to appear.
            device_secret = await self._async_device_secret(create=True)
            envelope, session_key = await self.hass.async_add_executor_job(
                partial(
                    reencrypt_password_payload,
                    deepcopy(data),
                    password=password,
                    entry_id=self.entry_id,
                    device_secret=device_secret,
                )
            )
            self._password_envelope = envelope
            await self._store.async_save(envelope)

        self._password_kdf = password_kdf_from_envelope(self._password_envelope)
        self._session_key = session_key  # random DEK in v3; never the master password
        self._locked = False
        self._setup_required = False
        self._normalize()
        await self._async_refresh_fifo_cache_without_lock()

    async def _async_set_new_password_without_lock(self, password: str) -> None:
        """Create a device-bound v3 vault with an independent random DEK."""
        device_secret = await self._async_device_secret(create=True)
        envelope, dek = await self.hass.async_add_executor_job(
            partial(
                create_password_envelope,
                deepcopy(self._data),
                password=password,
                entry_id=self.entry_id,
                device_secret=device_secret,
            )
        )
        self._password_envelope = envelope
        self._password_kdf = password_kdf_from_envelope(envelope)
        self._session_key = dek
        self._locked = False
        self._setup_required = False

    async def async_initialize_password(self, password: str) -> None:
        async with self._lock:
            if not self._setup_required:
                raise ValueError("Password setup is not required")
            self._data = self._empty_data()
            await self._async_set_new_password_without_lock(password)
            await self.security.async_set_encryption_mode(ENCRYPTION_PASSWORD)
            await self._async_save()

    async def async_unlock(self, password: str) -> None:
        async with self._lock:
            if self.security.encryption_mode != ENCRYPTION_PASSWORD:
                self._locked = False
                return
            if self._setup_required:
                self._data = self._empty_data()
                await self._async_set_new_password_without_lock(password)
                await self._async_save()
                return
            if self._password_envelope is None:
                loaded = await self._store.async_load()
                if not is_password_envelope(loaded):
                    raise PasswordDecryptionError("Encrypted ledger is missing")
                self._password_envelope = deepcopy(loaded)
            await self._async_unlock_without_lock(password)

    async def async_lock(self) -> None:
        """Drop plaintext data, DEK, KDF metadata and device secret from RAM."""
        async with self._lock:
            if self.security.encryption_mode != ENCRYPTION_PASSWORD:
                return
            self._data = self._empty_data()
            self._session_key = None
            self._password_kdf = None
            self._device_secret = None
            self._fifo_cache = {}
            self._locked = True

    async def async_enable_password(self, password: str) -> None:
        async with self._lock:
            self.require_unlocked()
            await self._async_set_new_password_without_lock(password)
            await self.security.async_set_encryption_mode(ENCRYPTION_PASSWORD)
            await self._async_save()

    async def async_disable_password(self) -> None:
        async with self._lock:
            self.require_unlocked()
            await self.security.async_set_encryption_mode(ENCRYPTION_NONE)
            self._password_envelope = None
            self._password_kdf = None
            self._session_key = None
            self._locked = False
            await self._async_save()
            await self._async_remove_device_secret()

    async def async_change_password(self, current_password: str, new_password: str) -> None:
        async with self._lock:
            if self.security.encryption_mode != ENCRYPTION_PASSWORD:
                raise ValueError("Password encryption is not enabled")
            if self._password_envelope is None:
                loaded = await self._store.async_load()
                if not is_password_envelope(loaded):
                    raise PasswordDecryptionError("Encrypted ledger is missing")
                self._password_envelope = deepcopy(loaded)

            old_mode = str(self._password_envelope.get("encryption_mode") or "")
            old_device_secret = (
                await self._async_device_secret(create=False)
                if old_mode == PASSWORD_ENVELOPE_MODE else None
            )
            payload, old_key = await self.hass.async_add_executor_job(
                partial(
                    decrypt_password_envelope,
                    self._password_envelope,
                    password=current_password,
                    entry_id=self.entry_id,
                    device_secret=old_device_secret,
                )
            )
            device_secret = await self._async_device_secret(create=True)
            if old_mode == PASSWORD_ENVELOPE_MODE:
                envelope = await self.hass.async_add_executor_job(
                    partial(
                        rewrap_password_envelope,
                        payload,
                        dek=old_key,
                        new_password=new_password,
                        entry_id=self.entry_id,
                        device_secret=device_secret,
                    )
                )
                dek = old_key
            else:
                envelope, dek = await self.hass.async_add_executor_job(
                    partial(
                        create_password_envelope,
                        payload,
                        password=new_password,
                        entry_id=self.entry_id,
                        device_secret=device_secret,
                    )
                )
            self._data = payload
            self._password_envelope = envelope
            self._password_kdf = password_kdf_from_envelope(envelope)
            self._session_key = dek
            self._locked = False
            await self._store.async_save(envelope)

    async def _async_refresh_fifo_cache_without_lock(self) -> None:
        """Refresh expensive FIFO summaries outside Home Assistant's event loop."""
        self.require_unlocked()
        entries = deepcopy(self._data.get("entries", []))
        depots = deepcopy(self._data.get("depots", []))
        days = int(
            self._data.get("tax_settings", {}).get(
                "long_term_days", DEFAULT_LONG_TERM_DAYS
            )
        )
        self._fifo_cache = await self.hass.async_add_executor_job(
            _build_fifo_cache, entries, depots, days
        )

    def password_crypto_status(self) -> dict[str, Any] | None:
        """Return non-secret cryptographic architecture details for owner UI."""
        if self.security.encryption_mode != ENCRYPTION_PASSWORD or self._password_kdf is None:
            return None
        profile = kdf_security_profile(self._password_kdf)
        envelope = self._password_envelope or {}
        key_wrap = envelope.get("key_wrap") if isinstance(envelope, dict) else {}
        return {
            "cipher": "AES-256-GCM",
            "key_bits": 256,
            "nonce_bits": 96,
            "tag_bits": 128,
            "aad": True,
            "envelope_encryption": str(envelope.get("encryption_mode") or "") == PASSWORD_ENVELOPE_MODE,
            "data_key_bits": 256,
            "key_wrap": "AES-256-GCM",
            "key_derivation_separation": "HKDF-SHA-512",
            "device_bound": bool(isinstance(key_wrap, dict) and key_wrap.get("device_bound")),
            "device_key_bits": 256,
            "session_secret": "random-data-encryption-key",
            "kdf": profile,
        }

    def fifo_summary(self, depot_id: str | None = None) -> dict[str, Any]:
        """Return a precomputed FIFO summary without blocking the event loop."""
        self.require_unlocked()
        key = depot_id or ALL_DEPOTS
        summary = self._fifo_cache.get(key)
        if summary is None:
            raise RuntimeError("FIFO cache is unavailable")
        return summary

    async def _async_save(self) -> None:
        self.require_unlocked()
        await self._async_refresh_fifo_cache_without_lock()
        mode = self.security.encryption_mode
        if mode == ENCRYPTION_PASSWORD:
            if self._session_key is None or self._password_envelope is None:
                raise VaultLockedError("Password vault data key is unavailable")
            if str(self._password_envelope.get("encryption_mode") or "") != PASSWORD_ENVELOPE_MODE:
                raise VaultLockedError("Password vault must be migrated before saving")
            envelope = await self.hass.async_add_executor_job(
                partial(
                    encrypt_v3_payload_with_dek,
                    deepcopy(self._data),
                    envelope=self._password_envelope,
                    dek=self._session_key,
                    context=f"ledger:{self.entry_id}",
                )
            )
            self._password_envelope = deepcopy(envelope)
            await self._store.async_save(envelope)
        elif mode == ENCRYPTION_LEGACY:
            envelope = await self.hass.async_add_executor_job(
                self.security.encrypt_payload, deepcopy(self._data)
            )
            await self._store.async_save(envelope)
        else:
            await self._store.async_save(deepcopy(self._data))

    def _normalize(self) -> bool:
        """Migrate every published local ledger format without data loss."""
        migrated, changed = migrate_ledger_data(self._data)
        self._data = migrated
        return changed

    @property
    def entries(self) -> list[dict[str, Any]]:
        self.require_unlocked()
        return deepcopy(self._data.get("entries", []))

    @property
    def depots(self) -> list[dict[str, Any]]:
        self.require_unlocked()
        return deepcopy(self._data.get("depots", []))

    @property
    def goals(self) -> list[dict[str, Any]]:
        self.require_unlocked()
        return deepcopy(self._data.get("goals", []))

    @property
    def tax_settings(self) -> dict[str, Any]:
        self.require_unlocked()
        return deepcopy(self._data.get("tax_settings", {}))

    @property
    def chart_cache(self) -> dict[str, Any]:
        """Return locally persisted sensitive daily portfolio chart values."""
        self.require_unlocked()
        cache = self._data.get("chart_cache", {})
        return deepcopy(cache if isinstance(cache, dict) else {})

    async def async_set_chart_cache(self, revision: str, data: dict[str, Any]) -> None:
        """Persist chart values inside the ledger (encrypted in password mode)."""
        async with self._lock:
            self.require_unlocked()
            self._data["chart_cache"] = {
                "revision": str(revision),
                "data": deepcopy(data),
            }
            await self._async_save()

    def has_depot(self, depot_id: str) -> bool:
        self.require_unlocked()
        return any(item.get("id") == depot_id for item in self._data.get("depots", []))
    async def async_add_purchase(
        self, *, timestamp: datetime, amount_btc: Any, currency: str, price: Any,
        fee: Any = 0, note: str = "", depot_id: str = DEFAULT_DEPOT_ID
    ) -> dict[str, Any]:
        return await self._async_add_transaction(
            kind="purchase", timestamp=timestamp, amount_btc=amount_btc,
            currency=currency, price=price, fee=fee, note=note, depot_id=depot_id,
        )

    async def async_add_sale(
        self, *, timestamp: datetime, amount_btc: Any, currency: str, price: Any,
        fee: Any = 0, note: str = "", depot_id: str = DEFAULT_DEPOT_ID
    ) -> dict[str, Any]:
        return await self._async_add_transaction(
            kind="sale", timestamp=timestamp, amount_btc=amount_btc,
            currency=currency, price=price, fee=fee, note=note, depot_id=depot_id,
        )

    async def _async_add_transaction(
        self, *, kind: str, timestamp: datetime, amount_btc: Any, currency: str,
        price: Any, fee: Any, note: str, depot_id: str
    ) -> dict[str, Any]:
        if not self.has_depot(depot_id):
            raise ValueError("Unknown depot")
        amount = decimal_value(amount_btc)
        if amount <= 0 or decimal_value(price) <= 0:
            raise ValueError("Amount and price must be greater than zero")
        clean_note = str(note).strip()[:MAX_NOTE_LENGTH]
        item = {
            "id": uuid4().hex,
            "type": kind,
            "timestamp": _normalized_utc_timestamp(timestamp),
            "depot_id": depot_id,
            "amount_btc": btc_string(amount),
            "currency": currency.upper(),
            "price": money_string(decimal_value(price)),
            "fee": money_string(decimal_value(fee)),
            "note": clean_note,
        }
        await self._async_append(item)
        return deepcopy(item)

    async def async_add_stack(
        self, *, timestamp: datetime, amount_btc: Any, note: str = "",
        depot_id: str = DEFAULT_DEPOT_ID
    ) -> dict[str, Any]:
        if not self.has_depot(depot_id):
            raise ValueError("Unknown depot")
        amount = decimal_value(amount_btc)
        if amount <= 0:
            raise ValueError("Amount must be greater than zero")
        clean_note = str(note).strip()[:MAX_NOTE_LENGTH]
        item = {
            "id": uuid4().hex,
            "type": "stack",
            "timestamp": _normalized_utc_timestamp(timestamp),
            "depot_id": depot_id,
            "amount_btc": btc_string(amount),
            "note": clean_note,
        }
        await self._async_append(item)
        return deepcopy(item)

    async def _async_append(self, item: dict[str, Any]) -> None:
        async with self._lock:
            if len(self._data.get("entries", [])) >= MAX_LEDGER_ENTRIES:
                raise ValueError(f"A maximum of {MAX_LEDGER_ENTRIES} ledger entries is allowed")
            self._data.setdefault("entries", []).append(item)
            self._data["entries"].sort(key=_ledger_sort_key)
            await self._async_save()

    async def async_bulk_import(
        self, transactions: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Validate, de-duplicate and persist a reviewed import in one write."""
        if not isinstance(transactions, list) or not transactions:
            raise ValueError("At least one reviewed transaction is required")
        if len(transactions) > 5_000:
            raise ValueError("A maximum of 5000 transactions can be imported at once")

        async with self._lock:
            self.require_unlocked()
            current = list(self._data.get("entries", []))
            depots = {str(item.get("id")) for item in self._data.get("depots", [])}
            existing_fingerprints = {_transaction_fingerprint(item) for item in current}
            pending_fingerprints: set[tuple[str, ...]] = set()
            additions: list[dict[str, Any]] = []
            duplicates = 0

            for index, raw in enumerate(transactions, start=1):
                if not isinstance(raw, dict):
                    raise ValueError(f"Import row {index} is invalid")
                kind = str(raw.get("type") or "").strip().lower()
                if kind not in {"purchase", "sale", "expense"}:
                    raise ValueError(f"Import row {index}: unknown transaction type")
                depot_id = str(raw.get("depot_id") or DEFAULT_DEPOT_ID)
                if depot_id not in depots:
                    raise ValueError(f"Import row {index}: unknown depot")
                timestamp_raw = str(raw.get("timestamp") or "").strip()
                try:
                    timestamp = datetime.fromisoformat(
                        timestamp_raw.replace("Z", "+00:00")
                    )
                except ValueError as err:
                    raise ValueError(f"Import row {index}: invalid timestamp") from err
                amount = decimal_value(raw.get("amount_btc"))
                price = decimal_value(raw.get("price"))
                fee = decimal_value(raw.get("fee"))
                currency = str(raw.get("currency") or "").strip().upper()[:16]
                if amount <= 0:
                    raise ValueError(f"Import row {index}: amount must be greater than zero")
                if kind != "expense" and price <= 0:
                    raise ValueError(f"Import row {index}: price must be greater than zero")
                if fee < 0:
                    raise ValueError(f"Import row {index}: fee must not be negative")
                if kind != "expense" and not currency:
                    raise ValueError(f"Import row {index}: currency is required")
                expense_has_fiat_value = kind == "expense" and bool(currency) and price > 0
                if kind == "expense" and (bool(currency) != (price > 0)):
                    raise ValueError(
                        f"Import row {index}: expense currency and price must be supplied together"
                    )
                item = {
                    "id": uuid4().hex,
                    "type": kind,
                    "timestamp": _normalized_utc_timestamp(timestamp),
                    "depot_id": depot_id,
                    "amount_btc": btc_string(amount),
                    "note": str(raw.get("note") or "").strip()[:MAX_NOTE_LENGTH],
                }
                if kind != "expense" or expense_has_fiat_value:
                    item.update({
                        "currency": currency,
                        "price": money_string(price),
                        "fee": money_string(fee),
                    })
                fingerprint = _transaction_fingerprint(item)
                if fingerprint in existing_fingerprints or fingerprint in pending_fingerprints:
                    duplicates += 1
                    continue
                pending_fingerprints.add(fingerprint)
                additions.append(item)

            if not additions:
                return {"imported": 0, "duplicates": duplicates, "entries": []}
            if len(current) + len(additions) > MAX_LEDGER_ENTRIES:
                raise ValueError(
                    f"A maximum of {MAX_LEDGER_ENTRIES} ledger entries is allowed"
                )

            combined = current + additions
            combined.sort(key=_ledger_sort_key)
            days = int(
                self._data.get("tax_settings", {}).get(
                    "long_term_days", DEFAULT_LONG_TERM_DAYS
                )
            )
            fifo_cache = await self.hass.async_add_executor_job(
                _build_fifo_cache, combined, deepcopy(self._data.get("depots", [])), days
            )
            oversold = [
                depot_id for depot_id, result in fifo_cache.items()
                if depot_id != ALL_DEPOTS and decimal_value(result.get("oversold_btc")) > 0
            ]
            if oversold:
                raise ValueError(
                    "Import contains a sale before enough BTC is available in depot: "
                    + ", ".join(sorted(oversold))
                )

            self._data["entries"] = combined
            await self._async_save()
            return {
                "imported": len(additions),
                "duplicates": duplicates,
                "entries": deepcopy(additions),
            }

    async def async_add_depot(self, name: str) -> dict[str, Any]:
        clean_name = name.strip()[:MAX_NAME_LENGTH]
        if not clean_name:
            raise ValueError("Depot name is empty")
        base = slugify(clean_name, "depot")
        async with self._lock:
            if len(self._data.get("depots", [])) >= MAX_DEPOTS:
                raise ValueError(f"A maximum of {MAX_DEPOTS} depots is allowed")
            existing = {item.get("id") for item in self._data.get("depots", [])}
            depot_id = base
            counter = 2
            while depot_id in existing:
                depot_id = f"{base}_{counter}"
                counter += 1
            item = {"id": depot_id, "name": clean_name}
            self._data.setdefault("depots", []).append(item)
            await self._async_save()
        return deepcopy(item)

    async def async_delete_depot(self, depot_id: str) -> bool:
        if depot_id == DEFAULT_DEPOT_ID:
            return False
        async with self._lock:
            if any(item.get("depot_id") == depot_id for item in self._data.get("entries", [])):
                raise ValueError("Depot contains ledger entries")
            before = len(self._data.get("depots", []))
            self._data["depots"] = [
                item for item in self._data.get("depots", []) if item.get("id") != depot_id
            ]
            self._data["goals"] = [
                item for item in self._data.get("goals", []) if item.get("depot_id") != depot_id
            ]
            changed = len(self._data["depots"]) != before
            if changed:
                await self._async_save()
            return changed

    async def async_add_goal(
        self, *, name: str, amount_btc: Any, depot_id: str = ALL_DEPOTS,
        currency: str = "EUR"
    ) -> dict[str, Any]:
        amount = decimal_value(amount_btc)
        if amount <= 0:
            raise ValueError("Goal must be greater than zero")
        async with self._lock:
            if depot_id != ALL_DEPOTS and not any(
                item.get("id") == depot_id for item in self._data.get("depots", [])
            ):
                raise ValueError("Unknown depot")
            if len(self._data.get("goals", [])) >= MAX_GOALS:
                raise ValueError(f"A maximum of {MAX_GOALS} goals is allowed")
            item = {
                "id": uuid4().hex,
                "name": name.strip()[:MAX_NAME_LENGTH] or f"{btc_string(amount)} BTC",
                "amount_btc": btc_string(amount),
                "depot_id": depot_id,
                "currency": str(currency or "EUR").upper(),
            }
            self._data.setdefault("goals", []).append(item)
            await self._async_save()
        return deepcopy(item)

    async def async_delete_goal(self, goal_id: str) -> bool:
        async with self._lock:
            before = len(self._data.get("goals", []))
            self._data["goals"] = [
                item for item in self._data.get("goals", []) if item.get("id") != goal_id
            ]
            changed = len(self._data["goals"]) != before
            if changed:
                await self._async_save()
            return changed

    async def async_update_goal(
        self, goal_id: str, *, amount_btc: Any | None = None,
        name: str | None = None, depot_id: str | None = None,
        currency: str | None = None
    ) -> bool:
        amount = decimal_value(amount_btc) if amount_btc is not None else None
        if amount is not None and amount <= 0:
            raise ValueError("Goal must be greater than zero")
        if depot_id is not None and depot_id != ALL_DEPOTS and not self.has_depot(depot_id):
            raise ValueError("Unknown depot")
        async with self._lock:
            for item in self._data.get("goals", []):
                if item.get("id") != goal_id:
                    continue
                if amount is not None:
                    item["amount_btc"] = btc_string(amount)
                if name is not None and name.strip():
                    item["name"] = name.strip()[:MAX_NAME_LENGTH]
                if depot_id is not None:
                    item["depot_id"] = depot_id
                if currency is not None and currency.strip():
                    item["currency"] = currency.strip().upper()
                await self._async_save()
                return True
            return False

    async def async_set_tax_settings(self, *, long_term_days: int, note: str) -> dict[str, Any]:
        days = int(long_term_days)
        if days < 1:
            raise ValueError("Long-term holding period must be at least one day")
        async with self._lock:
            self._data["tax_settings"] = {
                "long_term_days": days,
                "note": str(note).strip()[:MAX_NOTE_LENGTH],
            }
            await self._async_save()
            return deepcopy(self._data["tax_settings"])

    async def async_ensure_legacy_goal(self, amount_btc: Any, currency: str = "EUR") -> None:
        amount = decimal_value(amount_btc)
        if amount <= 0 or self._data.get("goals"):
            return
        await self.async_add_goal(
            name=f"{btc_string(amount)} BTC", amount_btc=amount, currency=currency
        )

    async def async_delete_all_entries(self) -> int:
        """Delete the complete ledger while keeping depots, goals and settings."""
        async with self._lock:
            self.require_unlocked()
            deleted = len(self._data.get("entries", []))
            if deleted:
                self._data["entries"] = []
                self._data["chart_cache"] = {}
                await self._async_save()
            return deleted

    async def async_update_entry(self, item_id: str, replacement: dict[str, Any]) -> bool:
        """Replace one existing ledger entry while preserving its stable id."""
        async with self._lock:
            self.require_unlocked()
            entries = list(self._data.get("entries", []))
            index = next((idx for idx, item in enumerate(entries) if item.get("id") == item_id), None)
            if index is None:
                return False
            updated = deepcopy(replacement)
            updated["id"] = item_id
            updated["note"] = str(updated.get("note") or "").strip()[:MAX_NOTE_LENGTH]
            if updated.get("timestamp"):
                updated["timestamp"] = _normalized_utc_timestamp(updated["timestamp"])
            fingerprint = _transaction_fingerprint(updated)
            if any(
                idx != index and _transaction_fingerprint(item) == fingerprint
                for idx, item in enumerate(entries)
            ):
                raise ValueError("Another ledger entry already has the same transaction values")
            entries[index] = updated
            entries.sort(key=_ledger_sort_key)
            self._data["entries"] = entries
            self._data["chart_cache"] = {}
            await self._async_save()
            return True

    async def async_delete(self, item_id: str) -> bool:
        async with self._lock:
            before = len(self._data.get("entries", []))
            self._data["entries"] = [
                item for item in self._data.get("entries", []) if item.get("id") != item_id
            ]
            changed = len(self._data["entries"]) != before
            if changed:
                await self._async_save()
            return changed

    async def async_export(self) -> dict[str, Any]:
        async with self._lock:
            self.require_unlocked()
            return deepcopy(self._data)

    async def async_replace(self, data: dict[str, Any]) -> None:
        """Replace the complete ledger after a validated backup import."""
        if not isinstance(data, dict):
            raise ValueError("Backup ledger must be an object")
        async with self._lock:
            self.require_unlocked()
            if len(data.get("entries", [])) > MAX_LEDGER_ENTRIES:
                raise ValueError("Backup contains too many ledger entries")
            if len(data.get("depots", [])) > MAX_DEPOTS:
                raise ValueError("Backup contains too many depots")
            if len(data.get("goals", [])) > MAX_GOALS:
                raise ValueError("Backup contains too many goals")
            self._data = deepcopy(data)
            self._normalize()
            await self._async_save()

    async def async_remove(self) -> None:
        """Remove the ledger storage after config-entry deletion."""
        await self._store.async_remove()


class BitcoinHistoryStore:
    """Persist downloaded daily prices and privacy-scrubbed sync metadata."""

    @staticmethod
    def _scrub_source_metadata(value: Any) -> Any:
        """Remove legacy fields that can reveal private node addresses."""
        if isinstance(value, dict):
            return {
                str(key): BitcoinHistoryStore._scrub_source_metadata(item)
                for key, item in value.items()
                if str(key) != "configured_base_url"
            }
        if isinstance(value, list):
            return [BitcoinHistoryStore._scrub_source_metadata(item) for item in value]
        return value

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = Store[dict[str, Any]](
            hass, STORAGE_VERSION, f"{HISTORY_STORAGE_KEY_PREFIX}.{entry_id}"
        )
        self._lock = asyncio.Lock()
        self.sync_lock = asyncio.Lock()
        self._data: dict[str, Any] = {
            "prices": {},
            "price_samples": {},
            "market_candles": {},
            "last_sync": None,
            "errors": [],
            "statistics_hashes": {},
            "statistics_ids": [],
            "bootstrap_complete": {},
            "source_metadata": {},
        }

    async def async_load(self) -> None:
        loaded = await self._store.async_load()
        scrubbed_legacy_metadata = False
        if isinstance(loaded, dict):
            self._data = loaded
            original_metadata = self._data.get("source_metadata", {})
            scrubbed_metadata = self._scrub_source_metadata(original_metadata)
            scrubbed_legacy_metadata = scrubbed_metadata != original_metadata
            self._data["source_metadata"] = scrubbed_metadata
        self._data.setdefault("prices", {})
        self._data.setdefault("price_samples", {})
        self._data.setdefault("market_candles", {})
        self._data.setdefault("last_sync", None)
        self._data.setdefault("errors", [])
        self._data.setdefault("statistics_hashes", {})
        self._data.setdefault("statistics_ids", [])
        self._data.setdefault("bootstrap_complete", {})
        self._data.setdefault("source_metadata", {})
        if scrubbed_legacy_metadata:
            await self._store.async_save(self._data)

    @property
    def data(self) -> dict[str, Any]:
        return deepcopy(self._data)

    async def async_merge_prices(self, currency: str, values: dict[str, float]) -> None:
        async with self._lock:
            prices = self._data.setdefault("prices", {})
            currency = currency.upper()
            if currency not in prices and len(prices) >= MAX_HISTORY_CURRENCIES:
                raise ValueError(
                    f"A maximum of {MAX_HISTORY_CURRENCIES} history currencies is allowed"
                )
            target = prices.setdefault(currency, {})
            target.update(
                {str(day): float(price) for day, price in values.items() if float(price) > 0}
            )
            # Keep every valid daily value. Chart range controls only affect
            # display, never the durable local cache.
            self._data["prices"][currency] = dict(sorted(target.items()))
            await self._store.async_save(self._data)


    @staticmethod
    def _sample_time(value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _bucket_key(moment: datetime, minutes: int) -> str:
        seconds = max(60, int(minutes) * 60)
        bucket = int(moment.timestamp()) // seconds * seconds
        return datetime.fromtimestamp(bucket, tz=timezone.utc).isoformat().replace("+00:00", "Z")

    @classmethod
    def _compact_price_samples(
        cls, values: dict[str, float], *, now: datetime | None = None
    ) -> dict[str, float]:
        """Keep recent prices dense and progressively thin older samples.

        The durable daily cache remains separate. Fine-grained samples stay
        progressively compacted internally, while the dashboard resamples a
        requested time window to one uniform interval before drawing it.
        """
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        buckets: dict[tuple[int, int], tuple[datetime, float]] = {}
        for raw_time, raw_price in values.items():
            moment = cls._sample_time(str(raw_time))
            try:
                price = float(raw_price)
            except (TypeError, ValueError):
                continue
            if moment is None or price <= 0:
                continue
            age = max(timedelta(0), current - moment)
            if age <= timedelta(hours=60):
                minutes = 5
            elif age <= timedelta(hours=180):
                minutes = 15
            elif age <= timedelta(days=15):
                minutes = 30
            elif age <= timedelta(days=30):
                minutes = 60
            elif age <= timedelta(days=60):
                minutes = 120
            elif age <= timedelta(days=120):
                minutes = 240
            elif age <= timedelta(days=500):
                minutes = 720
            elif age <= timedelta(days=720):
                minutes = 1440
            else:
                continue
            seconds = minutes * 60
            bucket = int(moment.timestamp()) // seconds
            key = (minutes, bucket)
            previous = buckets.get(key)
            if previous is None or moment >= previous[0]:
                buckets[key] = (moment, price)
        compacted = {
            cls._bucket_key(moment, minutes): price
            for (minutes, _bucket), (moment, price) in buckets.items()
        }
        return dict(sorted(compacted.items()))

    async def async_add_price_samples(
        self, prices: dict[str, float], timestamp: str | datetime | None = None
    ) -> bool:
        """Persist one five-minute live-price sample per currency when available."""
        if not prices:
            return False
        if isinstance(timestamp, datetime):
            moment = timestamp
        elif timestamp:
            moment = self._sample_time(str(timestamp))
        else:
            moment = datetime.now(timezone.utc)
        if moment is None:
            moment = datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        moment = moment.astimezone(timezone.utc)
        sample_key = self._bucket_key(moment, 5)

        async with self._lock:
            samples = self._data.setdefault("price_samples", {})
            changed = False
            for currency, raw_price in prices.items():
                try:
                    price = float(raw_price)
                except (TypeError, ValueError):
                    continue
                code = str(currency).upper()
                if price <= 0:
                    continue
                if code not in samples and len(samples) >= MAX_HISTORY_CURRENCIES:
                    continue
                target = samples.setdefault(code, {})
                # One write per five-minute bucket keeps Home Assistant storage
                # bounded even when the live coordinator runs every minute.
                if sample_key in target:
                    continue
                target[sample_key] = price
                samples[code] = self._compact_price_samples(target, now=moment)
                changed = True
            if changed:
                await self._store.async_save(self._data)
            return changed

    async def async_merge_price_samples(
        self, currency: str, values: dict[str, float]
    ) -> int:
        """Merge historical intraday samples and re-apply adaptive compaction."""
        if not isinstance(values, dict) or not values:
            return 0
        code = str(currency).upper()
        async with self._lock:
            samples = self._data.setdefault("price_samples", {})
            if code not in samples and len(samples) >= MAX_HISTORY_CURRENCIES:
                return 0
            target = samples.setdefault(code, {})
            before = dict(target)
            for raw_time, raw_price in values.items():
                try:
                    price = float(raw_price)
                except (TypeError, ValueError):
                    continue
                if self._sample_time(str(raw_time)) is not None and price > 0:
                    # Never replace a locally sampled multi-provider quote with
                    # the single-provider Kraken seed for the same bucket.
                    target.setdefault(str(raw_time), price)
            samples[code] = self._compact_price_samples(target)
            changed = sum(
                1
                for key, value in samples[code].items()
                if before.get(key) != value
            )
            if samples[code] != before:
                await self._store.async_save(self._data)
            return changed


    async def async_merge_market_candles(
        self, currency: str, interval_minutes: int, values: dict[str, float]
    ) -> int:
        """Persist one exact exchange candle tier without mixing resolutions.

        Each supported chart range has its own provider-native interval. Keeping
        those tiers separate prevents a 30-day chart from silently falling back
        to daily points or reusing a coarser 12-hour seed.
        """
        if not isinstance(values, dict) or not values:
            return 0
        code = str(currency).upper()
        interval = int(interval_minutes)
        if interval not in {5, 15, 30, 60, 120, 240, 720, 1440}:
            raise ValueError(f"Unsupported market candle interval: {interval}")
        async with self._lock:
            all_candles = self._data.setdefault("market_candles", {})
            if code not in all_candles and len(all_candles) >= MAX_HISTORY_CURRENCIES:
                return 0
            tiers = all_candles.setdefault(code, {})
            key = str(interval)
            clean: dict[str, float] = {}
            for raw_time, raw_price in values.items():
                moment = self._sample_time(str(raw_time))
                try:
                    price = float(raw_price)
                except (TypeError, ValueError):
                    continue
                if moment is None or price <= 0:
                    continue
                clean[moment.isoformat().replace("+00:00", "Z")] = price
            # Provider requests are deliberately bounded (720/1000 rows). Replace
            # the tier atomically so stale candles from an older request cannot
            # leave holes or mixed cadence in the selected chart.
            ordered = dict(sorted(clean.items(), key=lambda item: self._sample_time(item[0]) or datetime.min.replace(tzinfo=timezone.utc)))
            previous = tiers.get(key, {}) if isinstance(tiers.get(key), dict) else {}
            tiers[key] = ordered
            changed = sum(1 for stamp, price in ordered.items() if previous.get(stamp) != price)
            changed += sum(1 for stamp in previous if stamp not in ordered)
            if previous != ordered:
                await self._store.async_save(self._data)
            return changed

    def market_candles_for_days(
        self, history_days: int, interval_minutes: int
    ) -> dict[str, dict[str, float]]:
        """Return only the exact candle tier requested by the current chart."""
        days = int(history_days)
        interval = int(interval_minutes)
        if days <= 0 or interval not in {5, 15, 30, 60, 120, 240, 720, 1440}:
            return {}
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=max(days, 1))
        result: dict[str, dict[str, float]] = {}
        for currency, tiers in self._data.get("market_candles", {}).items():
            if not isinstance(tiers, dict):
                continue
            values = tiers.get(str(interval), {})
            if not isinstance(values, dict):
                continue
            selected: dict[str, float] = {}
            for raw_time, raw_price in values.items():
                moment = self._sample_time(str(raw_time))
                try:
                    price = float(raw_price)
                except (TypeError, ValueError):
                    continue
                if moment is None or moment < cutoff or price <= 0:
                    continue
                selected[str(raw_time)] = price
            if selected:
                result[str(currency).upper()] = dict(sorted(selected.items(), key=lambda item: self._sample_time(item[0]) or now))
        return result

    def price_samples_for_days(self, history_days: int) -> dict[str, dict[str, float]]:
        """Return already-adaptive samples without flattening all tiers to one grid."""
        days = int(history_days)
        if days <= 0 or days > 731:
            return {}
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=max(days, 1))
        result: dict[str, dict[str, float]] = {}
        for currency, values in self._data.get("price_samples", {}).items():
            if not isinstance(values, dict):
                continue
            selected: dict[str, float] = {}
            for raw_time, raw_price in values.items():
                moment = self._sample_time(str(raw_time))
                try:
                    price = float(raw_price)
                except (TypeError, ValueError):
                    continue
                if moment is None or moment < cutoff or price <= 0:
                    continue
                selected[str(raw_time)] = price
            if selected:
                result[str(currency).upper()] = dict(
                    sorted(selected.items(), key=lambda item: self._sample_time(item[0]) or now)
                )
        return result

    async def async_set_source_state(
        self,
        currency: str,
        *,
        bootstrap_complete: bool,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Remember full-history completion so later syncs are incremental."""
        async with self._lock:
            code = str(currency).upper()
            self._data.setdefault("bootstrap_complete", {})[code] = bool(
                bootstrap_complete
            )
            if metadata is not None:
                self._data.setdefault("source_metadata", {})[code] = self._scrub_source_metadata(
                    deepcopy(metadata)
                )
            await self._store.async_save(self._data)

    async def async_set_statistics_state(
        self, hashes: dict[str, str], statistic_ids: list[str]
    ) -> None:
        async with self._lock:
            self._data["statistics_hashes"] = dict(hashes)
            self._data["statistics_ids"] = sorted(set(statistic_ids))
            await self._store.async_save(self._data)

    async def async_set_sync_status(self, timestamp: str, errors: list[str]) -> None:
        async with self._lock:
            self._data["last_sync"] = timestamp
            self._data["errors"] = list(errors)
            await self._store.async_save(self._data)

    async def async_replace(self, data: dict[str, Any]) -> None:
        """Replace public price history from an authenticated backup."""
        if not isinstance(data, dict):
            raise ValueError("Backup history must be an object")
        async with self._lock:
            prices = data.get("prices", {})
            if not isinstance(prices, dict):
                raise ValueError("Backup history prices are invalid")
            normalized: dict[str, dict[str, float]] = {}
            for currency, values in list(prices.items())[:MAX_HISTORY_CURRENCIES]:
                if not isinstance(values, dict):
                    continue
                clean = {
                    str(day): float(price)
                    for day, price in values.items()
                    if float(price) > 0
                }
                normalized[str(currency).upper()] = dict(sorted(clean.items()))
            raw_samples = data.get("price_samples", {})
            normalized_samples: dict[str, dict[str, float]] = {}
            if isinstance(raw_samples, dict):
                for currency, values in list(raw_samples.items())[:MAX_HISTORY_CURRENCIES]:
                    if not isinstance(values, dict):
                        continue
                    normalized_samples[str(currency).upper()] = self._compact_price_samples(
                        values
                    )
            normalized_candles: dict[str, dict[str, dict[str, float]]] = {}
            raw_candles = data.get("market_candles", {})
            if isinstance(raw_candles, dict):
                for currency, tiers in list(raw_candles.items())[:MAX_HISTORY_CURRENCIES]:
                    if not isinstance(tiers, dict):
                        continue
                    clean_tiers: dict[str, dict[str, float]] = {}
                    for interval, values in tiers.items():
                        try:
                            interval_int = int(interval)
                        except (TypeError, ValueError):
                            continue
                        if interval_int not in {5, 15, 30, 60, 120, 240, 720, 1440} or not isinstance(values, dict):
                            continue
                        clean_values: dict[str, float] = {}
                        for raw_time, raw_price in values.items():
                            moment = self._sample_time(str(raw_time))
                            try:
                                price = float(raw_price)
                            except (TypeError, ValueError):
                                continue
                            if moment is not None and price > 0:
                                clean_values[moment.isoformat().replace("+00:00", "Z")] = price
                        clean_tiers[str(interval_int)] = dict(sorted(clean_values.items()))
                    if clean_tiers:
                        normalized_candles[str(currency).upper()] = clean_tiers
            self._data = {
                "prices": normalized,
                "price_samples": normalized_samples,
                "market_candles": normalized_candles,
                "last_sync": data.get("last_sync"),
                "errors": list(data.get("errors", [])),
                "statistics_hashes": {},
                "statistics_ids": [],
                "bootstrap_complete": {
                    str(code).upper(): bool(value)
                    for code, value in dict(data.get("bootstrap_complete", {})).items()
                },
                "source_metadata": self._scrub_source_metadata(
                    deepcopy(data.get("source_metadata", {}))
                )
                if isinstance(data.get("source_metadata"), dict)
                else {},
            }
            await self._store.async_save(self._data)

    async def async_remove(self) -> None:
        """Remove cached public history after config-entry deletion."""
        await self._store.async_remove()
