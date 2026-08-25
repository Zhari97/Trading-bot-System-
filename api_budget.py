"""Protezione leggera delle chiamate alle API di market data.

Non cambia la logica del segnale: limita solo raffiche di richieste,
riusa richieste identiche molto ravvicinate e applica retry con backoff
su errori transitori HTTP.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from threading import Lock
from typing import Callable, TypeVar

T = TypeVar("T")

MIN_REQUEST_GAP_SECONDS = 0.35
CACHE_TTL_SECONDS = 20.0
MAX_CACHE_ITEMS = 32
MAX_RETRIES = 3

_lock = Lock()
_last_request_at = 0.0
_cache: OrderedDict[str, tuple[float, object]] = OrderedDict()


def _wait_for_slot() -> None:
    global _last_request_at
    with _lock:
        now = time.monotonic()
        wait = MIN_REQUEST_GAP_SECONDS - (now - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


def cached_call(key: str, fetcher: Callable[[], T]) -> T:
    """Esegue fetcher con cache breve e protezione da raffiche."""
    now = time.monotonic()
    with _lock:
        cached = _cache.get(key)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            _cache.move_to_end(key)
            return cached[1]  # type: ignore[return-value]
        if cached:
            _cache.pop(key, None)

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            _wait_for_slot()
            value = fetcher()
            with _lock:
                _cache[key] = (time.monotonic(), value)
                _cache.move_to_end(key)
                while len(_cache) > MAX_CACHE_ITEMS:
                    _cache.popitem(last=False)
            return value
        except Exception as exc:
            last_error = exc
            if attempt >= MAX_RETRIES - 1:
                break
            time.sleep(0.75 * (2 ** attempt))

    assert last_error is not None
    raise last_error
