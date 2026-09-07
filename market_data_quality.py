"""Market-data quality and freshness guards for research/live diagnostics.

The module is intentionally independent from the signal engine. A stale or
malformed snapshot should be visible to the caller instead of being silently
accepted as current market information.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping, Any


@dataclass(frozen=True)
class DataQualityReport:
    valid: bool
    fresh: bool
    rows: int
    errors: tuple[str, ...]
    latest_timestamp_utc: str | None
    age_seconds: float | None


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def validate_ohlcv(
    rows: Iterable[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    max_age_seconds: float = 120.0,
    interval_seconds: int | None = None,
) -> DataQualityReport:
    """Validate OHLCV rows for basic integrity, duplicates and freshness."""
    data = list(rows)
    errors: list[str] = []
    timestamps: list[datetime] = []
    required = ("timestamp", "open", "high", "low", "close", "volume")

    for index, row in enumerate(data):
        missing = [key for key in required if key not in row]
        if missing:
            errors.append(f"row {index}: missing {','.join(missing)}")
            continue
        ts = _parse_ts(row.get("timestamp"))
        if ts is None:
            errors.append(f"row {index}: invalid timestamp")
        else:
            timestamps.append(ts)
        try:
            values = [float(row[key]) for key in required[1:]]
            if not all(math.isfinite(v) for v in values):
                errors.append(f"row {index}: non-finite OHLCV")
            o, h, l, c, volume = values
            if min(o, h, l, c) <= 0 or volume < 0:
                errors.append(f"row {index}: invalid OHLCV values")
            if h < max(o, c) or l > min(o, c) or h < l:
                errors.append(f"row {index}: inconsistent high/low")
        except (TypeError, ValueError):
            errors.append(f"row {index}: non-numeric OHLCV")

    if timestamps:
        ordered = sorted(timestamps)
        if len(set(ordered)) != len(ordered):
            errors.append("duplicate timestamps")
        if interval_seconds is not None and interval_seconds > 0:
            for prev, cur in zip(ordered, ordered[1:]):
                delta = (cur - prev).total_seconds()
                if delta != interval_seconds:
                    errors.append(f"timestamp gap/overlap: expected {interval_seconds}s, got {delta}s")
                    break
        latest = max(timestamps)
        ref = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        age = (ref - latest).total_seconds()
        fresh = 0 <= age <= max_age_seconds
    else:
        latest = None
        age = None
        fresh = False

    return DataQualityReport(
        valid=not errors,
        fresh=fresh,
        rows=len(data),
        errors=tuple(errors),
        latest_timestamp_utc=latest.isoformat() if latest else None,
        age_seconds=age,
    )
