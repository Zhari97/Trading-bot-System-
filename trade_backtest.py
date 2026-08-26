"""Backtest informativo dei trade plan.

Non esegue ordini. Riceve una serie OHLC e segnali gia' generati dal motore,
simula entry, TP +5% e SL ATR-based e restituisce metriche aggregate.
"""

from dataclasses import dataclass


TP_PCT = 0.05
MAX_ALLOCATION_PCT = 0.05


@dataclass
class SimulatedTrade:
    direction: str
    entry: float
    take_profit: float
    stop_loss: float
    outcome: str
    exit_price: float
    bars_held: int
    pnl_pct_price: float
    pnl_pct_account_at_max_allocation: float


def simulate_trade(signal: dict, future_candles: list[dict]) -> SimulatedTrade | None:
    """Simula un singolo segnale usando solo candele successive all'entry.

    Se TP e SL vengono toccati nella stessa candela, usa una regola conservativa:
    lo stop viene considerato colpito prima del target.
    """
    direction = signal.get("direction")
    entry = float(signal.get("entry", 0))
    sl = float(signal.get("stop_loss", 0))
    if direction not in ("LONG", "SHORT") or entry <= 0 or not future_candles:
        return None

    tp = entry * (1 + TP_PCT) if direction == "LONG" else entry * (1 - TP_PCT)
    for idx, candle in enumerate(future_candles, start=1):
        high = float(candle["high"])
        low = float(candle["low"])

        if direction == "LONG":
            hit_sl = low <= sl
            hit_tp = high >= tp
            if hit_sl and hit_tp:
                return SimulatedTrade(direction, entry, tp, sl, "SL", sl, idx, (sl / entry - 1) * 100, (sl / entry - 1) * MAX_ALLOCATION_PCT * 100)
            if hit_sl:
                return SimulatedTrade(direction, entry, tp, sl, "SL", sl, idx, (sl / entry - 1) * 100, (sl / entry - 1) * MAX_ALLOCATION_PCT * 100)
            if hit_tp:
                return SimulatedTrade(direction, entry, tp, sl, "TP", tp, idx, (tp / entry - 1) * 100, (tp / entry - 1) * MAX_ALLOCATION_PCT * 100)
        else:
            hit_sl = high >= sl
            hit_tp = low <= tp
            if hit_sl and hit_tp:
                return SimulatedTrade(direction, entry, tp, sl, "SL", sl, idx, (1 - sl / entry) * 100, (1 - sl / entry) * MAX_ALLOCATION_PCT * 100)
            if hit_sl:
                return SimulatedTrade(direction, entry, tp, sl, "SL", sl, idx, (1 - sl / entry) * 100, (1 - sl / entry) * MAX_ALLOCATION_PCT * 100)
            if hit_tp:
                return SimulatedTrade(direction, entry, tp, sl, "TP", tp, idx, (1 - tp / entry) * 100, (1 - tp / entry) * MAX_ALLOCATION_PCT * 100)

    return None


def summarize_trades(trades: list[SimulatedTrade]) -> dict:
    closed = [t for t in trades if t.outcome in ("TP", "SL")]
    wins = [t for t in closed if t.outcome == "TP"]
    losses = [t for t in closed if t.outcome == "SL"]
    gross_profit = sum(max(t.pnl_pct_account_at_max_allocation, 0) for t in wins)
    gross_loss = abs(sum(min(t.pnl_pct_account_at_max_allocation, 0) for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss else None

    return {
        "signals": len(trades),
        "closed": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": (len(wins) / len(closed) * 100) if closed else 0.0,
        "profit_factor": profit_factor,
        "avg_bars_held": (sum(t.bars_held for t in closed) / len(closed)) if closed else 0.0,
        "account_pnl_pct_at_max_allocation": sum(t.pnl_pct_account_at_max_allocation for t in closed),
    }
