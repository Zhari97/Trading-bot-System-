"""Historical OHLC loader for Binance public klines.

Downloads candles in bounded chunks for 5m/15m/1h experiments. Public market
klines require no API key. The module is data-only: it never places orders.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import requests

BASE_URL = "https://api.binance.com/api/v3/klines"
INTERVALS = {"5m": "5m", "15m": "15m", "1h": "1h"}
LIMIT = 1000


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def fetch_klines(symbol: str, interval: str, start: datetime, end: datetime) -> list[dict]:
    if interval not in INTERVALS:
        raise ValueError(f"Unsupported interval: {interval}")
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start/end must be timezone-aware")

    rows: list[dict] = []
    cursor = _ms(start)
    end_ms = _ms(end)

    while cursor < end_ms:
        response = requests.get(
            BASE_URL,
            params={
                "symbol": symbol.upper(),
                "interval": INTERVALS[interval],
                "startTime": cursor,
                "endTime": end_ms,
                "limit": LIMIT,
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        if not data:
            break

        for k in data:
            rows.append({
                "timestamp": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).isoformat(),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_timestamp": int(k[6]),
            })

        next_cursor = int(data[-1][6]) + 1
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        time.sleep(0.15)

    return rows


def load_six_months(symbol: str, end: datetime) -> dict[str, list[dict]]:
    """Return approximately six months for each candidate timeframe."""
    # 183 days is deliberate: enough history while keeping the first pass bounded.
    from datetime import timedelta
    start = end - timedelta(days=183)
    return {tf: fetch_klines(symbol, tf, start, end) for tf in INTERVALS}
