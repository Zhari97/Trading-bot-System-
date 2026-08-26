"""Offline Monte Carlo robustness analysis for closed-trade returns."""
from __future__ import annotations

import random
import statistics


def simulate_equity(returns_pct: list[float], trials: int = 1000, seed: int = 42) -> dict:
    if not returns_pct:
        return {"trials": 0, "median_return_pct": 0.0, "worst_return_pct": 0.0, "p05_return_pct": 0.0, "p95_return_pct": 0.0}
    rng = random.Random(seed)
    terminal: list[float] = []
    for _ in range(trials):
        equity = 0.0
        for value in rng.sample(returns_pct, len(returns_pct)):
            equity += value
        terminal.append(equity)
    terminal.sort()
    q = lambda p: terminal[min(len(terminal) - 1, int((len(terminal) - 1) * p))]
    return {
        "trials": trials,
        "median_return_pct": statistics.median(terminal),
        "worst_return_pct": terminal[0],
        "p05_return_pct": q(0.05),
        "p95_return_pct": q(0.95),
    }
