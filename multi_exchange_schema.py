"""Canonical multi-exchange market-data schema.

Phase 1 is observation/simulation only. It does not place orders.
"""

from dataclasses import dataclass
from typing import Optional


EXCHANGES = ("binance", "kraken", "coinbase")


@dataclass(frozen=True)
class MarketSnapshot:
    timestamp_ms: int
    exchange: str
    symbol: str
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    volume: Optional[float] = None
    funding_rate: Optional[float] = None
    open_interest: Optional[float] = None


def executable_spread_pct(buy_ask: float, sell_bid: float) -> float:
    """Gross cross-exchange spread available before fees/slippage."""
    if buy_ask <= 0:
        return 0.0
    return (sell_bid / buy_ask - 1.0) * 100.0


def net_spread_pct(
    buy_ask: float,
    sell_bid: float,
    buy_fee_pct: float,
    sell_fee_pct: float,
    slippage_pct: float = 0.0,
    transfer_cost_pct: float = 0.0,
) -> float:
    """Estimated spread after explicit costs; still simulation-only."""
    gross = executable_spread_pct(buy_ask, sell_bid)
    return gross - buy_fee_pct - sell_fee_pct - slippage_pct - transfer_cost_pct
