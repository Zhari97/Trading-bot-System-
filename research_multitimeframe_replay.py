"""Walk-forward replay across 5m/15m/1h using the shared signal engine.

This research module does not touch the live workflow. It converts historical
OHLC rows into the same candle shape expected by the engine, runs signals only
on closed information, and compares timeframe experiments without shuffling.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from historical_replay import evaluate_forward_result, split_time_ordered
from timeframe_evaluator import EXPERIMENTS


@dataclass(frozen=True)
class ReplayResult:
    experiment: str
    timeframe: str
    train_signals: int
    validation_signals: int
    oos_signals: int
    train_closed: int
    validation_closed: int
    oos_closed: int
    train_win_rate_pct: float
    validation_win_rate_pct: float
    oos_win_rate_pct: float


def _win_rate(records: list[dict]) -> float:
    closed = [r for r in records if r.get("outcome") in ("TP", "SL")]
    if not closed:
        return 0.0
    return 100.0 * sum(r["outcome"] == "TP" for r in closed) / len(closed)


def replay_one(
    candles: list[dict],
    signal_fn: Callable[[list[dict]], dict | None],
    future_bars: int = 96,
) -> list[dict]:
    """Generate signals sequentially and evaluate them only on future bars."""
    records: list[dict] = []
    minimum_history = 60
    for end in range(minimum_history, len(candles)):
        visible = candles[:end]
        signal = signal_fn(visible)
        if not signal:
            continue
        future = candles[end:min(end + future_bars, len(candles))]
        result = evaluate_forward_result(signal, future)
        if result:
            row = dict(signal)
            row.update(result)
            row["replay_timestamp"] = visible[-1].get("timestamp")
            records.append(row)
    return records


def run_experiment(
    datasets: dict[str, list[dict]],
    signal_functions: dict[str, Callable[[list[dict]], dict | None]],
) -> list[ReplayResult]:
    """Run the configured timeframe experiments on already-fetched datasets."""
    results: list[ReplayResult] = []
    for name, timeframes in EXPERIMENTS.items():
        for timeframe in timeframes:
            candles = datasets[timeframe]
            fn = signal_functions[timeframe]
            split = split_time_ordered(candles)
            partitions = (
                ("train", split.train),
                ("validation", split.validation),
                ("oos", split.out_of_sample),
            )
            stats = {}
            for label, part in partitions:
                records = replay_one(part, fn)
                stats[f"{label}_signals"] = len(records)
                stats[f"{label}_closed"] = sum(r.get("outcome") in ("TP", "SL") for r in records)
                stats[f"{label}_win_rate_pct"] = _win_rate(records)
            results.append(ReplayResult(experiment=name, timeframe=timeframe, **stats))
    return results
