"""Market Data Manager V2 foundation.

Centralizza il recupero delle candele e la cache in-process senza cambiare
la strategia V2.2. È progettato per essere riutilizzato da runner, dashboard
e futuro realtime monitor.

Principi:
- una sola sorgente di verità per OHLC;
- cache allineata al timeframe, non a un TTL arbitrario;
- non serve una nuova richiesta finché la candela chiusa più recente non può
  essere cambiata;
- nessuna credenziale o segreto nel modulo;
- il provider resta sostituibile.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class CacheEntry(Generic[T]):
    fetched_at: float
    value: T
    closed_bucket: int


class MarketDataCache(Generic[T]):
    """Cache thread-safe keyed by provider/symbol/timeframe.

    ``closed_bucket`` rappresenta l'inizio della candela chiusa più recente.
    Finché il bucket non cambia, il valore può essere riutilizzato.
    """

    def __init__(self, clock: Callable[[], float] | None = None):
        self._clock = clock or time.time
        self._lock = Lock()
        self._entries: dict[str, CacheEntry[T]] = {}

    @staticmethod
    def closed_bucket(timestamp: float, interval_seconds: int) -> int:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds deve essere positivo")
        # L'ultima candela chiusa termina all'inizio del bucket corrente.
        return int(timestamp // interval_seconds) - 1

    def get(self, key: str, now: float, interval_seconds: int) -> T | None:
        current_bucket = self.closed_bucket(now, interval_seconds)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry.closed_bucket != current_bucket:
                return None
            return entry.value

    def put(self, key: str, value: T, now: float, interval_seconds: int) -> None:
        bucket = self.closed_bucket(now, interval_seconds)
        with self._lock:
            self._entries[key] = CacheEntry(
                fetched_at=now,
                value=value,
                closed_bucket=bucket,
            )

    def get_or_fetch(
        self,
        key: str,
        interval_seconds: int,
        fetcher: Callable[[], T],
    ) -> T:
        now = self._clock()
        cached = self.get(key, now, interval_seconds)
        if cached is not None:
            return cached
        value = fetcher()
        self.put(key, value, self._clock(), interval_seconds)
        return value

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._entries)


GLOBAL_MARKET_CACHE: MarketDataCache[object] = MarketDataCache()


def cache_key(provider: str, symbol: str, interval_minutes: int) -> str:
    """Costruisce una chiave stabile e leggibile per una serie OHLC."""
    if interval_minutes <= 0:
        raise ValueError("interval_minutes deve essere positivo")
    return f"{provider.lower()}:{symbol.upper()}:{interval_minutes}m"
