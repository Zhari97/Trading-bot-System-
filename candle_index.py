"""Canonical candle indexing used by research and live guards.

Convention:
    0 = currently forming candle (if the provider includes it)
    1 = most recent fully closed candle
    2 = previous fully closed candle
    ...

The helper keeps this convention in one place and fails closed when there is
not enough data. It does not decide whether a provider actually supplied a
forming candle; that provider-specific contract remains outside this module.
"""
from __future__ import annotations

CURRENT_CANDLE = 0
LAST_CLOSED_CANDLE = 1


def index_from_latest(offset: int) -> int:
    """Translate semantic candle offset to Python's negative index."""
    if offset < 0:
        raise ValueError("candle offset must be >= 0")
    return -(offset + 1)


def require_candle(candles: list[dict], offset: int) -> dict:
    """Return candle by semantic offset, raising instead of silently falling back."""
    if offset < 0:
        raise ValueError("candle offset must be >= 0")
    if len(candles) <= offset:
        raise ValueError(f"not enough candles for offset {offset}")
    return candles[index_from_latest(offset)]


def closed_candle(candles: list[dict]) -> dict:
    """Return the candle designated as the latest closed candle."""
    return require_candle(candles, LAST_CLOSED_CANDLE)
