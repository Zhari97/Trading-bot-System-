"""Metrics for evaluating replayed trade results.

Research-only: metrics never feed back into live execution automatically.
"""

from __future__ import annotations


def summarize(results: list[dict]) -> dict:
    closed = [r for r in results if r.get("outcome") in ("TP", "SL")]
    wins = [r for r in closed if r.get("outcome") == "TP"]
    losses = [r for r in closed if r.get("outcome") == "SL"]

    returns = []
    for r in closed:
        entry = float(r.get("entry", 0) or 0)
        exit_price = float(r.get("exit", 0) or 0)
        direction = r.get("direction")
        if entry <= 0 or exit_price <= 0:
            continue
        ret = (exit_price / entry - 1) * 100
        returns.append(ret if direction == "LONG" else -ret)

    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for ret in returns:
        equity += ret
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    gross_profit = sum(x for x in returns if x > 0)
    gross_loss = abs(sum(x for x in returns if x < 0))

    return {
        "signals": len(results),
        "closed": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": len(wins) / len(closed) * 100 if closed else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "expectancy_pct": sum(returns) / len(returns) if returns else 0.0,
        "max_drawdown_pct": max_dd,
        "avg_bars_held": sum(float(r.get("bars", 0)) for r in closed) / len(closed) if closed else 0.0,
    }
