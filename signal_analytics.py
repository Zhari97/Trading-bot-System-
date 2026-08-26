"""Offline signal analytics: summarize outcomes by signal attributes."""
from __future__ import annotations

from collections import defaultdict


def _bucket(value: float, edges: tuple[float, ...]) -> str:
    for upper in edges:
        if value < upper:
            return f"<{upper:g}"
    return f">={edges[-1]:g}"


def enrich(record: dict) -> dict:
    row = dict(record)
    categories = row.get("categories") or row.get("categorie") or {}
    row["trend"] = categories.get("trend", row.get("trend"))
    row["momentum"] = categories.get("momentum", row.get("momentum"))
    row["setup"] = categories.get("setup", row.get("setup"))
    row["regime"] = row.get("regime", "UNKNOWN")
    row["score_bucket"] = _bucket(float(row.get("score", 0) or 0), (40, 50, 60, 70, 80))
    row["confluence_bucket"] = _bucket(float(row.get("confluence", 0) or 0), (40, 60, 80, 90))
    return row


def group_summary(records: list[dict], key: str, min_trades: int = 5) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for raw in records:
        row = enrich(raw)
        outcome = row.get("outcome")
        if outcome not in ("TP", "SL"):
            continue
        groups[str(row.get(key, "UNKNOWN"))].append(row)

    output: list[dict] = []
    for group, rows in sorted(groups.items()):
        if len(rows) < min_trades:
            continue
        wins = sum(r.get("outcome") == "TP" for r in rows)
        output.append({
            "group": group,
            "trades": len(rows),
            "wins": wins,
            "losses": len(rows) - wins,
            "win_rate_pct": wins / len(rows) * 100.0,
            "avg_score": sum(float(r.get("score", 0) or 0) for r in rows) / len(rows),
            "avg_confluence": sum(float(r.get("confluence", 0) or 0) for r in rows) / len(rows),
        })
    return output


def analyze(records: list[dict], min_trades: int = 5) -> dict:
    enriched = [enrich(r) for r in records]
    keys = ("timeframe", "direction", "regime", "score_bucket", "confluence_bucket", "trend", "momentum", "setup")
    return {key: group_summary(enriched, key, min_trades) for key in keys}
