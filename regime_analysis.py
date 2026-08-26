"""Offline market-regime analysis for research and stratification."""
from __future__ import annotations


def classify_regime(candles: list[dict], lookback: int = 48, trend_threshold_pct: float = 1.0, volatility_threshold_pct: float = 2.0) -> str:
    if len(candles) < lookback + 1:
        return "UNKNOWN"
    closes = [float(row["close"]) for row in candles[-(lookback + 1):]]
    start, end = closes[0], closes[-1]
    if start <= 0:
        return "UNKNOWN"
    trend_pct = (end / start - 1.0) * 100.0
    returns = [(closes[i] / closes[i - 1] - 1.0) * 100.0 for i in range(1, len(closes))]
    avg_abs_move = sum(abs(x) for x in returns) / len(returns)
    if abs(trend_pct) >= trend_threshold_pct:
        return "TREND_UP" if trend_pct > 0 else "TREND_DOWN"
    if avg_abs_move >= volatility_threshold_pct:
        return "HIGH_VOL_RANGE"
    return "RANGE"


def stratify(records: list[dict], candles_by_timeframe: dict[str, list[dict]]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for record in records:
        timeframe = record.get("timeframe", "unknown")
        candles = candles_by_timeframe.get(timeframe, [])
        regime = classify_regime(candles)
        row = dict(record)
        row["regime"] = regime
        grouped.setdefault(regime, []).append(row)
    return grouped
