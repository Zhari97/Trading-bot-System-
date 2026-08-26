"""Deterministic guards for closed-candle analysis and alert deduplication.

Research/live orchestration helper: it does not place orders or send alerts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class CandleDecision:
    accepted: bool
    reason: str


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


def candle_is_closed(open_time: datetime, interval_minutes: int, now: datetime) -> CandleDecision:
    """Accept only a candle whose full interval has elapsed."""
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")
    start = _as_utc(open_time)
    current = _as_utc(now)
    close_time = start.timestamp() + interval_minutes * 60
    if current.timestamp() < close_time:
        return CandleDecision(False, "CANDLE_STILL_OPEN")
    return CandleDecision(True, "CANDLE_CLOSED")


def should_emit_signal(
    pair: str,
    candle_open_time: datetime,
    direction: str,
    score: float,
    confluence: float,
    last_key: tuple | None,
    score_change_threshold: float = 5.0,
) -> CandleDecision:
    """Suppress duplicate alerts while allowing meaningful setup changes."""
    if not pair or not direction:
        raise ValueError("pair and direction are required")
    if not 0 <= score <= 100 or not 0 <= confluence <= 100:
        raise ValueError("score and confluence must be between 0 and 100")
    key = (pair.upper(), candle_open_time.isoformat(), direction.upper())
    if last_key is None:
        return CandleDecision(True, "NEW_SIGNAL")
    if key[:3] == last_key[:3]:
        previous_score = float(last_key[3]) if len(last_key) > 3 else score
        if abs(score - previous_score) < score_change_threshold:
            return CandleDecision(False, "DUPLICATE_SIGNAL")
        return CandleDecision(True, "MEANINGFUL_SCORE_CHANGE")
    return CandleDecision(True, "NEW_CANDLE_OR_DIRECTION")
