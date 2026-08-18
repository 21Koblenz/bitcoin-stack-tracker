"""Lightweight persistent intraday snapshots for the public market assessment.

The expensive current assessment is already calculated at most once every five
minutes.  Short overview charts benefit from more than one causal point per day,
so this store records one real model snapshot per UTC hour without triggering any
additional model calculation.

The data contains public market/model output only.  A model/settings/currency
change selects a new generation; newly appended daily history does not rewrite
past intraday observations because those observations represent the score that
was actually known at that timestamp.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .buy_opportunity import SCORE_VERSION
from .const import DOMAIN

_STORAGE_VERSION = 1
_KEY_PREFIX = f"{DOMAIN}.market_assessment_intraday"
_RETENTION_DAYS = 45
_MAX_POINTS = (_RETENTION_DAYS + 2) * 24


def market_assessment_intraday_signature(*, currency: str, settings: Mapping[str, Any]) -> str:
    """Return the generation key for comparable intraday score snapshots."""
    payload = {
        "score_version": SCORE_VERSION,
        "currency": str(currency).upper(),
        "settings": settings,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class MarketAssessmentIntradayCache:
    """Persist one real market-assessment snapshot per UTC hour."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = Store[dict[str, Any]](hass, _STORAGE_VERSION, f"{_KEY_PREFIX}.{entry_id}")
        self._lock = asyncio.Lock()
        self._data: dict[str, Any] = {"signature": "", "points": []}

    async def async_load(self) -> None:
        loaded = await self._store.async_load()
        if isinstance(loaded, dict):
            self._data = loaded
        if not isinstance(self._data.get("points"), list):
            self._data["points"] = []
        self._data["signature"] = str(self._data.get("signature") or "")
        await self._async_prune(save=True)

    async def _async_prune(self, *, save: bool = False) -> bool:
        cutoff = datetime.now(timezone.utc) - timedelta(days=_RETENTION_DAYS)
        cleaned: list[dict[str, Any]] = []
        for raw in self._data.get("points", []):
            if not isinstance(raw, dict):
                continue
            stamp = _parse_utc(raw.get("timestamp"))
            try:
                score = float(raw.get("score"))
            except (TypeError, ValueError):
                continue
            if stamp is None or stamp < cutoff or not (0 <= score <= 100):
                continue
            cleaned.append(dict(raw))
        cleaned.sort(key=lambda item: str(item.get("timestamp") or ""))
        if len(cleaned) > _MAX_POINTS:
            cleaned = cleaned[-_MAX_POINTS:]
        changed = cleaned != self._data.get("points", [])
        self._data["points"] = cleaned
        if save and changed:
            await self._store.async_save(self._data)
        return changed

    async def async_record(
        self,
        signature: str,
        *,
        calculated_at: str,
        result: Mapping[str, Any],
        currency: str,
    ) -> bool:
        """Record one real model sample per hour without extra calculation."""
        stamp = _parse_utc(calculated_at)
        try:
            score = float(result.get("score_raw", result.get("score")))
        except (TypeError, ValueError):
            return False
        if stamp is None or not (0 <= score <= 100):
            return False
        price_raw = result.get("current_price")
        try:
            price = float(price_raw) if price_raw is not None else None
        except (TypeError, ValueError):
            price = None
        if price is not None and price <= 0:
            price = None
        bucket = stamp.strftime("%Y-%m-%dT%H")
        point = {
            "timestamp": stamp.isoformat(),
            "date": stamp.date().isoformat(),
            "score": score,
            "rating": str(result.get("rating") or "unavailable"),
            "price": price,
            "currency": str(currency).upper(),
            "bucket": bucket,
        }
        async with self._lock:
            if str(self._data.get("signature") or "") != str(signature):
                self._data = {"signature": str(signature), "points": []}
            points = self._data.setdefault("points", [])
            # Save only the first completed model snapshot in each hour.  The
            # current in-memory/live point represents the still-open hour.
            if any(str(item.get("bucket") or "") == bucket for item in points if isinstance(item, dict)):
                return False
            points.append(point)
            await self._async_prune(save=False)
            await self._store.async_save(self._data)
            return True

    async def async_points(self, signature: str, *, since: datetime | None = None) -> list[dict[str, Any]]:
        async with self._lock:
            if str(self._data.get("signature") or "") != str(signature):
                return []
            result: list[dict[str, Any]] = []
            for raw in self._data.get("points", []):
                if not isinstance(raw, dict):
                    continue
                stamp = _parse_utc(raw.get("timestamp"))
                if stamp is None or (since is not None and stamp < since.astimezone(timezone.utc)):
                    continue
                result.append(deepcopy(raw))
            return result

    async def async_clear(self) -> None:
        async with self._lock:
            self._data = {"signature": "", "points": []}
            await self._store.async_save(self._data)

    async def async_remove(self) -> None:
        async with self._lock:
            self._data = {"signature": "", "points": []}
            await self._store.async_remove()
