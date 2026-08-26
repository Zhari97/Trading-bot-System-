"""Offline integration dry-run for the LIVE signal path.

Uses the real signal engine and guards, but never sends Telegram, orders, or
external dashboard writes. It validates the complete decision chain.
"""
from __future__ import annotations

import datetime as dt
import signal_engine
from signal_quality_guard import analizza_coppia_con_guard
from signal_timing_guard import candle_is_closed, should_emit_signal
from trade_plan import costruisci_trade_plan


def run_pair(pair: str) -> dict:
    analysis = analizza_coppia_con_guard(pair)
    ctx = analysis.get("ctx")
    candle_open = getattr(ctx, "candle_open_time", None) or getattr(ctx, "open_time", None)
    if candle_open is None:
        return {"pair": pair, "passed": False, "stage": "TIMING", "reason": "MISSING_CANDLE_OPEN_TIME"}
    timing = candle_is_closed(candle_open, signal_engine.INTERVAL_MIN, dt.datetime.now(dt.timezone.utc))
    if not timing.accepted:
        return {"pair": pair, "passed": False, "stage": "TIMING", "reason": timing.reason}
    c = analysis["classificazione"]
    decision = should_emit_signal(pair, candle_open, c.get("direzione", "NEUTRO"), float(analysis["score"]), float(analysis["confluenza"]), None)
    if not decision.accepted:
        return {"pair": pair, "passed": False, "stage": "DEDUP", "reason": decision.reason}
    plan = costruisci_trade_plan(analysis)
    return {
        "pair": pair,
        "passed": isinstance(plan, dict),
        "stage": "COMPLETE",
        "timing": timing.reason,
        "dedup": decision.reason,
        "direction": c.get("direzione", "NEUTRO"),
        "score": float(analysis["score"]),
        "confluence": float(analysis["confluenza"]),
        "trade_plan": isinstance(plan, dict),
        "telegram_sent": False,
        "order_sent": False,
        "dashboard_written": False,
    }


def main() -> int:
    results = [run_pair(pair) for pair in signal_engine.COPPIE_MONITORATE]
    for result in results:
        print(result)
    return 0 if all(r.get("passed") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
