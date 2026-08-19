"""Persistent public-data cache for historical market-assessment charts.

Historical score reconstruction is one of the most CPU-intensive operations in
Bitcoin Stack Tracker.  The inputs are public daily BTC prices and the public
model settings, so the result can safely be persisted without touching private
portfolio data.

The cache is content-addressed: any change to the score implementation, selected
currency, model settings, or cached daily-price history changes the signature
and causes a clean rebuild.  The wall-clock day and intraday live-price ticks are
deliberately not part of the expensive score-series signature: if the actual
source history did not change, the same causal daily scores remain valid.  The
frontend appends the already calculated current assessment as the live tail.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .buy_opportunity import SCORE_VERSION, score_affecting_settings
from .const import DOMAIN

_CACHE_STORAGE_VERSION = 1
_CACHE_KEY_PREFIX = f"{DOMAIN}.market_assessment_history"
_MAX_CACHED_RANGES = 16


def market_assessment_history_signature(
    history: Mapping[str, Any],
    *,
    currency: str,
    settings: Mapping[str, Any],
) -> str:
    """Return a deterministic content hash for all expensive history inputs."""
    digest = hashlib.sha256()
    header = {
        "score_version": SCORE_VERSION,
        "currency": str(currency).upper(),
        "settings": score_affecting_settings(settings),
    }
    digest.update(
        json.dumps(header, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    )
    digest.update(b"\n")
    for raw_day, raw_price in sorted(history.items(), key=lambda item: str(item[0])):
        try:
            price = float(raw_price)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        digest.update(str(raw_day).encode("ascii", "ignore"))
        digest.update(b"=")
        digest.update(format(price, ".15g").encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


class MarketAssessmentHistoryCache:
    """Small persistent cache containing only public historical score output."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = Store[dict[str, Any]](
            hass,
            _CACHE_STORAGE_VERSION,
            f"{_CACHE_KEY_PREFIX}.{entry_id}",
        )
        self._lock = asyncio.Lock()
        self._data: dict[str, Any] = {
            "signature": "",
            "scores": None,
            "ranges": {},
            "order": [],
        }

    async def async_load(self) -> None:
        loaded = await self._store.async_load()
        if isinstance(loaded, dict):
            self._data = loaded
        self._data.setdefault("signature", "")
        self._data.setdefault("scores", None)
        self._data.setdefault("ranges", {})
        self._data.setdefault("order", [])
        if not isinstance(self._data.get("ranges"), dict):
            self._data["ranges"] = {}
        if not isinstance(self._data.get("order"), list):
            self._data["order"] = []

    async def async_get(self, signature: str, range_key: str) -> dict[str, Any] | None:
        async with self._lock:
            if str(self._data.get("signature") or "") != str(signature):
                return None
            ranges = self._data.get("ranges", {})
            result = ranges.get(str(range_key)) if isinstance(ranges, dict) else None
            return deepcopy(result) if isinstance(result, dict) else None

    async def async_prepare(self, signature: str) -> None:
        """Select the newest input generation before an expensive calculation starts."""
        async with self._lock:
            if str(self._data.get("signature") or "") == str(signature):
                return
            self._data = {"signature": str(signature), "scores": None, "ranges": {}, "order": []}
            await self._store.async_save(self._data)

    async def async_get_scores(self, signature: str) -> dict[str, Any] | None:
        async with self._lock:
            if str(self._data.get("signature") or "") != str(signature):
                return None
            result = self._data.get("scores")
            return deepcopy(result) if isinstance(result, dict) else None

    async def async_put_scores(self, signature: str, result: Mapping[str, Any]) -> bool:
        async with self._lock:
            if str(self._data.get("signature") or "") != str(signature):
                return False
            self._data["scores"] = deepcopy(dict(result))
            await self._store.async_save(self._data)
            return True

    async def async_put(self, signature: str, range_key: str, result: Mapping[str, Any]) -> bool:
        async with self._lock:
            # A slower calculation for an older source/settings generation must
            # never evict a newer cache that finished first.
            if str(self._data.get("signature") or "") != str(signature):
                return False
            ranges = self._data.setdefault("ranges", {})
            order = self._data.setdefault("order", [])
            key = str(range_key)
            ranges[key] = deepcopy(dict(result))
            if key in order:
                order.remove(key)
            order.append(key)
            while len(order) > _MAX_CACHED_RANGES:
                oldest = str(order.pop(0))
                ranges.pop(oldest, None)
            await self._store.async_save(self._data)
            return True

    async def async_clear(self) -> None:
        async with self._lock:
            self._data = {"signature": "", "scores": None, "ranges": {}, "order": []}
            await self._store.async_save(self._data)

    async def async_remove(self) -> None:
        async with self._lock:
            self._data = {"signature": "", "scores": None, "ranges": {}, "order": []}
            await self._store.async_remove()
