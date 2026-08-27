"""Research-only frozen-model volume holdout.

Loads roughly 12 months of OHLCV, replays the unchanged production signal
engine, and evaluates the six months immediately preceding the current
six-month research window as a historical holdout. No production thresholds,
signal rules, sizing, or risk logic are changed.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from historical_data import fetch_klines
from historical_engine_runner import replay_timeframe

SYMBOL = "BTCUSDT"
TIMEFRAME = "1h"
CURRENT_WINDOW_DAYS = 183
LOOKBACK_DAYS = 366
OUT = Path("research/extended_volume_holdout_results.json")


def main() -> None:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=LOOKBACK_DAYS)
    current_window_start = end - timedelta(days=CURRENT_WINDOW_DAYS)

    candles = fetch_klines(SYMBOL, TIMEFRAME, start, end)
    replay = replay_timeframe(candles, TIMEFRAME)
    holdout = [
        row for row in replay["records"]
        if row["timestamp"] < current_window_start.isoformat()
    ]

    result = {
        "generated_at": end.isoformat(),
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "lookback_days": LOOKBACK_DAYS,
        "holdout_end": current_window_start.isoformat(),
        "holdout_records": holdout,
        "holdout_count": len(holdout),
        "method": "Frozen current model evaluated on the six months immediately preceding the current six-month research window.",
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"WROTE {OUT}: {len(holdout)} holdout signals")


if __name__ == "__main__":
    main()
