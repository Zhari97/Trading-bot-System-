"""Historical replay utilities with no future-data leakage."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ReplaySplit:
    train: list[dict]
    validation: list[dict]
    out_of_sample: list[dict]


def split_time_ordered(candles: list[dict]) -> ReplaySplit:
    n = len(candles)
    train_end = int(n * 0.50)
    validation_end = int(n * (0.50 + 1 / 6))
    return ReplaySplit(candles[:train_end], candles[train_end:validation_end], candles[validation_end:])


def replay_closed_candles(
    candles: list[dict],
    signal_fn: Callable[[list[dict]], dict | None],
    minimum_history: int = 60,
) -> list[dict]:
    records = []
    for end in range(minimum_history, len(candles) + 1):
        visible = candles[:end]
        signal = signal_fn(visible)
        if signal:
            record = dict(signal)
            record["replay_timestamp"] = visible[-1].get("timestamp")
            records.append(record)
    return records


def evaluate_forward_result(signal: dict, future_candles: list[dict], tp_pct: float = 0.05) -> dict | None:
    """Evaluate TP/SL using only candles after the signal.

    If the signal contains an explicit ``take_profit`` price, that level wins
    over the percentage fallback. If TP and SL occur in the same candle, SL is
    selected conservatively because intrabar order is unknown.
    """
    direction = signal.get("direction")
    entry = float(signal.get("entry", 0) or 0)
    stop = float(signal.get("stop_loss", 0) or 0)
    if direction not in ("LONG", "SHORT") or entry <= 0 or stop <= 0 or not future_candles:
        return None

    supplied_tp = signal.get("take_profit")
    tp = float(supplied_tp) if supplied_tp is not None else (
        entry * (1 + tp_pct) if direction == "LONG" else entry * (1 - tp_pct)
    )
    if tp <= 0:
        return None

    for bars, candle in enumerate(future_candles, start=1):
        high = float(candle["high"])
        low = float(candle["low"])
        if direction == "LONG":
            hit_sl, hit_tp = low <= stop, high >= tp
        else:
            hit_sl, hit_tp = high >= stop, low <= tp

        if hit_sl and hit_tp:
            return {"outcome": "SL", "bars": bars, "exit": stop, "tp": tp, "sl": stop}
        if hit_sl:
            return {"outcome": "SL", "bars": bars, "exit": stop, "tp": tp, "sl": stop}
        if hit_tp:
            return {"outcome": "TP", "bars": bars, "exit": tp, "tp": tp, "sl": stop}

    return {"outcome": "OPEN", "bars": len(future_candles), "exit": future_candles[-1]["close"], "tp": tp, "sl": stop}
