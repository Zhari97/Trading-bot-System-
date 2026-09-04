"""Persistenza dei segnali Telegram realmente inviati.

Il registro e' separato dalla signal history generale: contiene solo i piani
che sono stati effettivamente inviati a Telegram, con timestamp UTC e livelli
entry/TP/SL, per consentire l'audit storico dei segnali.

La retention locale e' di almeno 7 giorni: ad ogni scrittura vengono rimossi
solo i record piu' vecchi di 7 giorni. La persistenza tra run GitHub Actions e'
garantita dall'upload dell'artefatto nel workflow, con retention >= 7 giorni.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

TRADE_HISTORY_PATH = Path("data/trade_history/trades.jsonl")
RETENTION_DAYS = 7


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _safe_record(record: dict) -> dict:
    return json.loads(json.dumps(record, ensure_ascii=False, default=str))


def prune_trade_history(path: Path = TRADE_HISTORY_PATH, now: datetime | None = None) -> None:
    """Keep only records from the last RETENTION_DAYS days."""
    if not path.exists():
        return

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RETENTION_DAYS)
    kept: list[dict] = []

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            timestamp = _parse_timestamp(record.get("timestamp_utc"))
            if timestamp is None or timestamp >= cutoff:
                kept.append(record)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in kept:
            fh.write(json.dumps(_safe_record(record), ensure_ascii=False, separators=(",", ":")) + "\n")


def append_sent_trade(record: dict, path: Path = TRADE_HISTORY_PATH) -> None:
    """Append one successfully sent Telegram signal, then enforce retention."""
    if not isinstance(record, dict):
        return

    payload = dict(record)
    payload["telegram_status"] = "SENT"
    payload["telegram_sent_at_utc"] = datetime.now(timezone.utc).isoformat()

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_safe_record(payload), ensure_ascii=False, separators=(",", ":")) + "\n")

    prune_trade_history(path)
