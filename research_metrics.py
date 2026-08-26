"""Research metrics for replayed trades.

Portfolio metrics use the configured capital allocation instead of treating
 every signal as if it used 100% of the account. Research only.
"""
from __future__ import annotations


def summarize(results: list[dict], allocation_pct: float = 5.0) -> dict:
    if not 0 < allocation_pct <= 100:
        raise ValueError("allocation_pct must be in (0, 100]")

    closed = [r for r in results if r.get("outcome") in ("TP", "SL")]
    wins = [r for r in closed if r.get("outcome") == "TP"]
    losses = [r for r in closed if r.get("outcome") == "SL"]

    trade_returns: list[float] = []
    portfolio_returns: list[float] = []
    for r in closed:
        entry = float(r.get("entry", 0) or 0)
        exit_price = float(r.get("exit", 0) or 0)
        direction = r.get("direction")
        if entry <= 0 or exit_price <= 0 or direction not in ("LONG", "SHORT"):
            continue
        raw = (exit_price / entry - 1.0) * 100.0
        gross = raw if direction == "LONG" else -raw
        trade_returns.append(gross)
        portfolio_returns.append(gross * allocation_pct / 100.0)

    equity = peak = max_dd = 0.0
    for ret in portfolio_returns:
        equity += ret
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    gross_profit = sum(x for x in portfolio_returns if x > 0)
    gross_loss = abs(sum(x for x in portfolio_returns if x < 0))
    return {
        "signals": len(results),
        "closed": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": len(wins) / len(closed) * 100 if closed else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "expectancy_pct": sum(portfolio_returns) / len(portfolio_returns) if portfolio_returns else 0.0,
        "trade_expectancy_pct": sum(trade_returns) / len(trade_returns) if trade_returns else 0.0,
        "portfolio_return_pct": equity,
        "max_drawdown_pct": max_dd,
        "allocation_pct": allocation_pct,
        "avg_bars_held": sum(float(r.get("bars", 0)) for r in closed) / len(closed) if closed else 0.0,
    }
