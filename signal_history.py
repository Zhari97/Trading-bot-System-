"""Persistenza leggera dei segnali per dataset live e futura analisi.

Scrive JSON Lines append-only. Non contiene credenziali e non esegue ordini.
Il formato e' pensato per essere esportato in seguito verso storage persistente.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

HISTORY_PATH = Path("data/signal_history.jsonl")


def _json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


def build_signal_record(pair: str, analysis: dict, trade_plan: dict | None = None) -> dict:
    c = analysis.get("classificazione", {})
    cats = analysis.get("categorie", {})
    ctx = analysis.get("ctx")
    i = getattr(ctx, "i", None)

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "pair": pair,
        "price": float(analysis.get("prezzo", 0)),
        "level": c.get("livello", "WATCH"),
        "direction": c.get("direzione", "NEUTRO"),
        "score": float(analysis.get("score", 50)),
        "confluence": float(analysis.get("confluenza", 0)),
        "trend": float(cats.get("trend", 50)),
        "momentum": float(cats.get("momentum", 50)),
        "setup": float(cats.get("setup", 50)),
        "trend_direction": c.get("trend_direzione", "NEUTRO"),
        "momentum_direction": c.get("momentum_direzione", "NEUTRO"),
        "setup_direction": c.get("setup_direzione", "NEUTRO"),
        "counter_trend": bool(c.get("controtrend", False)),
        "rsi": float(ctx.rsi14[i]) if ctx is not None and i is not None else None,
        "atr": float(ctx.atr14[i]) if ctx is not None and i is not None else None,
        "ema9": float(ctx.ema9[i]) if ctx is not None and i is not None else None,
        "ema21": float(ctx.ema21[i]) if ctx is not None and i is not None else None,
        "ema50": float(ctx.ema50[i]) if ctx is not None and i is not None else None,
        "trade_plan": _json_safe(trade_plan) if trade_plan else None,
    }


def append_signal(record: dict, path: Path = HISTORY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_json_safe(record), ensure_ascii=False, separators=(",", ":")) + "\n")
