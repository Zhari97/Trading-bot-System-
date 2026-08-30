"""Research-only TP/SL sensitivity experiment.

Keeps production signal entries frozen and compares the current dynamic
ATR-based exit with fixed 5%/5% and 10%/10% risk-reward scenarios.
No production module is changed.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from historical_data import load_six_months
from historical_engine_runner import replay_timeframe
from historical_replay import evaluate_forward_result
from research_config import TRADE_PLAN
from research_metrics import summarize

SYMBOL = "BTCUSDT"
OUT = ROOT / "research" / "stop_sensitivity_results.json"
SCENARIOS = {
    "current_dynamic": {"tp_pct": None, "sl_pct": None},
    "fixed_5_5": {"tp_pct": 0.05, "sl_pct": 0.05},
    "fixed_10_10": {"tp_pct": 0.10, "sl_pct": 0.10},
}


def scenario_result(row: dict, candles: list[dict], scenario: dict) -> dict | None:
    if scenario["sl_pct"] is None:
        return {
            "outcome": row.get("outcome"),
            "bars": row.get("bars"),
            "exit": row.get("exit"),
            "tp": row.get("take_profit"),
            "sl": row.get("stop_loss"),
        }

    entry = float(row["entry"])
    direction = row["direction"]
    tp_pct = float(scenario["tp_pct"])
    sl_pct = float(scenario["sl_pct"])

    if direction == "LONG":
        stop = entry * (1 - sl_pct)
        take_profit = entry * (1 + tp_pct)
    else:
        stop = entry * (1 + sl_pct)
        take_profit = entry * (1 - tp_pct)

    future = candles[int(row["candle_index"]) + 1 : min(int(row["candle_index"]) + 1 + 500, len(candles))]
    return evaluate_forward_result(
        {
            "direction": direction,
            "entry": entry,
            "stop_loss": stop,
            "take_profit": take_profit,
        },
        future,
    )


def attach_metrics(rows: list[dict], scenario: str, allocation: float) -> list[dict]:
    out = []
    for row in rows:
        result = row["scenarios"][scenario]
        item = dict(row)
        item.pop("scenarios", None)
        item.update(result or {})
        out.append(item)
    return out


def summarize_group(rows: list[dict], allocation: float) -> dict:
    return summarize(rows, allocation)


def main() -> None:
    end = datetime.now(timezone.utc)
    datasets = load_six_months(SYMBOL, end)
    allocation = float(TRADE_PLAN["max_account_allocation_pct"])
    result = {
        "generated_at": end.isoformat(),
        "symbol": SYMBOL,
        "method": "Frozen production signal entries; only TP/SL exit levels change by scenario. Signal timing is not regenerated per scenario.",
        "allocation_pct": allocation,
        "scenarios": {
            "current_dynamic": "Production ATR-based stop (0.5%-2.0% bounds) with production 5% TP",
            "fixed_5_5": "Fixed 5% TP / 5% SL",
            "fixed_10_10": "Fixed 10% TP / 10% SL",
        },
        "timeframes": {},
    }

    for timeframe, candles in datasets.items():
        replay = replay_timeframe(candles, timeframe)
        base_rows = replay["records"]
        scenario_rows: list[dict] = []
        for row in base_rows:
            enriched = dict(row)
            enriched["scenarios"] = {}
            for scenario, config in SCENARIOS.items():
                enriched["scenarios"][scenario] = scenario_result(row, candles, config)
            scenario_rows.append(enriched)

        tf_out = {"signals_frozen": len(scenario_rows), "scenarios": {}}
        for scenario in SCENARIOS:
            all_rows = attach_metrics(scenario_rows, scenario, allocation)
            tf_out["scenarios"][scenario] = {
                "all": summarize_group(all_rows, allocation),
                "long": summarize_group([r for r in all_rows if r.get("direction") == "LONG"], allocation),
                "short": summarize_group([r for r in all_rows if r.get("direction") == "SHORT"], allocation),
                "trend_down": summarize_group([r for r in all_rows if r.get("regime") == "TREND_DOWN"], allocation),
                "short_trend_down": summarize_group(
                    [r for r in all_rows if r.get("direction") == "SHORT" and r.get("regime") == "TREND_DOWN"],
                    allocation,
                ),
            }

        transitions = {}
        base = attach_metrics(scenario_rows, "current_dynamic", allocation)
        for scenario in ("fixed_5_5", "fixed_10_10"):
            alt = attach_metrics(scenario_rows, scenario, allocation)
            transitions[scenario] = {
                "dynamic_sl_to_tp": sum(1 for a, b in zip(base, alt) if a.get("outcome") == "SL" and b.get("outcome") == "TP"),
                "dynamic_tp_to_sl": sum(1 for a, b in zip(base, alt) if a.get("outcome") == "TP" and b.get("outcome") == "SL"),
                "unchanged_tp": sum(1 for a, b in zip(base, alt) if a.get("outcome") == "TP" and b.get("outcome") == "TP"),
                "unchanged_sl": sum(1 for a, b in zip(base, alt) if a.get("outcome") == "SL" and b.get("outcome") == "SL"),
                "open_or_other": sum(1 for a, b in zip(base, alt) if a.get("outcome") not in ("TP", "SL") or b.get("outcome") not in ("TP", "SL")),
            }

        tf_out["transitions_vs_current"] = transitions
        tf_out["records"] = scenario_rows
        result["timeframes"][timeframe] = tf_out

    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"WROTE {OUT}")


if __name__ == "__main__":
    main()
