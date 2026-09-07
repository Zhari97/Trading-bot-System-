"""Persistent research evidence registry.

Inspired by the evidence/provenance pattern in the reviewed trading projects.
This module is research-only: it never changes a signal or places an order.
Each evidence item is append-only JSONL with a hash-chain link so a later
report can verify that historical evidence was not silently rewritten.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path("data/research/evidence.jsonl")


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    strategy_id: str
    stage: str
    dataset: str
    timeframe: str
    source_commit: str
    artifact: str
    metrics: dict[str, Any]
    verdict: str
    created_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    previous_hash: str | None = None
    record_hash: str | None = None


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def append_evidence(record: EvidenceRecord, path: Path = DEFAULT_PATH) -> EvidenceRecord:
    """Append evidence and return the record with its chain hash populated."""
    if not record.evidence_id or not record.strategy_id:
        raise ValueError("evidence_id and strategy_id are required")
    if not record.verdict:
        raise ValueError("verdict is required")

    existing = _read_records(path)
    previous_hash = existing[-1].get("record_hash") if existing else None
    payload = asdict(record)
    payload["previous_hash"] = previous_hash
    payload["record_hash"] = None
    payload["record_hash"] = _hash_payload(payload)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str) + "\n")

    return EvidenceRecord(**payload)


def verify_chain(path: Path = DEFAULT_PATH) -> dict[str, Any]:
    """Verify hashes and previous-hash links without modifying the registry."""
    records = _read_records(path)
    previous_hash: str | None = None
    errors: list[str] = []
    for index, record in enumerate(records, start=1):
        expected_prev = previous_hash
        if record.get("previous_hash") != expected_prev:
            errors.append(f"record {index}: previous_hash mismatch")
        supplied_hash = record.get("record_hash")
        check = dict(record)
        check["record_hash"] = None
        if supplied_hash != _hash_payload(check):
            errors.append(f"record {index}: record_hash mismatch")
        previous_hash = supplied_hash
    return {"valid": not errors, "records": len(records), "errors": errors}


def load_evidence(path: Path = DEFAULT_PATH) -> list[dict[str, Any]]:
    """Load the registry for reporting; no mutation is performed."""
    return _read_records(path)
