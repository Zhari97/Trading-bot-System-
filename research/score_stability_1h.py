"""Research-only 1h score stability analysis.

Consumes the deterministic six-month replay output and measures score
separation across chronological partitions, regimes and walk-forward windows.
No threshold is selected and no production logic is changed.
"""
from __future__ import annotations

import json
from pathlib import Path

from research_score_analysis import analyze_records

INPUT = Path("backtest_results.json")
OUTPUT = Path("research/score_stability_1h_results.json")


def main() -> None:
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    timeframe = payload.get("timeframes", {}).get("1h")
    if not timeframe:
        raise SystemExit("Missing 1h timeframe in backtest_results.json")

    records = timeframe.get("records", [])
    analysis = analyze_records(records)

    result = {
        "generated_at": payload.get("generated_at"),
        "symbol": payload.get("symbol", "BTCUSDT"),
        "history_days": payload.get("history_days", 183),
        "timeframe": "1h",
        "method": {
            "threshold_optimization": False,
            "oos_optimization": False,
            "score_buckets": [[0, 40], [40, 60], [60, 80], [80, 100]],
            "chronological_windows": 4,
        },
        "analysis": analysis,
    }
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        "SCORE STABILITY 1h: "
        f"status={analysis['stability']['research_status']} "
        f"oos_lift={analysis['stability']['oos_high_minus_low_win_rate_pp']}pp"
    )
    print(f"WROTE {OUTPUT}")


if __name__ == "__main__":
    main()
