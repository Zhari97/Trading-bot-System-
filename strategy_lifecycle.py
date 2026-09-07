"""Strategy lifecycle and configurable decay diagnostics.

The reviewed trading systems treat a strategy as a lifecycle object rather than
an eternal backtest result. This implementation keeps transitions explicit and
configurable; it does not auto-promote anything to LIVE.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class StrategyStatus(str, Enum):
    RESEARCH = "RESEARCH"
    CANDIDATE = "CANDIDATE"
    SHADOW = "SHADOW"
    PAPER = "PAPER"
    LIVE = "LIVE"
    MONITORING = "MONITORING"
    DECAYED = "DECAYED"
    DISABLED = "DISABLED"


_ALLOWED: dict[StrategyStatus, set[StrategyStatus]] = {
    StrategyStatus.RESEARCH: {StrategyStatus.CANDIDATE, StrategyStatus.DISABLED},
    StrategyStatus.CANDIDATE: {StrategyStatus.SHADOW, StrategyStatus.MONITORING, StrategyStatus.DISABLED},
    StrategyStatus.SHADOW: {StrategyStatus.PAPER, StrategyStatus.MONITORING, StrategyStatus.DECAYED, StrategyStatus.DISABLED},
    StrategyStatus.PAPER: {StrategyStatus.LIVE, StrategyStatus.MONITORING, StrategyStatus.DECAYED, StrategyStatus.DISABLED},
    StrategyStatus.LIVE: {StrategyStatus.MONITORING, StrategyStatus.DECAYED, StrategyStatus.DISABLED},
    StrategyStatus.MONITORING: {StrategyStatus.PAPER, StrategyStatus.LIVE, StrategyStatus.DECAYED, StrategyStatus.DISABLED},
    StrategyStatus.DECAYED: {StrategyStatus.MONITORING, StrategyStatus.DISABLED},
    StrategyStatus.DISABLED: {StrategyStatus.RESEARCH},
}


@dataclass(frozen=True)
class DecayThresholds:
    """Relative/absolute checks; values are deliberately configurable."""
    min_observations: int = 30
    warning_return_ratio: float = 0.75
    decay_return_ratio: float = 0.50
    warning_pf_ratio: float = 0.85
    decay_pf_ratio: float = 0.70


@dataclass(frozen=True)
class DecayAssessment:
    status: str
    reasons: tuple[str, ...]
    observations: int


def transition(current: StrategyStatus, target: StrategyStatus) -> StrategyStatus:
    """Validate an explicit lifecycle transition."""
    if target not in _ALLOWED[current]:
        raise ValueError(f"invalid strategy transition: {current.value} -> {target.value}")
    return target


def assess_decay(
    baseline: Mapping[str, float],
    current: Mapping[str, float],
    *,
    thresholds: DecayThresholds = DecayThresholds(),
) -> DecayAssessment:
    """Compare current rolling metrics to a frozen baseline.

    Expected keys are ``observations``, ``return_pct`` and ``profit_factor``.
    With insufficient observations the result is ``INSUFFICIENT_DATA`` rather
    than a false healthy/decayed classification.
    """
    observations = int(current.get("observations", 0))
    if observations < thresholds.min_observations:
        return DecayAssessment("INSUFFICIENT_DATA", ("not_enough_observations",), observations)

    reasons: list[str] = []
    base_return = float(baseline.get("return_pct", 0.0))
    cur_return = float(current.get("return_pct", 0.0))
    base_pf = float(baseline.get("profit_factor", 0.0))
    cur_pf = float(current.get("profit_factor", 0.0))

    return_ratio = cur_return / base_return if base_return > 0 else (1.0 if cur_return >= 0 else 0.0)
    pf_ratio = cur_pf / base_pf if base_pf > 0 else (1.0 if cur_pf >= 1.0 else 0.0)

    if return_ratio < thresholds.decay_return_ratio:
        reasons.append("rolling_return_below_decay_ratio")
    if pf_ratio < thresholds.decay_pf_ratio:
        reasons.append("rolling_profit_factor_below_decay_ratio")
    if reasons:
        return DecayAssessment("DECAYED", tuple(reasons), observations)

    if return_ratio < thresholds.warning_return_ratio:
        reasons.append("rolling_return_below_warning_ratio")
    if pf_ratio < thresholds.warning_pf_ratio:
        reasons.append("rolling_profit_factor_below_warning_ratio")
    if reasons:
        return DecayAssessment("WARNING", tuple(reasons), observations)

    return DecayAssessment("HEALTHY", (), observations)
