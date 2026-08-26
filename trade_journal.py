"""Research-only trade journal and risk attribution model.

Keeps strategy performance separate from capital-management effects.
It records immutable trade facts and computes portfolio-level statistics.
No live execution, alerts, or order placement are performed here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass(frozen=True)
class TradeRecord:
    timestamp: str
    timeframe: str
    direction: str
    score: float
    confluence: float
    entry: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    allocation_pct: float
    outcome: str
    exit_price: Optional[float] = None
    bars_held: int = 0
    pnl_pct: Optional[float] = None
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def calculate_pnl_pct(direction: str, entry: float, exit_price: float) -> float:
    if entry <= 0 or exit_price <= 0:
        raise ValueError("entry and exit_price must be positive")
    raw = (exit_price / entry - 1.0) * 100.0
    return raw if direction.upper() == "LONG" else -raw


def summarize_journal(records: list[TradeRecord]) -> dict:
    closed = [r for r in records if r.outcome in {"TP", "SL", "CLOSE"} and r.pnl_pct is not None]
    wins = [r for r in closed if r.pnl_pct > 0]
    losses = [r for r in closed if r.pnl_pct < 0]
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for record in closed:
        equity += float(record.pnl_pct or 0.0) * (record.allocation_pct / 100.0)
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    gross_profit = sum(r.pnl_pct * r.allocation_pct / 100.0 for r in wins)
    gross_loss = abs(sum(r.pnl_pct * r.allocation_pct / 100.0 for r in losses))
    return {
        "signals": len(records),
        "closed_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": 100.0 * len(wins) / len(closed) if closed else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "portfolio_return_pct": equity,
        "max_drawdown_pct": max_drawdown,
        "avg_trade_pnl_pct": sum(r.pnl_pct for r in closed) / len(closed) if closed else 0.0,
        "avg_bars_held": sum(r.bars_held for r in closed) / len(closed) if closed else 0.0,
    }
