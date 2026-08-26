"""Executable first-pass historical replay using the production signal engine.

Research-only. Builds indicators once per timeframe, then moves the engine's
candle index forward so the six-month replay is computationally tractable.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from historical_data import load_six_months
from historical_replay import evaluate_forward_result
from research_metrics import summarize
from signal_engine_replay_adapter import analyze_context_at
from signal_engine import ContestoMercato

SYMBOL = "BTCUSDT"
OUT = Path("backtest_results.json")


def replay_timeframe(candles: list[dict], timeframe: str) -> dict:
    ctx = ContestoMercato(candles)
    records: list[dict] = []
    # Keep enough warm-up history and reserve future candles for outcome.
    for i in range(60, len(candles) - 1):
        analysis = analyze_context_at(ctx, i)
        if not analysis:
            continue
        classification = analysis["classificazione"]
        if classification.get("livello") != "FORTE":
            continue
        plan = analysis.get("trade_plan")
        if not plan:
            continue
        future = candles[i + 1:min(i + 1 + 500, len(candles))]
        result = evaluate_forward_result({
            "direction": plan["direction"],
            "entry": plan["entry"],
            "stop_loss": plan["stop_loss"],
        }, future)
        if result:
            row = {
                "timestamp": candles[i].get("timestamp"),
                "timeframe": timeframe,
                "direction": plan["direction"],
                "entry": plan["entry"],
                "stop_loss": plan["stop_loss"],
                "take_profit": plan["take_profit"],
                "score": analysis["score"],
                "confluence": analysis["confluenza"],
            }
            row.update(result)
            records.append(row)

    split = int(len(records) * 0.5)
    val = int(len(records) * (0.5 + 1 / 6))
    partitions = {
        "train": records[:split],
        "validation": records[split:val],
        "oos": records[val:],
    }
    return {
        "timeframe": timeframe,
        "candles": len(candles),
        "signals": len(records),
        "train": summarize(partitions["train"]),
        "validation": summarize(partitions["validation"]),
        "oos": summarize(partitions["oos"]),
        "records": records,
    }


def main() -> None:
    end = datetime.now(timezone.utc)
    datasets = load_six_months(SYMBOL, end)
    results = {
        "generated_at": end.isoformat(),
        "symbol": SYMBOL,
        "history_days": 183,
        "tp_pct": 5.0,
        "timeframes": {},
    }
    for timeframe, candles in datasets.items():
        print(f"REPLAY {timeframe}: {len(candles)} candles")
        results["timeframes"][timeframe] = replay_timeframe(candles, timeframe)

    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"WROTE {OUT}")


if __name__ == "__main__":
    main()
