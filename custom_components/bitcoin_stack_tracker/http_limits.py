"""Bounded HTTP response readers used for all external/provider payloads."""

from __future__ import annotations

import asyncio
import json
from typing import Any

MAX_JSON_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_TEXT_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_BULK_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_ERROR_RESPONSE_BYTES = 4096


class ResponseTooLargeError(ValueError):
    """Raised before or while reading a response that exceeds its hard limit."""


def _declared_size(response: Any) -> int | None:
    value = getattr(response, "content_length", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def async_read_limited(response: Any, *, max_bytes: int) -> bytes:
    """Read no more than ``max_bytes`` even for chunked/lying responses."""
    declared = _declared_size(response)
    if declared is not None and declared > max_bytes:
        raise ResponseTooLargeError(
            f"HTTP response is too large ({declared} bytes; limit {max_bytes})"
        )

    stream = getattr(response, "content", None)
    readexactly = getattr(stream, "readexactly", None)
    if callable(readexactly):
        try:
            data = await readexactly(max_bytes + 1)
        except asyncio.IncompleteReadError as err:
            data = err.partial
    else:
        # Compatibility path for simple test doubles. Real aiohttp responses use
        # StreamReader.readexactly above, so production memory stays bounded.
        data = await response.read()

    if len(data) > max_bytes:
        raise ResponseTooLargeError(
            f"HTTP response exceeded {max_bytes} bytes"
        )
    return bytes(data)


async def async_text_limited(response: Any, *, max_bytes: int = MAX_TEXT_RESPONSE_BYTES) -> str:
    raw = await async_read_limited(response, max_bytes=max_bytes)
    charset = getattr(response, "charset", None) or "utf-8"
    try:
        return raw.decode(charset, errors="strict")
    except (LookupError, UnicodeDecodeError):
        return raw.decode("utf-8", errors="replace")


async def async_json_limited(response: Any, *, max_bytes: int = MAX_JSON_RESPONSE_BYTES) -> Any:
    text = await async_text_limited(response, max_bytes=max_bytes)
    return json.loads(text)
