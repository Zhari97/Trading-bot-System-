"""Research-only frozen-model volume holdout.

Replays the unchanged production signal engine over a historical window and
keeps only signals from the six-month holdout immediately preceding the
current research window. The holdout is never used to tune the model.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from historical_data import fetch_klines
from historical_engine_runner import replay_timeframe

SYMBOL = "BTCUSDT"
TIMEFRAME = "1h"
HOLDOUT_DAYS = 183
LOOKBACK_DAYS = 366
OUT = ROOT / "research" / "extended_volume_holdout_results.json"


def main() -> None:
    end = datetime.now(timezone.utc)
    holdout_end = end - timedelta(days=HOLDOUT_DAYS)
    start = end - timedelta(days=LOOKBACK_DAYS)

    candles = fetch_klines(SYMBOL, TIMEFRAME, start, end)
    replay = replay_timeframe(candles, TIMEFRAME)

    # Use explicit timestamps rather than replay_timeframe's internal
    # train/validation/OOS partitions. This makes the holdout a genuine
    # contiguous historical period independent of the current backtest split.
    holdout_start = start.isoformat()
    holdout_end_iso = holdout_end.isoformat()
    holdout = [
        row for row in replay["records"]
        if holdout_start <= row["timestamp"] < holdout_end_iso
    ]

    result = {
        "generated_at": end.isoformat(),
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "lookback_days": LOOKBACK_DAYS,
        "holdout_days": HOLDOUT_DAYS,
        "holdout_start": holdout_start,
        "holdout_end": holdout_end_iso,
        "holdout_records": holdout,
        "holdout_count": len(holdout),
        "method": "Frozen current model evaluated on the contiguous six-month period immediately preceding the current six-month research window.",
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"WROTE {OUT}: {len(holdout)} holdout signals")


if __name__ == "__main__":
    main()
