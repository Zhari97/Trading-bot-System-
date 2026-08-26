"""Historical replay skeleton for the 15m signal engine.

Purpose: replay closed candles sequentially without future data leakage.
The engine itself is intentionally kept unchanged; this module provides the
walk-forward harness and dataset split used for later evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ReplaySplit:
    train: list[dict]
    validation: list[dict]
    out_of_sample: list[dict]


def split_time_ordered(candles: list[dict]) -> ReplaySplit:
    """Split chronologically: 50% train, 16.7% validation, 33.3% OOS.

    For a six-month source dataset this approximates 3 / 1 / 2 months.
    No shuffling is allowed.
    """
    n = len(candles)
    train_end = int(n * 0.50)
    validation_end = int(n * (0.50 + 1 / 6))
    return ReplaySplit(
        candles[:train_end],
        candles[train_end:validation_end],
        candles[validation_end:],
    )


def replay_closed_candles(
    candles: list[dict],
    signal_fn: Callable[[list[dict]], dict | None],
    minimum_history: int = 60,
) -> list[dict]:
    """Run signal_fn only on information available up to each closed candle.

    signal_fn receives a copy of candles ending at the current closed candle;
    therefore it cannot see future candles. Each returned signal is timestamped
    by the candle timestamp when available.
    """
    records = []
    for end in range(minimum_history, len(candles) + 1):
        visible = candles[:end]
        signal = signal_fn(visible)
        if signal:
            record = dict(signal)
            record["replay_timestamp"] = visible[-1].get("timestamp")
            records.append(record)
    return records


def evaluate_forward_result(
    signal: dict,
    future_candles: list[dict],
    tp_pct: float = 0.05,
) -> dict | None:
    """Evaluate TP/SL after the signal using only future candles.

    Conservative tie-break: if TP and SL are touched in the same candle,
    classify the result as SL because intrabar order is unknown.
    """
    direction = signal.get("direction")
    entry = float(signal.get("entry", 0))
    stop = float(signal.get("stop_loss", 0))
    if direction not in ("LONG", "SHORT") or entry <= 0 or stop <= 0:
        return None

    tp = entry * (1 + tp_pct) if direction == "LONG" else entry * (1 - tp_pct)
    for bars, candle in enumerate(future_candles, start=1):
        high = float(candle["high"])
        low = float(candle["low"])
        if direction == "LONG":
            hit_sl = low <= stop
            hit_tp = high >= tp
        else:
            hit_sl = high >= stop
            hit_tp = low <= tp

        if hit_sl and hit_tp:
            return {"outcome": "SL", "bars": bars, "exit": stop, "tp": tp, "sl": stop}
        if hit_sl:
            return {"outcome": "SL", "bars": bars, "exit": stop, "tp": tp, "sl": stop}
        if hit_tp:
            return {"outcome": "TP", "bars": bars, "exit": tp, "tp": tp, "sl": stop}

    return {"outcome": "OPEN", "bars": len(future_candles), "exit": future_candles[-1]["close"], "tp": tp, "sl": stop}
