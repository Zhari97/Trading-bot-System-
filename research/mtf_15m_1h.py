"""Fixed 15m-entry / 1h-confirmation research for BTCUSDT.

This script consumes a completed historical replay.  It is intentionally a
post-replay research report: it neither imports the live signal loop nor
places, queues, or suggests an order.  The 1h direction is eligible only
after that candle has closed, and it must have been available strictly before
the 15m entry candle closed.  The strict ordering avoids an ambiguous
same-close ordering and prevents higher-timeframe lookahead.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_metrics import summarize
from research_quality_gate import evaluate as evaluate_quality_gate

SYMBOL = "BTCUSDT"
LOW_TIMEFRAME = "15m"
HIGH_TIMEFRAME = "1h"
LOW_TIMEFRAME_MINUTES = 15
HIGH_TIMEFRAME_MINUTES = 60
MAX_HIGH_TIMEFRAME_AGE_MINUTES = 240
PARTITIONS = ("train", "validation", "oos")
SCHEMA_VERSION = "mtf_15m_1h_research_v1"


def _parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp as an aware UTC datetime."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must include a timezone: {value}")
    return parsed.astimezone(timezone.utc)


def _available_at(record: dict[str, Any], minutes: int) -> datetime:
    """Return when a signal based on the record's candle could be known."""
    return _parse_timestamp(str(record["timestamp"])) + timedelta(minutes=minutes)


def _safe_iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def align_15m_with_1h(
    low_records: Iterable[dict[str, Any]],
    high_records: Iterable[dict[str, Any]],
    *,
    max_high_tf_age_minutes: int = MAX_HIGH_TIMEFRAME_AGE_MINUTES,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Filter 15m candidates using the latest *previously closed* 1h signal.

    ``high_records`` may contain ex-post fields such as ``outcome`` because it
    comes from the historical replay.  This function deliberately reads only
    the 1h timestamp and direction; none of those future-result fields can
    affect whether a 15m record is selected.
    """
    if max_high_tf_age_minutes <= 0:
        raise ValueError("max_high_tf_age_minutes must be positive")

    highs = [
        {
            "timestamp": str(row["timestamp"]),
            "direction": row["direction"],
            "available_at": _available_at(row, HIGH_TIMEFRAME_MINUTES),
        }
        for row in high_records
        if row.get("direction") in {"LONG", "SHORT"} and row.get("timestamp")
    ]
    highs.sort(key=lambda row: row["available_at"])

    lows = [
        row for row in low_records
        if row.get("direction") in {"LONG", "SHORT"} and row.get("timestamp")
    ]
    lows.sort(key=lambda row: _available_at(row, LOW_TIMEFRAME_MINUTES))

    counts: Counter[str] = Counter(
        eligible_15m_records=len(lows),
        eligible_1h_records=len(highs),
    )
    aligned: list[dict[str, Any]] = []
    high_index = 0
    latest_high: dict[str, Any] | None = None

    for low in lows:
        low_available_at = _available_at(low, LOW_TIMEFRAME_MINUTES)

        # Strictly earlier avoids using a 1h close that occurs at the same
        # moment as the 15m close, where processing order is not observable.
        while high_index < len(highs) and highs[high_index]["available_at"] < low_available_at:
            latest_high = highs[high_index]
            high_index += 1

        if latest_high is None:
            counts["rejected_no_closed_1h"] += 1
            continue

        age_minutes = (low_available_at - latest_high["available_at"]).total_seconds() / 60.0
        if age_minutes > max_high_tf_age_minutes:
            counts["rejected_stale_1h"] += 1
            continue
        if low["direction"] != latest_high["direction"]:
            counts["rejected_direction_disagreement"] += 1
            continue

        selected = dict(low)
        selected.update({
            "mtf_high_timeframe": HIGH_TIMEFRAME,
            "mtf_high_timestamp": latest_high["timestamp"],
            "mtf_high_available_at": _safe_iso(latest_high["available_at"]),
            "mtf_low_available_at": _safe_iso(low_available_at),
            "mtf_high_direction": latest_high["direction"],
            "mtf_alignment_lag_minutes": round(age_minutes, 6),
        })
        aligned.append(selected)
        counts["aligned"] += 1

    return aligned, dict(counts)


def _partition_metrics(records: list[dict[str, Any]], allocation_pct: float) -> dict[str, dict[str, Any]]:
    return {
        partition: summarize(
            [row for row in records if row.get("partition") == partition],
            allocation_pct,
        )
        for partition in PARTITIONS
    }


def build_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a fixed-rule MTF report from ``historical_engine_runner`` output."""
    symbol = payload.get("symbol")
    if symbol != SYMBOL:
        raise ValueError(f"This research is fixed to {SYMBOL}; got {symbol!r}")

    timeframes = payload.get("timeframes", {})
    try:
        low_replay = timeframes[LOW_TIMEFRAME]
        high_replay = timeframes[HIGH_TIMEFRAME]
    except KeyError as exc:
        raise ValueError("Replay output must include both 15m and 1h data") from exc

    low_records = list(low_replay.get("records", []))
    high_records = list(high_replay.get("records", []))
    allocation_pct = float(payload.get("allocation_pct", low_replay.get("allocation_pct", 5.0)))
    aligned, alignment_counts = align_15m_with_1h(low_records, high_records)
    metrics = _partition_metrics(aligned, allocation_pct)
    oos = metrics["oos"]
    oos_gate = evaluate_quality_gate({
        "oos_closed": oos["closed"],
        "oos_profit_factor": oos["profit_factor"],
        "oos_expectancy_pct": oos["expectancy_pct"],
        "oos_max_drawdown_pct": oos["max_drawdown_pct"],
    })

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": payload.get("generated_at"),
        "symbol": SYMBOL,
        "history_days": payload.get("history_days"),
        "research_only": True,
        "execution": "none",
        "method": {
            "low_timeframe": LOW_TIMEFRAME,
            "high_timeframe": HIGH_TIMEFRAME,
            "rule": "Take a 15m research signal only when the latest previously closed 1h research signal agrees.",
            "high_timeframe_available_after_minutes": HIGH_TIMEFRAME_MINUTES,
            "low_timeframe_available_after_minutes": LOW_TIMEFRAME_MINUTES,
            "same_close_policy": "reject_ambiguous_same_close",
            "max_high_timeframe_age_minutes": MAX_HIGH_TIMEFRAME_AGE_MINUTES,
            "parameters_fixed_before_evaluation": True,
            "optimization_on_oos": False,
            "live_changes": False,
            "automatic_orders": False,
        },
        "source_record_counts": {
            "15m": len(low_records),
            "1h": len(high_records),
        },
        "alignment_counts": alignment_counts,
        "metrics": metrics,
        "oos_research_gate": oos_gate,
        "records": aligned,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BTCUSDT 15m+1h research from one completed replay.")
    parser.add_argument("--input", type=Path, default=Path("backtest_results.json"))
    parser.add_argument("--output", type=Path, default=Path("research/mtf_15m_1h_results.json"))
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    report = build_report(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        "MTF 15m+1h research: "
        f"aligned={report['alignment_counts'].get('aligned', 0)} "
        f"oos_closed={report['metrics']['oos']['closed']} "
        f"gate={report['oos_research_gate']['status']}"
    )
    print(f"WROTE {args.output}")


if __name__ == "__main__":
    main()
