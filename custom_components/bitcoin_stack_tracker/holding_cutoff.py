"""Holding-period cutoff support for Bitcoin Stack Tracker.

The feature keeps existing FIFO status compatibility: acquisitions on or after
an optional cutoff remain in the established ``short_term`` bucket and receive
no future long-term date.
"""

from __future__ import annotations

from contextvars import ContextVar
from copy import deepcopy
from datetime import date, datetime, timezone
import re
import sys
from typing import Any

_FEATURE_INSTALLED = False
_CUTOFF_CONTEXT: ContextVar[str] = ContextVar("bst_tax_cutoff_date", default="")
_MARKER_RE = re.compile(r"(?:\r?\n)?\[BST_TAX_CUTOFF:(\d{4}-\d{2}-\d{2})?\]\s*$")


def _normalize_cutoff(value: Any, *, strict: bool = False) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as err:
        if strict:
            raise ValueError("Tax cutoff date must use YYYY-MM-DD") from err
        return ""


def _parse_tax_marker(note: Any) -> tuple[str, str | None]:
    """Return (clean note, cutoff marker).

    ``None`` means no marker was supplied and an existing cutoff should be
    preserved.  ``""`` means the user explicitly cleared the cutoff.
    """
    text = str(note or "")
    match = _MARKER_RE.search(text)
    if match is None:
        return text, None
    cutoff = _normalize_cutoff(match.group(1) or "", strict=bool(match.group(1)))
    return text[: match.start()].rstrip(), cutoff


def _parse_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_cutoff_blocked(acquired_at: Any, cutoff: Any) -> bool:
    cutoff_text = _normalize_cutoff(cutoff)
    acquired = _parse_utc(acquired_at)
    if not cutoff_text or acquired is None:
        return False
    # The ledger persists canonical UTC instants. The modelling cutoff therefore
    # starts at 00:00 UTC on the selected calendar date.
    return acquired.date() >= date.fromisoformat(cutoff_text)


def install_holding_cutoff_feature() -> None:
    """Install the release runtime hooks once."""
    global _FEATURE_INSTALLED
    if _FEATURE_INSTALLED:
        return

    from . import fifo as fifo_mod
    from . import storage as storage_mod
    from .const import ALL_DEPOTS, DEFAULT_DEPOT_ID, DEFAULT_LONG_TERM_DAYS
    from .models import decimal_value

    original_holding_details = fifo_mod._holding_details
    original_fifo_result = fifo_mod.fifo_result

    def holding_details(
        acquired_at: Any, reference_at: Any, long_term_days: int
    ) -> dict[str, Any]:
        result = dict(original_holding_details(acquired_at, reference_at, long_term_days))
        cutoff = _CUTOFF_CONTEXT.get()
        blocked = (
            result.get("holding_status") != "unknown"
            and _is_cutoff_blocked(acquired_at, cutoff)
        )
        result["tax_cutoff_blocked"] = bool(blocked)
        result["tax_cutoff_date"] = cutoff or ""
        if blocked:
            # Compatibility: keep the established short_term bucket. This means
            # existing metrics, realized-gain buckets and sensors continue to
            # classify the lot as taxable instead of introducing a new status
            # that older frontend code would not understand.
            result["holding_status"] = "short_term"
            result["long_term_date"] = None
            result["days_until_long_term"] = None
        return result

    def fifo_result(
        entries: list[dict[str, Any]],
        depot_id: str | None = None,
        *,
        long_term_days: int = 365,
        as_of: datetime | None = None,
        tax_cutoff_date: Any = "",
    ) -> dict[str, Any]:
        cutoff = _normalize_cutoff(tax_cutoff_date, strict=bool(tax_cutoff_date))
        token = _CUTOFF_CONTEXT.set(cutoff)
        try:
            result = original_fifo_result(
                entries,
                depot_id,
                long_term_days=long_term_days,
                as_of=as_of,
            )
        finally:
            _CUTOFF_CONTEXT.reset(token)

        blocked_btc = sum(
            (
                decimal_value(lot.get("remaining_btc"))
                for lot in result.get("open_lots", [])
                if lot.get("tax_cutoff_blocked")
            ),
            decimal_value(0),
        )
        result["tax_cutoff_date"] = cutoff
        result["tax_cutoff_blocked_btc"] = blocked_btc
        return result

    def build_fifo_cache(
        entries: list[dict[str, Any]],
        depots: list[dict[str, Any]],
        long_term_days: int,
        tax_cutoff_date: Any = "",
    ) -> dict[str, dict[str, Any]]:
        cutoff = _normalize_cutoff(tax_cutoff_date)
        cache = {
            ALL_DEPOTS: fifo_result(
                entries,
                None,
                long_term_days=long_term_days,
                tax_cutoff_date=cutoff,
            )
        }
        for depot in depots:
            depot_id = str(depot.get("id") or DEFAULT_DEPOT_ID)
            cache[depot_id] = fifo_result(
                entries,
                depot_id,
                long_term_days=long_term_days,
                tax_cutoff_date=cutoff,
            )
        return cache

    async def refresh_fifo_cache(self) -> None:
        self.require_unlocked()
        entries = deepcopy(self._data.get("entries", []))
        depots = deepcopy(self._data.get("depots", []))
        settings = self._data.get("tax_settings", {})
        days = int(settings.get("long_term_days", DEFAULT_LONG_TERM_DAYS))
        cutoff = _normalize_cutoff(settings.get("tax_cutoff_date", ""))
        self._fifo_cache = await self.hass.async_add_executor_job(
            build_fifo_cache, entries, depots, days, cutoff
        )

    async def fifo_cache_for_entries(
        self, entries: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        settings = self._data.get("tax_settings", {})
        days = int(settings.get("long_term_days", DEFAULT_LONG_TERM_DAYS))
        cutoff = _normalize_cutoff(settings.get("tax_cutoff_date", ""))
        return await self.hass.async_add_executor_job(
            build_fifo_cache,
            deepcopy(entries),
            deepcopy(self._data.get("depots", [])),
            days,
            cutoff,
        )

    async def set_tax_settings(
        self, *, long_term_days: int, note: str
    ) -> dict[str, Any]:
        days = int(long_term_days)
        if days < 1:
            raise ValueError("Long-term holding period must be at least one day")

        clean_note, marker_cutoff = _parse_tax_marker(note)
        async with self._lock:
            existing = self._data.get("tax_settings", {})
            if marker_cutoff is None:
                cutoff = _normalize_cutoff(existing.get("tax_cutoff_date", ""))
            else:
                cutoff = marker_cutoff
            self._data["tax_settings"] = {
                "long_term_days": days,
                "note": clean_note.strip()[: storage_mod.MAX_NOTE_LENGTH],
                "tax_cutoff_date": cutoff,
            }
            await self._async_save()
            return deepcopy(self._data["tax_settings"])

    # Patch the calculation module and the storage module binding used by its
    # existing cache builder.
    fifo_mod._holding_details = holding_details
    fifo_mod.fifo_result = fifo_result
    storage_mod.fifo_result = fifo_result
    storage_mod._build_fifo_cache = build_fifo_cache

    store_cls = storage_mod.BitcoinLedgerStore
    store_cls._async_refresh_fifo_cache_without_lock = refresh_fifo_cache
    store_cls._async_fifo_cache_for_entries = fifo_cache_for_entries
    store_cls.async_set_tax_settings = set_tax_settings

    # Extend only the already-sanitized browser payloads. No provider IDs, notes,
    # source hashes or additional sensitive ledger fields are exposed.
    root_mod = sys.modules.get(__package__)
    if root_mod is not None:
        original_summary = getattr(root_mod, "_dashboard_fifo_summary", None)
        if callable(original_summary):
            def dashboard_fifo_summary(
                fifo: dict[str, Any], currencies: list[str]
            ) -> dict[str, Any]:
                result = original_summary(fifo, currencies)
                result["tax_cutoff_date"] = fifo.get("tax_cutoff_date", "")
                result["tax_cutoff_blocked_btc"] = fifo.get(
                    "tax_cutoff_blocked_btc", decimal_value(0)
                )
                return result
            root_mod._dashboard_fifo_summary = dashboard_fifo_summary

        original_ledger_fifo = getattr(root_mod, "_dashboard_ledger_fifo", None)
        if callable(original_ledger_fifo):
            def dashboard_ledger_fifo(fifo: dict[str, Any]) -> dict[str, Any]:
                result = original_ledger_fifo(fifo)
                details = {
                    str(lot.get("entry_id") or ""): lot
                    for lot in fifo.get("open_lots", [])
                    if lot.get("entry_id")
                }
                for item in result.get("open_lots", []):
                    detail = details.get(str(item.get("entry_id") or ""), {})
                    item["timestamp"] = detail.get("timestamp")
                    item["remaining_btc"] = detail.get("remaining_btc")
                    item["tax_cutoff_blocked"] = bool(
                        detail.get("tax_cutoff_blocked")
                    )
                    item["tax_cutoff_date"] = detail.get("tax_cutoff_date", "")
                result["tax_cutoff_date"] = fifo.get("tax_cutoff_date", "")
                result["tax_cutoff_blocked_btc"] = fifo.get(
                    "tax_cutoff_blocked_btc", decimal_value(0)
                )
                return result
            root_mod._dashboard_ledger_fifo = dashboard_ledger_fifo

    _FEATURE_INSTALLED = True
