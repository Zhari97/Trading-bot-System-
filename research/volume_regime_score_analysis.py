"""Research-only analysis for the 1h volume/regime/direction/score relationship.

This module is deliberately outside the live signal path. It reads an existing
backtest_results.json and produces a deterministic diagnostic table for
TRAIN/VALIDATION/OOS. It does not alter signals, thresholds, sizing, or risk.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PARTITIONS = ("train", "validation", "oos")


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("records", "trades", "signals", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    raise ValueError("Could not find a record list in backtest_results.json")


def _partition(row: dict[str, Any]) -> str | None:
    value = str(row.get("partition", row.get("split", ""))).lower()
    if value in PARTITIONS:
        return value
    return None


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
    vr = row.get("volume_research")
    if not isinstance(vr, dict):
        return None
    value = vr.get("price_volume_confirmation")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def analyse(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = _records(payload)
    output: list[dict[str, Any]] = []

    for row in rows:
        partition = _partition(row)
        outcome = _outcome(row)
        direction = str(row.get("direction", "")).upper()
        regime = str(row.get("regime", "")).upper()
        score_value = row.get("research_score", row.get("score"))
        try:
            score = float(score_value)
        except (TypeError, ValueError):
            continue
        volume_confirmation = _volume_confirmation(row)
        if partition not in PARTITIONS or outcome is None or direction not in {"LONG", "SHORT"}:
            continue
        if volume_confirmation is None:
            continue
        output.append(
            {
                "partition": partition,
                "direction": direction,
                "regime": regime,
                "score_bucket": _score_bucket(score),
                "volume_confirmation": volume_confirmation,
                "outcome": outcome,
            }
        )
    return output


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[int]] = {}
    for row in rows:
        key = (
            row["partition"],
            row["direction"],
            row["regime"],
            row["score_bucket"],
            row["volume_confirmation"],
        )
        groups.setdefault(key, []).append(row["outcome"])

    result = []
    for key, outcomes in sorted(groups.items()):
        trades = len(outcomes)
        wins = sum(outcomes)
        result.append(
            {
                "partition": key[0],
                "direction": key[1],
                "regime": key[2],
                "score_bucket": key[3],
                "volume_confirmation": key[4],
                "trades": trades,
                "wins": wins,
                "win_rate_pct": round(100 * wins / trades, 2),
            }
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    rows = analyse(args.json_path)
    result = aggregate(rows)
    text = json.dumps(result, indent=2, sort_keys=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
