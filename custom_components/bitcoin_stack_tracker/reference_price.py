"""Local historical BTC reference-price lookup helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        raw = str(value or "").strip()
        if not raw:
            raise ValueError("timestamp missing")
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        result = datetime.fromisoformat(raw)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def historical_reference_price(
    history_data: dict[str, Any],
    currency: str,
    timestamp: Any,
    *,
    live_price: Any = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the best locally known BTC price for a booking timestamp.

    The closest intraday sample on the same UTC calendar day wins. If none is
    available, the exact daily history value is used. Today's live price is a
    final fallback only for a booking dated today; an old booking can never be
    compared with today's live price.
    """
    code = str(currency or "").strip().upper()
    if not code:
        return {"available": False, "currency": code, "reason": "currency_missing"}
    try:
        target = _timestamp(timestamp)
    except Exception:
        return {"available": False, "currency": code, "reason": "timestamp_invalid"}
    day = target.date().isoformat()

    samples = history_data.get("price_samples", {}).get(code, {})
    nearest: tuple[float, datetime, Decimal] | None = None
    if isinstance(samples, dict):
        for raw_time, raw_price in samples.items():
            try:
                moment = _timestamp(raw_time)
            except Exception:
                continue
            if moment.date() != target.date():
                continue
            price = _decimal(raw_price)
            if price <= 0:
                continue
            distance = abs((moment - target).total_seconds())
            if nearest is None or distance < nearest[0]:
                nearest = (distance, moment, price)
    if nearest is not None:
        return {
            "available": True,
            "currency": code,
            "price": nearest[2],
            "source": "intraday",
            "reference_at": nearest[1].isoformat(),
            "day": day,
        }

    daily = history_data.get("prices", {}).get(code, {})
    if isinstance(daily, dict):
        price = _decimal(daily.get(day))
        if price > 0:
            return {
                "available": True,
                "currency": code,
                "price": price,
                "source": "daily",
                "reference_at": day,
                "day": day,
            }

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)
    current = _decimal(live_price)
    if target.date() == current_time.date() and current > 0:
        return {
            "available": True,
            "currency": code,
            "price": current,
            "source": "live",
            "reference_at": current_time.isoformat(),
            "day": day,
        }
    return {"available": False, "currency": code, "day": day, "reason": "price_missing"}
