"""Executable historical replay using the production signal engine.

Research-only. One simulated position at a time per timeframe, with the
configured 5% account allocation used for portfolio metrics.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from historical_data import load_six_months
from historical_replay import evaluate_forward_result
from market_regime import classify as classify_regime
from research_config import HISTORICAL_DAYS, TRADE_PLAN
from research_metrics import summarize
from signal_analytics import analyze as analyze_signal_analytics
from signal_engine_replay_adapter_fast import analyze_context_at
from signal_engine import ContestoMercato

SYMBOL = "BTCUSDT"
OUT = Path("backtest_results.json")


def replay_timeframe(candles: list[dict], timeframe: str) -> dict:
    ctx = ContestoMercato(candles)
    records: list[dict] = []
    next_free_index = 60

    for i in range(60, len(candles) - 1):
        if i < next_free_index:
            continue
        analysis = analyze_context_at(ctx, i)
        if not analysis or analysis["classificazione"].get("livello") != "FORTE":
            continue
        plan = analysis.get("trade_plan")
        if not plan:
            continue

        future = candles[i + 1:min(i + 1 + 500, len(candles))]
        result = evaluate_forward_result({
            "direction": plan["direction"],
            "entry": plan["entry"],
            "stop_loss": plan["stop_loss"],
            "take_profit": plan["take_profit"],
        }, future)
        if not result:
            continue

        categories = analysis.get("categorie") or analysis.get("categories") or {}
        row = {
            "candle_index": i,
            "timestamp": candles[i].get("timestamp"),
            "timeframe": timeframe,
            "direction": plan["direction"],
            "entry": plan["entry"],
            "stop_loss": plan["stop_loss"],
            "take_profit": plan["take_profit"],
            "score": analysis["score"],
            "confluence": analysis["confluenza"],
            "trend": categories.get("trend"),
            "momentum": categories.get("momentum"),
            "setup": categories.get("setup"),
            "regime": classify_regime(candles[: i + 1]),
            "allocation_pct": float(TRADE_PLAN["max_account_allocation_pct"]),
        }
        row.update(result)
        records.append(row)

        # Do not count overlapping positions as independent full-size trades.
        next_free_index = i + max(1, int(result.get("bars", 1))) + 1

    train_end = int(len(candles) * 0.50)
    validation_end = int(len(candles) * (0.50 + 1 / 6))
    partitions = {
        "train": [r for r in records if r["candle_index"] < train_end],
        "validation": [r for r in records if train_end <= r["candle_index"] < validation_end],
        "oos": [r for r in records if r["candle_index"] >= validation_end],
    }
    allocation = float(TRADE_PLAN["max_account_allocation_pct"])
    return {
        "timeframe": timeframe,
        "candles": len(candles),
        "signals": len(records),
        "allocation_pct": allocation,
        "train": summarize(partitions["train"], allocation),
        "validation": summarize(partitions["validation"], allocation),
        "oos": summarize(partitions["oos"], allocation),
        "analytics": {
            "all": analyze_signal_analytics(records, min_trades=5),
            "oos": analyze_signal_analytics(partitions["oos"], min_trades=5),
        },
        "records": records,
    }


def main() -> None:
    end = datetime.now(timezone.utc)
    datasets = load_six_months(SYMBOL, end)
    results = {
        "generated_at": end.isoformat(),
        "symbol": SYMBOL,
        "history_days": HISTORICAL_DAYS,
        "tp_pct": float(TRADE_PLAN["take_profit_pct"]),
        "allocation_pct": float(TRADE_PLAN["max_account_allocation_pct"]),
        "timeframes": {},
    }
    for timeframe, candles in datasets.items():
        print(f"REPLAY {timeframe}: {len(candles)} candles")
        results["timeframes"][timeframe] = replay_timeframe(candles, timeframe)

    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"WROTE {OUT}")


if __name__ == "__main__":
    main()
