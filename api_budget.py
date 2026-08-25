"""Protezione centrale e leggera delle chiamate alle API di market data.

La logica del segnale non viene modificata: il modulo può essere usato sia
come wrapper esplicito sia come guard globale del runner.
"""

from __future__ import annotations

import os
import time
from collections import OrderedDict
from threading import Lock
from typing import Callable, TypeVar

import requests

T = TypeVar("T")

MIN_REQUEST_GAP_SECONDS = max(0.0, float(os.environ.get("API_MIN_REQUEST_GAP_SECONDS", "0.35")))
CACHE_TTL_SECONDS = max(1.0, float(os.environ.get("API_CACHE_TTL_SECONDS", "20")))
MAX_CACHE_ITEMS = max(1, int(os.environ.get("API_MAX_CACHE_ITEMS", "64")))
MAX_RETRIES = max(0, int(os.environ.get("API_MAX_RETRIES", "2")))
MAX_REQUESTS_PER_RUN = max(1, int(os.environ.get("API_MAX_REQUESTS_PER_RUN", "20")))

_lock = Lock()
_last_request_at = 0.0
_request_count = 0
_cache: OrderedDict[str, tuple[float, object]] = OrderedDict()
_original_get = None
_guard_installed = False


class ApiBudgetExceeded(RuntimeError):
    """Il runner ha raggiunto il limite di richieste del processo."""


def reset_budget() -> None:
    global _request_count
    with _lock:
        _request_count = 0


def request_count() -> int:
    with _lock:
        return _request_count


def _wait_for_slot() -> None:
    global _last_request_at
    with _lock:
        now = time.monotonic()
        wait = MIN_REQUEST_GAP_SECONDS - (now - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


def _consume_request_slot() -> None:
    global _request_count
    with _lock:
        if _request_count >= MAX_REQUESTS_PER_RUN:
            raise ApiBudgetExceeded(
                f"API budget per run raggiunto ({MAX_REQUESTS_PER_RUN} richieste)"
            )
        _request_count += 1


def cached_call(key: str, fetcher: Callable[[], T]) -> T:
    """Esegue fetcher con cache breve, rate guard e retry controllati."""
    now = time.monotonic()
    with _lock:
        cached = _cache.get(key)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            _cache.move_to_end(key)
            return cached[1]  # type: ignore[return-value]
        if cached:
            _cache.pop(key, None)

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            _consume_request_slot()
            _wait_for_slot()
            value = fetcher()
            with _lock:
                _cache[key] = (time.monotonic(), value)
                _cache.move_to_end(key)
                while len(_cache) > MAX_CACHE_ITEMS:
                    _cache.popitem(last=False)
            return value
        except ApiBudgetExceeded:
            raise
        except Exception as exc:
            last_error = exc
            if attempt >= MAX_RETRIES:
                break
            time.sleep(0.75 * (2 ** attempt))

    assert last_error is not None
    raise last_error


def _guarded_get(url, *args, **kwargs):
    """Intercetta solo GET verso provider market-data noti.

    Telegram e dashboard continuano a usare requests.get/post normalmente.
    """
    if not any(provider in str(url) for provider in ("api.kraken.com", "api.twelvedata.com")):
        return _original_get(url, *args, **kwargs)

    params = kwargs.get("params") or {}
    cache_key = f"GET:{url}:{sorted((str(k), str(v)) for k, v in params.items())}"

    def fetch():
        return _original_get(url, *args, **kwargs)

    return cached_call(cache_key, fetch)


def guard_requests() -> None:
    """Installa una sola volta il guard sui GET dei provider market-data."""
    global _original_get, _guard_installed
    if _guard_installed:
        return
    _original_get = requests.get
    requests.get = _guarded_get
    _guard_installed = True
