"""Research-only analysis for 1h volume/regime/direction/score relationships.

This module is deliberately outside the live signal path. It reads the actual
nested backtest_results.json schema and produces deterministic diagnostics.
It does not alter signals, thresholds, sizing, or risk.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

PARTITIONS = ("train", "validation", "oos")
TIMEFRAME = "1h"


def _records(payload: Any) -> list[dict[str, Any]]:
    """Read the production backtest schema: {timeframes: {1h: {records: []}}}."""
    if not isinstance(payload, dict):
        raise ValueError("backtest_results.json must contain an object")
    timeframes = payload.get("timeframes")
    if isinstance(timeframes, dict):
        timeframe = timeframes.get(TIMEFRAME)
        if isinstance(timeframe, dict) and isinstance(timeframe.get("records"), list):
            return [x for x in timeframe["records"] if isinstance(x, dict)]
    # Keep support for a simple list-shaped research fixture.
    if isinstance(payload.get("records"), list):
        return [x for x in payload["records"] if isinstance(x, dict)]
    raise ValueError("Could not find 1h records in backtest_results.json")


def _partition(row: dict[str, Any]) -> str | None:
    value = str(row.get("partition", row.get("split", ""))).lower()
    return value if value in PARTITIONS else None


def _outcome(row: dict[str, Any]) -> int | None:
    value = str(row.get("outcome", row.get("result", ""))).upper()
    if value in {"TP", "WIN", "WON"}:
        return 1
    if value in {"SL", "LOSS", "LOST"}:
        return 0
    return None


def _score_bucket(score: float) -> str:
    if score < 40:
        return "<40"
    if score < 60:
        return "40-60"
    if score < 80:
        return "60-80"
    return "80-100"


def _volume_confirmation(row: dict[str, Any]) -> int | None:
    value = row.get("volume_research", {}).get("price_volume_confirmation")
    try:
        return int(float(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _trade_return(row: dict[str, Any]) -> float | None:
    """Derive realized trade return from entry/exit because records store prices."""
    try:
        entry = float(row["entry"])
        exit_price = float(row["exit"])
        direction = str(row["direction"]).upper()
    except (KeyError, TypeError, ValueError):
        return None
    if entry <= 0 or not math.isfinite(entry) or not math.isfinite(exit_price):
        return None
    raw = (exit_price / entry - 1.0) * 100.0
    return raw if direction == "LONG" else -raw if direction == "SHORT" else None


def analyse(path: Path) -> list[dict[str, Any]]:
    rows = _records(json.loads(path.read_text(encoding="utf-8")))
    output: list[dict[str, Any]] = []
    for row in rows:
        partition = _partition(row)
        outcome = _outcome(row)
        direction = str(row.get("direction", "")).upper()
        regime = str(row.get("regime", "")).upper()
        try:
            score = float(row.get("research_score", row.get("score")))
        except (TypeError, ValueError):
            continue
        volume_confirmation = _volume_confirmation(row)
        if partition is None or outcome is None or direction not in {"LONG", "SHORT"}:
            continue
        if volume_confirmation is None:
            continue
        output.append({
            "partition": partition,
            "direction": direction,
            "regime": regime,
            "score_bucket": _score_bucket(score),
            "volume_confirmation": volume_confirmation,
            "outcome": outcome,
            "trade_return_pct": _trade_return(row),
        })
    return output


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        key = (
            row["partition"], row["direction"], row["regime"],
            row["score_bucket"], row["volume_confirmation"],
        )
        groups.setdefault(key, []).append(row)

    result: list[dict[str, Any]] = []
    for key, group in sorted(groups.items()):
        outcomes = [r["outcome"] for r in group]
        returns = [r["trade_return_pct"] for r in group if r["trade_return_pct"] is not None]
        wins = sum(outcomes)
        losses = len(outcomes) - wins
        gross_profit = sum(r for r in returns if r > 0)
        gross_loss = abs(sum(r for r in returns if r < 0))
        expectancy = sum(returns) / len(returns) if returns else None
        profit_factor = None
        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        elif gross_profit > 0:
            profit_factor = math.inf
        result.append({
            "partition": key[0],
            "direction": key[1],
            "regime": key[2],
            "score_bucket": key[3],
            "volume_confirmation": key[4],
            "trades": len(group),
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round(100 * wins / len(group), 2),
            "expectancy_pct": round(expectancy, 4) if expectancy is not None else None,
            "profit_factor": round(profit_factor, 4) if profit_factor is not None and math.isfinite(profit_factor) else ("inf" if profit_factor == math.inf else None),
            "return_observations": len(returns),
        })
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = aggregate(analyse(args.json_path))
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
