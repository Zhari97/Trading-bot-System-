"""Offline integration dry-run for the LIVE signal path.

Uses the real signal engine and guards, but never sends Telegram, orders, or
external dashboard writes.
"""
from __future__ import annotations

import datetime as dt
import signal_engine
from signal_quality_guard import analizza_coppia_con_guard
from signal_timing_guard import candle_is_closed, should_emit_signal
from trade_plan import costruisci_trade_plan


def _expected_closed_candle_open(now: dt.datetime, interval_minutes: int) -> dt.datetime:
    interval_seconds = interval_minutes * 60
    bucket = int(now.timestamp()) // interval_seconds
    return dt.datetime.fromtimestamp((bucket - 1) * interval_seconds, tz=dt.timezone.utc)


def run_pair(pair: str) -> dict:
    analysis = analizza_coppia_con_guard(pair)
    now = dt.datetime.now(dt.timezone.utc)
    ctx = analysis.get("ctx")
    candle_open = getattr(ctx, "candle_open_time", None) or _expected_closed_candle_open(now, signal_engine.INTERVAL_MIN)
    timing = candle_is_closed(candle_open, signal_engine.INTERVAL_MIN, now)
    if not timing.accepted:
        return {"pair": pair, "passed": False, "stage": "TIMING", "reason": timing.reason}
    c = analysis["classificazione"]
    dedup = should_emit_signal(pair, candle_open, c.get("direzione", "NEUTRO"), float(analysis["score"]), float(analysis["confluenza"]), None)
    if not dedup.accepted:
        return {"pair": pair, "passed": False, "stage": "DEDUP", "reason": dedup.reason}
    plan = costruisci_trade_plan(analysis)
    if c.get("livello") == "FORTE" and c.get("direzione") in ("LONG", "SHORT") and not isinstance(plan, dict):
        return {"pair": pair, "passed": False, "stage": "TRADE_PLAN", "reason": "FORTE_SIGNAL_WITHOUT_PLAN"}
    return {"pair": pair, "passed": True, "stage": "COMPLETE", "timing": timing.reason, "dedup": dedup.reason, "direction": c.get("direzione", "NEUTRO"), "score": float(analysis["score"]), "confluence": float(analysis["confluenza"]), "trade_plan": isinstance(plan, dict), "telegram_sent": False, "order_sent": False, "dashboard_written": False}


def main() -> int:
    results = [run_pair(pair) for pair in signal_engine.COPPIE_MONITORATE]
    for result in results:
        print(result)
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
