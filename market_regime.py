"""Offline market-regime classifier using only closed candles."""
from __future__ import annotations


def _ema(values: list[float], period: int) -> float:
    if len(values) < period:
        raise ValueError("not enough closes for EMA")
    alpha = 2.0 / (period + 1)
    value = sum(values[:period]) / period
    for price in values[period:]:
        value = alpha * price + (1.0 - alpha) * value
    return value


def classify(candles: list[dict], min_history: int = 50) -> str:
    """Return a coarse regime label from candles visible at the signal time."""
    if len(candles) < min_history:
        return "UNKNOWN"
    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles[-14:]]
    lows = [float(c["low"]) for c in candles[-14:]]
    price = closes[-1]
    fast = _ema(closes, 20)
    slow = _ema(closes, 50)
    atr = sum(h - l for h, l in zip(highs, lows)) / len(highs)
    atr_pct = atr / price * 100.0 if price else 0.0
    trend_pct = abs(fast - slow) / price * 100.0 if price else 0.0

    # Deliberately conservative first version: thresholds are descriptive,
    # not trading rules. They will be evaluated and calibrated offline.
    if atr_pct >= 3.0:
        return "HIGH_VOL"
    if trend_pct < 0.35:
        return "RANGE"
    if fast > slow:
        return "TREND_UP"
    if fast < slow:
        return "TREND_DOWN"
    return "UNKNOWN"
