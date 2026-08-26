"""Build a compact, comparable research report from journal records."""
from __future__ import annotations

from trade_journal import TradeRecord, summarize_journal


def compare_by_timeframe(records: list[TradeRecord]) -> dict[str, dict]:
    groups: dict[str, list[TradeRecord]] = {}
    for record in records:
        groups.setdefault(record.timeframe, []).append(record)
    return {timeframe: summarize_journal(items) for timeframe, items in sorted(groups.items())}


def rank_timeframes(records: list[TradeRecord]) -> list[tuple[str, dict]]:
    comparison = compare_by_timeframe(records)
    return sorted(
        comparison.items(),
        key=lambda item: (
            item[1].get("profit_factor") or 0.0,
            item[1].get("expectancy_pct", 0.0),
            -item[1].get("max_drawdown_pct", 0.0),
        ),
        reverse=True,
    )
