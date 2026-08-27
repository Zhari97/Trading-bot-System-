"""Research-only volume diagnostics.

This module intentionally does not affect signal generation, scoring, trade
selection, sizing, or risk. It exposes causal, backward-looking OHLCV features
so the historical replay can test whether volume adds information.
"""
from __future__ import annotations


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile_rank(value: float, history: list[float]) -> float:
    """Return the percentile rank of value within history, in [0, 100]."""
    if not history:
        return 50.0
    less_or_equal = sum(1 for item in history if item <= value)
    return less_or_equal / len(history) * 100.0


def diagnostics(candles: list[dict], index: int) -> dict:
    """Return backward-looking volume/price-volume diagnostics at index.

    The current closed candle is included in the observation, while all
    baselines use only candles at or before the current index. No future data
    is referenced.
    """
    if index < 0 or index >= len(candles):
        raise IndexError("candle index out of range")

    current = candles[index]
    volume = float(current.get("volume", 0.0) or 0.0)
    close = float(current["close"])
    open_price = float(current["open"])

    history20 = [
        float(c.get("volume", 0.0) or 0.0)
        for c in candles[max(0, index - 19): index + 1]
    ]
    history50 = [
        float(c.get("volume", 0.0) or 0.0)
        for c in candles[max(0, index - 49): index + 1]
    ]

    mean20 = _mean(history20)
    mean50 = _mean(history50)
    relative20 = volume / mean20 if mean20 > 0 else None
    relative50 = volume / mean50 if mean50 > 0 else None

    percentile50 = _percentile_rank(volume, history50)

    previous = candles[index - 1] if index > 0 else None
    previous_volume = float(previous.get("volume", 0.0) or 0.0) if previous else 0.0
    volume_change_pct = (
        (volume / previous_volume - 1.0) * 100.0
        if previous_volume > 0 else None
    )
    price_change_pct = (
        (close / float(previous["close"]) - 1.0) * 100.0
        if previous else None
    )

    # A continuous signed confirmation measure. Positive means price and
    # volume moved in the same directional sense; negative means divergence.
    if price_change_pct is None or volume_change_pct is None:
        pv_confirmation = None
    elif price_change_pct == 0 or volume_change_pct == 0:
        pv_confirmation = 0.0
    else:
        pv_confirmation = (
            1.0 if (price_change_pct > 0) == (volume_change_pct > 0) else -1.0
        )

    return {
        "volume": volume,
        "relative_volume_20": round(relative20, 6) if relative20 is not None else None,
        "relative_volume_50": round(relative50, 6) if relative50 is not None else None,
        "volume_percentile_50": round(percentile50, 4),
        "volume_change_pct": round(volume_change_pct, 6) if volume_change_pct is not None else None,
        "price_change_pct": round(price_change_pct, 6) if price_change_pct is not None else None,
        "price_volume_confirmation": pv_confirmation,
    }
