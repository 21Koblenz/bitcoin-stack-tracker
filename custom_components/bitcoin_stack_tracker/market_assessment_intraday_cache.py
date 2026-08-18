"""Persistent five-minute snapshots for the public market assessment.

The expensive current assessment is already calculated at most once every five
minutes. Short overview charts should use those real model observations instead
of fabricating/interpolating values from daily closes, so this store records one
snapshot for each completed five-minute UTC bucket without triggering another
model calculation.

Only public market/model output is stored. A model/settings/currency change
selects a new generation. Points older than 90 days are removed automatically.
To keep Home Assistant I/O low, the in-memory cache is updated immediately while
durable storage writes are coalesced to at most roughly once per hour.
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

_STORAGE_VERSION = 2
_KEY_PREFIX = f"{DOMAIN}.market_assessment_intraday"
_RETENTION_DAYS = 90
_BUCKET_MINUTES = 5
_BUCKETS_PER_DAY = (24 * 60) // _BUCKET_MINUTES
_MAX_POINTS = (_RETENTION_DAYS + 2) * _BUCKETS_PER_DAY
_SAVE_DELAY_SECONDS = 60 * 60


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


def _bucket_key(stamp: datetime) -> str:
    minute = (stamp.minute // _BUCKET_MINUTES) * _BUCKET_MINUTES
    return stamp.replace(minute=minute, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")


class MarketAssessmentIntradayCache:
    """Persist real market-assessment samples in five-minute UTC buckets."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = Store[dict[str, Any]](hass, _STORAGE_VERSION, f"{_KEY_PREFIX}.{entry_id}")
        self._lock = asyncio.Lock()
        self._data: dict[str, Any] = {"signature": "", "points": []}
        self._save_scheduled = False

    async def async_load(self) -> None:
        loaded = await self._store.async_load()
        if isinstance(loaded, dict):
            self._data = loaded
        if not isinstance(self._data.get("points"), list):
            self._data["points"] = []
        self._data["signature"] = str(self._data.get("signature") or "")
        await self._async_prune(save=True)

    def _delayed_save_payload(self) -> dict[str, Any]:
        self._save_scheduled = False
        return deepcopy(self._data)

    def _schedule_save(self) -> None:
        if self._save_scheduled:
            return
        self._save_scheduled = True
        self._store.async_delay_save(self._delayed_save_payload, _SAVE_DELAY_SECONDS)

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
            point = dict(raw)
            point["bucket"] = _bucket_key(stamp)
            cleaned.append(point)
        cleaned.sort(key=lambda item: str(item.get("timestamp") or ""))
        if len(cleaned) > _MAX_POINTS:
            cleaned = cleaned[-_MAX_POINTS:]
        # Deduplicate old hourly/v1 data and any accidental duplicate bucket.
        deduped: dict[str, dict[str, Any]] = {}
        for point in cleaned:
            deduped[str(point.get("bucket") or point.get("timestamp") or "")] = point
        cleaned = list(deduped.values())
        cleaned.sort(key=lambda item: str(item.get("timestamp") or ""))
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
        """Record one already-calculated model sample per five-minute bucket."""
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
        bucket = _bucket_key(stamp)
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
            signature_changed = str(self._data.get("signature") or "") != str(signature)
            if signature_changed:
                self._data = {"signature": str(signature), "points": []}
            points = self._data.setdefault("points", [])
            if any(str(item.get("bucket") or "") == bucket for item in points if isinstance(item, dict)):
                return False
            points.append(point)
            await self._async_prune(save=False)
            # Keep the hot path cheap: the point is immediately visible to API
            # reads, while Store coalesces durable writes instead of rewriting a
            # growing 90-day JSON document every five minutes.
            if signature_changed:
                await self._store.async_save(self._data)
                self._save_scheduled = False
            else:
                self._schedule_save()
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
            self._save_scheduled = False
            await self._store.async_save(self._data)

    async def async_remove(self) -> None:
        async with self._lock:
            self._data = {"signature": "", "points": []}
            self._save_scheduled = False
            await self._store.async_remove()
