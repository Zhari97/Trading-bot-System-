"""Append-only, hash-chained audit ledger.

Used for operational/research events such as signal emission, Telegram send,
trade-plan creation and later outcome reconciliation. It is deliberately
separate from the trading decision logic.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_AUDIT_PATH = Path("data/audit/audit.jsonl")


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _load(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def append_event(
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    path: Path = DEFAULT_AUDIT_PATH,
) -> dict[str, Any]:
    """Append one immutable audit event and return the stored event."""
    if not event_type:
        raise ValueError("event_type is required")
    rows = _load(path)
    previous_hash = rows[-1].get("record_hash") if rows else None
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "payload": payload or {},
        "previous_hash": previous_hash,
        "record_hash": None,
    }
    event["record_hash"] = _digest(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str) + "\n")
    return event


def verify(path: Path = DEFAULT_AUDIT_PATH) -> dict[str, Any]:
    """Verify event hashes and chain links without modifying the ledger."""
    rows = _load(path)
    errors: list[str] = []
    previous_hash: str | None = None
    for index, row in enumerate(rows, start=1):
        if row.get("previous_hash") != previous_hash:
            errors.append(f"event {index}: previous_hash mismatch")
        supplied = row.get("record_hash")
        check = dict(row)
        check["record_hash"] = None
        if supplied != _digest(check):
            errors.append(f"event {index}: record_hash mismatch")
        previous_hash = supplied
    return {"valid": not errors, "events": len(rows), "errors": errors}
