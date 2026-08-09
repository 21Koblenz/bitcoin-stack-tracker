"""Small in-memory sliding-window limiter for sensitive operations."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from time import monotonic


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    retry_after: int
    remaining: int


class OperationRateLimiter:
    """Limit operations per portfolio, user and action.

    State is intentionally volatile and resets with Home Assistant. It protects
    the event loop and password KDF from accidental or scripted bursts; it is not
    intended as a replacement for Home Assistant authentication.
    """

    def __init__(self) -> None:
        self._events: dict[tuple[str, str, str], deque[float]] = defaultdict(deque)

    def check(
        self,
        *,
        entry_id: str,
        user_id: str,
        operation: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        now = monotonic()
        key = (entry_id, user_id, operation)
        events = self._events[key]
        cutoff = now - window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= limit:
            retry_after = max(1, int(window_seconds - (now - events[0])) + 1)
            return RateLimitResult(False, retry_after, 0)
        events.append(now)
        return RateLimitResult(True, 0, max(0, limit - len(events)))

    def clear_user(self, entry_id: str, user_id: str, operation: str | None = None) -> None:
        keys = [
            key
            for key in self._events
            if key[0] == entry_id
            and key[1] == user_id
            and (operation is None or key[2] == operation)
        ]
        for key in keys:
            self._events.pop(key, None)
