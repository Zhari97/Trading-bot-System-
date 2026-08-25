"""Persistenza minimale e sicura dello stato osservabile della dashboard."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

MAX_HISTORY = 200
STATE_FILE = Path(os.environ.get("DASHBOARD_STATE_FILE", "data/dashboard_state.json"))


def _empty_state():
    return {"updated_at": None, "markets": {}, "history": [], "telegram": {"configured": False}}


def read_state():
    try:
        with STATE_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else _empty_state()
    except (OSError, json.JSONDecodeError):
        return _empty_state()


def _write_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, separators=(",", ":"))
    temporary.replace(STATE_FILE)


def save_analysis(analysis, guard_status="PASS", guard_reason="", telegram_status="NOT_SENT"):
    """Registra esclusivamente dati già calcolati dal motore, mai segreti."""
    classification = analysis["classificazione"]
    now = datetime.now(timezone.utc).isoformat()
    record = {"timestamp": now, "pair": analysis["pair"], "price": round(float(analysis["prezzo"]), 8), "rsi": round(float(analysis["rsi"]), 2), "score": analysis["score"], "confluence": analysis["confluenza"], "direction": classification.get("direzione", "NEUTRO"), "classification": classification.get("livello", "WATCH"), "reason": classification.get("motivo", ""), "counter_trend": bool(classification.get("controtrend")), "guard_rail": {"status": guard_status, "reason": guard_reason}, "telegram": telegram_status, "categories": analysis["categorie"], "weights": {"long": analysis["peso_long"], "short": analysis["peso_short"]}, "strategies": [{key: result[key] for key in ("nome", "voto", "motivo", "attivo")} for result in analysis["risultati"]]}
    state = read_state()
    state["updated_at"] = now
    state.setdefault("markets", {})[record["pair"]] = record
    state["history"] = (state.get("history", []) + [record])[-MAX_HISTORY:]
    state["telegram"] = {"configured": bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")), "last_alert": record if telegram_status == "SENT" else state.get("telegram", {}).get("last_alert")}
    _write_state(state)
    return record
