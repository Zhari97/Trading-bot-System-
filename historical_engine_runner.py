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

# Mirror of the production strategy weights. These metrics are research-only:
# they expose how much weighted evidence actually supports a direction instead
# of treating "no opposition" as 100% confluence.
STRATEGY_WEIGHTS = {
    "EMA9/21 + RSI + conferma": 0.45,
    "MACD crossover": 0.20,
    "Bollinger Bands": 0.15,
    "Ichimoku semplificato": 0.15,
    "Fibonacci retracement": 0.10,
    "Price Action": 0.10,
    "ATR volatilità": 0.05,
}
TOTAL_STRATEGY_WEIGHT = sum(STRATEGY_WEIGHTS.values())


def weighted_evidence(risultati: list[dict]) -> dict:
    """Return continuous research metrics for directional evidence.

    The legacy confluence metric measures agreement only among non-neutral
    votes, so a single directional vote can become 100%. These metrics use
    the full strategy weight budget and therefore distinguish strong evidence
    from sparse evidence.
    """
    long_weight = 0.0
    short_weight = 0.0
    for result in risultati:
        weight = STRATEGY_WEIGHTS.get(result.get("nome"), 0.0)
        if result.get("voto") == "LONG":
            long_weight += weight
        elif result.get("voto") == "SHORT":
            short_weight += weight

    supported_weight = long_weight + short_weight
    neutral_weight = max(0.0, TOTAL_STRATEGY_WEIGHT - supported_weight)
    dominant_weight = max(long_weight, short_weight)
    direction = (
        "LONG" if long_weight > short_weight
        else "SHORT" if short_weight > long_weight
        else "NEUTRO"
    )

    support_coverage_pct = supported_weight / TOTAL_STRATEGY_WEIGHT * 100.0
    neutral_weight_pct = neutral_weight / TOTAL_STRATEGY_WEIGHT * 100.0
    weighted_confidence_pct = dominant_weight / TOTAL_STRATEGY_WEIGHT * 100.0
    if supported_weight > 0:
        directional_agreement_pct = dominant_weight / supported_weight * 100.0
    else:
        directional_agreement_pct = 0.0

    evidence_score = 50.0 + (
        (long_weight - short_weight) / TOTAL_STRATEGY_WEIGHT
    ) * 50.0

    return {
        "evidence_score": round(evidence_score, 4),
        "weighted_confidence_pct": round(weighted_confidence_pct, 4),
        "support_coverage_pct": round(support_coverage_pct, 4),
        "neutral_weight_pct": round(neutral_weight_pct, 4),
        "directional_agreement_pct": round(directional_agreement_pct, 4),
        "weighted_long_pct": round(long_weight / TOTAL_STRATEGY_WEIGHT * 100.0, 4),
        "weighted_short_pct": round(short_weight / TOTAL_STRATEGY_WEIGHT * 100.0, 4),
        "evidence_direction": direction,
    }


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
        evidence = weighted_evidence(analysis.get("risultati", []))
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
            **evidence,
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
