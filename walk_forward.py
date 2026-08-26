"""Walk-forward research utilities.

The out-of-sample window is never used to fit or select parameters. This
module only partitions chronologically and evaluates supplied experiments.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any


@dataclass(frozen=True)
class Window:
    name: str
    rows: list[dict]


def chronological_windows(rows: list[dict], train_frac: float = 0.50, validation_frac: float = 1 / 6) -> tuple[Window, Window, Window]:
    if not rows:
        return Window("train", []), Window("validation", []), Window("oos", [])
    if not 0 < train_frac < 1 or not 0 < validation_frac < 1 or train_frac + validation_frac >= 1:
        raise ValueError("invalid walk-forward fractions")
    n = len(rows)
    a = int(n * train_frac)
    b = a + int(n * validation_frac)
    return Window("train", rows[:a]), Window("validation", rows[a:b]), Window("oos", rows[b:])


def evaluate_parameter_grid(
    train_rows: list[dict],
    validation_rows: list[dict],
    candidates: list[Any],
    evaluator: Callable[[list[dict], Any], dict],
    key: Callable[[dict], tuple] = lambda m: (m.get("profit_factor") or 0.0, m.get("expectancy_pct", 0.0)),
) -> tuple[Any, dict, dict]:
    """Select a candidate using train only, validate it once, and return both."""
    if not candidates:
        raise ValueError("candidate grid is empty")
    train_scores = [(candidate, evaluator(train_rows, candidate)) for candidate in candidates]
    best_candidate, best_train = max(train_scores, key=lambda x: key(x[1]))
    validation = evaluator(validation_rows, best_candidate)
    return best_candidate, best_train, validation
