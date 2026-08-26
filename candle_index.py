"""Canonical candle indexing used by live and historical research.

Semantic convention:
    0 = currently forming candle (when the provider includes it)
    1 = most recent fully closed candle
    2 = previous fully closed candle
    ...

Live OHLC from the provider includes the current candle. Historical replay
contains closed candles only and declares that explicitly.
"""
from __future__ import annotations

CURRENT_CANDLE = 0
LAST_CLOSED_CANDLE = 1


def index_from_latest(offset: int) -> int:
    """Translate a live semantic candle offset to Python's negative index."""
    if offset < 0:
        raise ValueError("candle offset must be >= 0")
    return -(offset + 1)


def latest_closed_index(candles: list[dict], *, includes_forming: bool = True) -> int:
    """Return the Python index of the latest fully closed candle."""
    minimum = 2 if includes_forming else 1
    if len(candles) < minimum:
        raise ValueError("not enough candles to identify the latest closed candle")
    return len(candles) - (2 if includes_forming else 1)


def require_candle(candles: list[dict], offset: int, *, includes_forming: bool = True) -> dict:
    """Return a candle by semantic offset, failing closed on bad history."""
    if offset < 0:
        raise ValueError("candle offset must be >= 0")
    if includes_forming:
        if len(candles) <= offset:
            raise ValueError(f"not enough candles for offset {offset}")
        return candles[index_from_latest(offset)]
    if offset == CURRENT_CANDLE:
        raise ValueError("historical closed-only data has no candle 0")
    if len(candles) < offset:
        raise ValueError(f"not enough closed candles for offset {offset}")
    return candles[-offset]


def closed_candle(candles: list[dict], *, includes_forming: bool = True) -> dict:
    """Return the latest fully closed candle."""
    return candles[latest_closed_index(candles, includes_forming=includes_forming)]
