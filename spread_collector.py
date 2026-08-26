"""Synchronized multi-exchange observation collector.

Read-only research component. It samples public top-of-book quotes and
calculates gross/net cross-exchange spreads. It does not place orders.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from exchange_connectors import binance_ticker, coinbase_ticker, kraken_ticker
from multi_exchange_schema import MarketSnapshot, net_spread_pct


DEFAULTS = {
    "binance": "BTCUSDT",
    "kraken": "XBTUSD",
    "coinbase": "BTC-USD",
}


def collect_once() -> list[MarketSnapshot]:
    snapshots: list[MarketSnapshot] = []
    snapshots.append(binance_ticker(DEFAULTS["binance"]))
    snapshots.append(kraken_ticker(DEFAULTS["kraken"]))
    snapshots.append(coinbase_ticker(DEFAULTS["coinbase"]))
    return snapshots


def quote_age_ms(now_ms: int, snapshot: MarketSnapshot) -> int:
    return max(0, now_ms - snapshot.timestamp_ms)


def pairwise_opportunities(
    snapshots: list[MarketSnapshot],
    fees_pct: dict[str, float] | None = None,
    slippage_pct: float = 0.0,
) -> list[dict]:
    fees_pct = fees_pct or {}
    rows: list[dict] = []
    now = int(time.time() * 1000)
    for buy in snapshots:
        for sell in snapshots:
            if buy.exchange == sell.exchange:
                continue
            if not buy.ask or not sell.bid:
                continue
            # Require fresh quotes before comparing them.
            if quote_age_ms(now, buy) > 5000 or quote_age_ms(now, sell) > 5000:
                continue
            gross = (sell.bid / buy.ask - 1.0) * 100.0
            net = net_spread_pct(
                buy.ask,
                sell.bid,
                fees_pct.get(buy.exchange, 0.0),
                fees_pct.get(sell.exchange, 0.0),
                slippage_pct,
            )
            rows.append({
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "buy_exchange": buy.exchange,
                "sell_exchange": sell.exchange,
                "buy_ask": buy.ask,
                "sell_bid": sell.bid,
                "gross_spread_pct": gross,
                "net_spread_pct": net,
                "quote_age_buy_ms": quote_age_ms(now, buy),
                "quote_age_sell_ms": quote_age_ms(now, sell),
            })
    return rows
