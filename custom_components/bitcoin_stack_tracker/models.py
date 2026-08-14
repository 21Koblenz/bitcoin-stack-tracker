"""Data helpers for Bitcoin Stack Tracker."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
from typing import Any
import unicodedata

SATOSHIS_PER_BTC = Decimal("100000000")
BTC_QUANT = Decimal("0.00000001")
MONEY_QUANT = Decimal("0.00000001")


def decimal_value(value: Any, default: str = "0") -> Decimal:
    """Convert a value to Decimal without binary float surprises."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def amount_to_btc(amount: Any, unit: str) -> Decimal:
    """Convert BTC or sats to BTC."""
    value = decimal_value(amount)
    if unit == "sats":
        value /= SATOSHIS_PER_BTC
    return value.quantize(BTC_QUANT)


def btc_string(value: Decimal) -> str:
    """Serialize a BTC amount."""
    return format(value.quantize(BTC_QUANT), "f")


def money_string(value: Decimal) -> str:
    """Serialize a fiat amount or price."""
    return format(value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP), "f")


def slugify(value: str, fallback: str = "item") -> str:
    """Create a conservative identifier safe for entity IDs and filenames."""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    normalized = "".join(
        char.lower() if char.isascii() and char.isalnum() else "_"
        for char in ascii_value
    )
    normalized = "_".join(part for part in normalized.split("_") if part)
    return normalized[:64] or fallback


def external_statistic_id(
    domain: str,
    entry_id: str,
    metric: str,
    currency: str | None = None,
    suffix: str | None = None,
) -> str:
    """Build a lowercase Home Assistant external statistic identifier."""
    source = slugify(domain)
    parts = [slugify(entry_id), slugify(metric)]
    if currency:
        parts.append(slugify(currency.lower()))
    if suffix:
        parts.append(slugify(suffix))
    object_id = "_".join(parts)
    result = f"{source}:{object_id}"
    # Recorder stores statistic IDs in a 255-character column. Preserve a
    # deterministic suffix if unusually long user-defined IDs require trimming.
    if len(result) > 255:
        digest = hashlib.sha256(result.encode("utf-8")).hexdigest()[:12]
        object_limit = 255 - len(source) - 1 - len(digest) - 1
        object_id = object_id[:object_limit].rstrip("_")
        result = f"{source}:{object_id}_{digest}"
    return result


def _ledger_timestamp(value: Any) -> tuple[datetime, str]:
    """Return a UTC timestamp sort key plus a normalized display value."""
    raw = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)
        return parsed, parsed.isoformat()
    except (TypeError, ValueError):
        return datetime.max.replace(tzinfo=timezone.utc), raw


def goal_reached_at(
    entries: list[dict[str, Any]], target_btc: Any, depot_id: str = "all"
) -> str | None:
    """Return the first ledger timestamp at which a BTC goal was reached.

    Purchases, income and stack entries increase the running balance; sales, expenses,
    standalone network fees and explicitly stack-affecting BTC fees decrease it. ISO timestamps are sorted as actual UTC instants instead of plain
    strings, so old imports with different offsets cannot move the crossing date.
    """
    target = decimal_value(target_btc)
    if target <= 0:
        return None
    balance = Decimal("0")
    scoped = sorted(
        (
            row for row in entries
            if depot_id == "all" or str(row.get("depot_id") or "main") == depot_id
        ),
        key=lambda row: (
            _ledger_timestamp(row.get("timestamp"))[0],
            1 if str(row.get("type", "")) in {"sale", "expense", "network_fee"} else 0,
            str(row.get("id", "")),
        ),
    )
    for row in scoped:
        amount = decimal_value(row.get("amount_btc"))
        fee_btc = max(decimal_value(row.get("fee_btc")), Decimal("0"))
        fee_affects_stack = bool(row.get("fee_btc_affects_stack"))
        kind = str(row.get("type") or "").lower()
        if kind in {"purchase", "income", "stack"}:
            balance += amount
        elif kind in {"sale", "expense", "network_fee"}:
            balance -= amount
        if fee_affects_stack:
            balance -= fee_btc
        if balance >= target:
            _parsed, timestamp = _ledger_timestamp(row.get("timestamp"))
            return timestamp or None
    return None
