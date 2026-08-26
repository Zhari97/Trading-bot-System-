"""Offline execution-cost model for realistic backtests.

No live orders or exchange calls. Costs are explicit so an apparent edge
cannot be mistaken for a net tradable edge.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    entry_fee_pct: float = 0.0
    exit_fee_pct: float = 0.0
    slippage_pct: float = 0.0
    spread_pct: float = 0.0
    funding_pct_per_period: float = 0.0

    def round_trip_cost_pct(self, periods_held: int = 0) -> float:
        return (
            self.entry_fee_pct
            + self.exit_fee_pct
            + self.slippage_pct
            + self.spread_pct
            + max(0, periods_held) * self.funding_pct_per_period
        )


def net_pnl_pct(gross_pnl_pct: float, costs: CostModel, periods_held: int = 0) -> float:
    return gross_pnl_pct - costs.round_trip_cost_pct(periods_held)
