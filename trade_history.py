"""Persistenza dei segnali Telegram realmente inviati.

Il registro e' separato dalla signal history generale: contiene solo i piani
che sono stati effettivamente inviati a Telegram, con timestamp UTC e livelli
entry/TP/SL, per consentire l'audit storico dei segnali.

Ogni record contiene inoltre un hash SHA-256 collegato al record precedente.
Questo non rende il file immutabile, ma rende rilevabili modifiche, riordini o
cancellazioni quando la catena viene verificata.
"""

from __future__ import annotations

import hashlib
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


def _canonical(record: dict) -> bytes:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _record_hash(record: dict) -> str:
    payload = dict(record)
    payload["record_hash"] = None
    return hashlib.sha256(_canonical(payload)).hexdigest()


def verify_trade_history(path: Path = TRADE_HISTORY_PATH) -> dict:
    """Verify the hash chain without changing the trade history."""
    if not path.exists():
        return {"valid": True, "records": 0, "errors": []}
    errors: list[str] = []
    previous_hash: str | None = None
    records = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                errors.append(f"record {records + 1}: invalid JSON")
                continue
            records += 1
            if not isinstance(record, dict):
                errors.append(f"record {records}: not an object")
                continue
            if record.get("previous_hash") != previous_hash:
                errors.append(f"record {records}: previous_hash mismatch")
            if record.get("record_hash") != _record_hash(record):
                errors.append(f"record {records}: record_hash mismatch")
            previous_hash = record.get("record_hash")
    return {"valid": not errors, "records": records, "errors": errors}


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

    # Retention deliberately rebuilds the chain because deleting the oldest
    # records would otherwise make the remaining file fail its own audit.
    previous_hash: str | None = None
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in kept:
            record = dict(record)
            record["previous_hash"] = previous_hash
            record["record_hash"] = None
            record["record_hash"] = _record_hash(record)
            fh.write(json.dumps(_safe_record(record), ensure_ascii=False, separators=(",", ":")) + "\n")
            previous_hash = record["record_hash"]


def append_sent_trade(record: dict, path: Path = TRADE_HISTORY_PATH) -> None:
    """Append one successfully sent Telegram signal, then enforce retention."""
    if not isinstance(record, dict):
        return

    payload = dict(record)
    payload["telegram_status"] = "SENT"
    payload["telegram_sent_at_utc"] = datetime.now(timezone.utc).isoformat()

    previous_hash: str | None = None
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    previous_hash = json.loads(line).get("record_hash")
                except json.JSONDecodeError:
                    continue

    payload["previous_hash"] = previous_hash
    payload["record_hash"] = None
    payload["record_hash"] = _record_hash(payload)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_safe_record(payload), ensure_ascii=False, separators=(",", ":")) + "\n")

    prune_trade_history(path)
