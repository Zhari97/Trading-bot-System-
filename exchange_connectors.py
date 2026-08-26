"""Public market-data adapters for Binance, Kraken and Coinbase.

Observation-only: no private endpoints and no order placement.
The adapters return the canonical snapshot shape used by the inefficiency layer.
"""

from __future__ import annotations

import time
import requests

from multi_exchange_schema import MarketSnapshot

TIMEOUT = 10


def _get(url: str, params: dict | None = None) -> dict:
    response = requests.get(url, params=params, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def binance_ticker(symbol: str) -> MarketSnapshot:
    data = _get("https://api.binance.com/api/v3/ticker/bookTicker", {"symbol": symbol.upper()})
    return MarketSnapshot(int(time.time() * 1000), "binance", symbol.upper(), float(data["bidPrice"]), float(data["askPrice"]))


def kraken_ticker(pair: str) -> MarketSnapshot:
    data = _get("https://api.kraken.com/0/public/Ticker", {"pair": pair})
    result = data.get("result", {})
    if not result:
        raise ValueError(f"Kraken: no ticker for {pair}")
    ticker = next(iter(result.values()))
    return MarketSnapshot(int(time.time() * 1000), "kraken", pair.upper(), float(ticker["b"][0]), float(ticker["a"][0]))


def coinbase_ticker(product: str) -> MarketSnapshot:
    data = _get(f"https://api.exchange.coinbase.com/products/{product.upper()}/ticker")
    return MarketSnapshot(int(time.time() * 1000), "coinbase", product.upper(), float(data["bid"]), float(data["ask"]), float(data["price"]), float(data.get("volume", 0)))
