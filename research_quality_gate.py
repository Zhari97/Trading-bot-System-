"""Conservative gates for interpreting out-of-sample research results.

This module never changes trading signals. It only labels whether a research
result has enough evidence to be considered, rejected, or kept for observation.
"""
from __future__ import annotations


def evaluate(result: dict, *, min_oos_trades: int = 30, max_allowed_dd_pct: float = 10.0) -> dict:
    if min_oos_trades < 1:
        raise ValueError("min_oos_trades must be >= 1")
    if max_allowed_dd_pct <= 0:
        raise ValueError("max_allowed_dd_pct must be > 0")

    trades = int(result.get("oos_closed", result.get("closed", 0)) or 0)
    pf = result.get("oos_profit_factor", result.get("profit_factor"))
    expectancy = float(result.get("oos_expectancy_pct", result.get("expectancy_pct", 0.0)) or 0.0)
    drawdown = float(result.get("oos_max_drawdown_pct", result.get("max_drawdown_pct", 0.0)) or 0.0)

    if trades < min_oos_trades:
        status = "INSUFFICIENT_SAMPLE"
        reason = f"OOS trades {trades} < minimum {min_oos_trades}"
    elif drawdown > max_allowed_dd_pct:
        status = "REJECT_RISK"
        reason = f"OOS max drawdown {drawdown:.2f}% > limit {max_allowed_dd_pct:.2f}%"
    elif pf is None or float(pf) <= 1.0 or expectancy <= 0.0:
        status = "NO_EDGE"
        reason = "OOS profit factor or expectancy is not positive"
    else:
        status = "CANDIDATE"
        reason = "OOS edge and risk pass the basic research gates"

    return {
        "status": status,
        "reason": reason,
        "oos_closed": trades,
        "oos_profit_factor": None if pf is None else float(pf),
        "oos_expectancy_pct": expectancy,
        "oos_max_drawdown_pct": drawdown,
        "min_oos_trades": min_oos_trades,
        "max_allowed_dd_pct": max_allowed_dd_pct,
    }
