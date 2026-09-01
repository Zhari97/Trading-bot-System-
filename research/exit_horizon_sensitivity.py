"""Research-only exit horizon sensitivity analysis.

Keeps the production signal engine frozen and studies how quickly a +5% TP is
reached, plus how often a production ATR stop is followed by a later +5% TP.
No production strategy files are modified by this script.
"""
from __future__ import annotations

import json
from pathlib import Path

from historical_data import load_six_months
from historical_replay import evaluate_forward_result
from market_regime import classify as classify_regime
from research_config import HISTORICAL_DAYS, TRADE_PLAN
from signal_engine import ContestoMercato
from signal_engine_replay_adapter_fast import analyze_context_at

SYMBOL = "BTCUSDT"
HORIZONS = (10, 25, 50, 100, 200, 500)
OUT = Path("research/exit_horizon_results.json")


def level_hit(direction: str, candle: dict, level: float) -> bool:
    high = float(candle["high"])
    low = float(candle["low"])
    return low <= level if direction == "LONG" else high >= level


def tp_hit(direction: str, candle: dict, tp: float) -> bool:
    high = float(candle["high"])
    low = float(candle["low"])
    return high >= tp if direction == "LONG" else low <= tp


def analyze_timeframe(candles: list[dict], timeframe: str) -> dict:
    ctx = ContestoMercato(candles)
    next_free_index = 60
    rows: list[dict] = []

    for i in range(60, len(candles) - 1):
        if i < next_free_index:
            continue
        analysis = analyze_context_at(ctx, i)
        if not analysis or analysis["classificazione"].get("livello") != "FORTE":
            continue
        plan = analysis.get("trade_plan")
        if not plan:
            continue

        direction = plan["direction"]
        entry = float(plan["entry"])
        stop = float(plan["stop_loss"])
        tp = float(plan["take_profit"])
        future = candles[i + 1:min(i + 1 + 500, len(candles))]
        baseline = evaluate_forward_result({
            "direction": direction,
            "entry": entry,
            "stop_loss": stop,
            "take_profit": tp,
        }, future)
        if not baseline:
            continue

        first_stop_bar = None
        later_tp_after_stop_bar = None
        first_tp_bar = None
        for bars, candle in enumerate(future, start=1):
            if first_tp_bar is None and tp_hit(direction, candle, tp):
                first_tp_bar = bars
            if first_stop_bar is None and level_hit(direction, candle, stop):
                first_stop_bar = bars
                # Continue scanning after the stop to measure the counterfactual
                # recovery independently of the production exit.
                continue
            if first_stop_bar is not None and later_tp_after_stop_bar is None and bars > first_stop_bar and tp_hit(direction, candle, tp):
                later_tp_after_stop_bar = bars

        horizon_hits = {str(h): bool(first_tp_bar is not None and first_tp_bar <= h) for h in HORIZONS}
        row = {
            "candle_index": i,
            "timestamp": candles[i].get("timestamp"),
            "timeframe": timeframe,
            "direction": direction,
            "regime": classify_regime(candles[: i + 1]),
            "entry": entry,
            "stop_loss": stop,
            "take_profit": tp,
            "baseline_outcome": baseline["outcome"],
            "baseline_bars": baseline["bars"],
            "first_tp_bar": first_tp_bar,
            "first_stop_bar": first_stop_bar,
            "later_tp_after_stop_bar": later_tp_after_stop_bar,
            "tp_within_horizon": horizon_hits,
        }
        rows.append(row)
        next_free_index = i + max(1, int(baseline.get("bars", 1))) + 1

    def summarize(subset: list[dict]) -> dict:
        n = len(subset)
        stop_hits = [r for r in subset if r["first_stop_bar"] is not None]
        recoveries = [r for r in stop_hits if r["later_tp_after_stop_bar"] is not None]
        return {
            "signals": n,
            "baseline_tp": sum(r["baseline_outcome"] == "TP" for r in subset),
            "baseline_sl": sum(r["baseline_outcome"] == "SL" for r in subset),
            "baseline_open": sum(r["baseline_outcome"] == "OPEN" for r in subset),
            "stop_hits": len(stop_hits),
            "stop_then_later_tp": len(recoveries),
            "stop_then_later_tp_rate_pct": round(100 * len(recoveries) / len(stop_hits), 4) if stop_hits else 0.0,
            "tp_hit_rate_by_horizon_pct": {
                str(h): round(100 * sum(r["tp_within_horizon"][str(h)] for r in subset) / n, 4) if n else 0.0
                for h in HORIZONS
            },
            "median_first_tp_bar": sorted(r["first_tp_bar"] for r in subset if r["first_tp_bar"] is not None)[len([r for r in subset if r["first_tp_bar"] is not None]) // 2] if any(r["first_tp_bar"] is not None for r in subset) else None,
        }

    return {
        "timeframe": timeframe,
        "candles": len(candles),
        "summary": summarize(rows),
        "by_direction": {
            d: summarize([r for r in rows if r["direction"] == d])
            for d in ("LONG", "SHORT")
        },
        "by_regime": {
            regime: summarize([r for r in rows if r["regime"] == regime])
            for regime in sorted({r["regime"] for r in rows})
        },
        "records": rows,
    }


def main() -> None:
    from datetime import datetime, timezone

    end = datetime.now(timezone.utc)
    datasets = load_six_months(SYMBOL, end)
    results = {
        "generated_at": end.isoformat(),
        "symbol": SYMBOL,
        "history_days": HISTORICAL_DAYS,
        "tp_pct": float(TRADE_PLAN["take_profit_pct"]),
        "horizons_bars": list(HORIZONS),
        "timeframes": {},
    }
    for timeframe, candles in datasets.items():
        print(f"HORIZON {timeframe}: {len(candles)} candles")
        results["timeframes"][timeframe] = analyze_timeframe(candles, timeframe)
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"WROTE {OUT}")


if __name__ == "__main__":
    main()
