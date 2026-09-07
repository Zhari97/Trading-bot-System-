"""Research-only execution realism helpers.

Adapted conceptually from the reviewed execution-cost research: explicit
slippage, spread, impact, funding and ADV participation prevent a backtest
from assuming infinite liquidity. No exchange calls are made here.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionScenario:
    name: str
    fee_bps_round_trip: float = 0.0
    spread_bps_round_trip: float = 0.0
    slippage_bps_round_trip: float = 0.0
    impact_model: str = "fixed"
    impact_coefficient: float = 0.0
    max_participation: float = 0.10


@dataclass(frozen=True)
class ExecutionCost:
    total_cost_pct: float
    participation: float
    capped: bool
    model: str


def cap_order_notional(
    order_notional: float,
    adv_notional: float,
    *,
    max_participation: float = 0.10,
) -> tuple[float, float, bool]:
    """Cap an order to a configurable fraction of ADV."""
    if order_notional < 0 or adv_notional < 0:
        raise ValueError("notional values must be non-negative")
    if not 0.0 < max_participation <= 1.0:
        raise ValueError("max_participation must be in (0, 1]")
    if adv_notional <= 0:
        return 0.0, 0.0, order_notional > 0
    capacity = adv_notional * max_participation
    filled = min(order_notional, capacity)
    participation = filled / adv_notional
    return filled, participation, order_notional > filled


def estimate_cost(
    scenario: ExecutionScenario,
    *,
    order_notional: float,
    adv_notional: float | None = None,
    volatility: float = 0.0,
) -> ExecutionCost:
    """Estimate round-trip execution drag as a percentage of notional.

    ``volatility`` is a decimal per execution period (e.g. 0.01 for 1%).
    The square-root model follows the conservative research pattern
    ``coefficient * volatility * sqrt(participation)``.
    """
    if order_notional < 0 or volatility < 0:
        raise ValueError("order_notional and volatility must be non-negative")
    if scenario.impact_model not in {"fixed", "linear", "sqrt"}:
        raise ValueError("impact_model must be fixed, linear or sqrt")
    if scenario.impact_coefficient < 0:
        raise ValueError("impact_coefficient must be non-negative")

    if adv_notional is None:
        filled = order_notional
        participation = 0.0
        capped = False
    else:
        filled, participation, capped = cap_order_notional(
            order_notional, adv_notional, max_participation=scenario.max_participation
        )

    fixed_cost = (
        scenario.fee_bps_round_trip
        + scenario.spread_bps_round_trip
        + scenario.slippage_bps_round_trip
    ) / 100.0

    if scenario.impact_model == "fixed" or filled == 0:
        impact_pct = 0.0
    elif scenario.impact_model == "linear":
        impact_pct = scenario.impact_coefficient * participation * 100.0
    else:
        impact_pct = scenario.impact_coefficient * volatility * math.sqrt(max(participation, 0.0)) * 100.0

    return ExecutionCost(
        total_cost_pct=fixed_cost + impact_pct,
        participation=participation,
        capped=capped,
        model=scenario.impact_model,
    )


def net_return_pct(gross_return_pct: float, execution_cost_pct: float, funding_pct: float = 0.0) -> float:
    """Subtract explicit execution/funding drag from a gross trade return."""
    if execution_cost_pct < 0 or funding_pct < 0:
        raise ValueError("costs must be non-negative")
    return gross_return_pct - execution_cost_pct - funding_pct
