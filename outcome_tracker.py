"""Build outcome measurements from recent live-signal journal artifacts.

Instrumentation/research only: this module does not change signal generation,
alert gating, execution, thresholds, or trade-plan construction.
"""

from __future__ import annotations

import io
import json
import os
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

REPO = os.environ.get("GITHUB_REPOSITORY", "").strip()
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
INTERVAL_MIN = int(os.environ.get("INTERVAL_MIN", "15"))
HORIZONS_H = (1, 4, 12, 24)
MAX_ARTIFACTS = int(os.environ.get("OUTCOME_MAX_ARTIFACTS", "100"))
OUT_DIR = Path("data/outcomes")
OUT_JSONL = OUT_DIR / "signal_outcomes.jsonl"
OUT_SUMMARY = OUT_DIR / "summary.json"

SESSION = requests.Session()
SESSION.headers.update({"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"})


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _github_get(url: str, **params):
    r = SESSION.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def collect_signal_records() -> list[dict]:
    if not REPO or not TOKEN:
        raise RuntimeError("GITHUB_REPOSITORY/GITHUB_TOKEN required")

    artifacts = _github_get(
        f"https://api.github.com/repos/{REPO}/actions/artifacts",
        per_page=100,
    ).get("artifacts", [])

    records = {}
    for artifact in artifacts:
        name = str(artifact.get("name", ""))
        if not name.startswith("live-signal-journal-") or artifact.get("expired"):
            continue
        if len(records) >= MAX_ARTIFACTS * 10:
            break
        archive = SESSION.get(artifact["archive_download_url"], timeout=30)
        archive.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(archive.content)) as zf:
            members = [n for n in zf.namelist() if n.endswith("signal_history.jsonl")]
            if not members:
                continue
            for line in zf.read(members[0]).decode("utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                key = (str(row.get("pair", "")).upper(), str(row.get("timestamp_utc", "")))
                if key[0] and key[1]:
                    records[key] = row
    return sorted(records.values(), key=lambda r: r.get("timestamp_utc", ""))


def fetch_ohlc(pair: str, interval_min: int) -> list[dict]:
    r = SESSION.get(
        "https://api.kraken.com/0/public/OHLC",
        params={"pair": pair, "interval": interval_min},
        timeout=20,
    )
    r.raise_for_status()
    payload = r.json()
    if payload.get("error"):
        raise RuntimeError(f"Kraken error for {pair}: {payload['error']}")
    result = payload["result"]
    key = next(k for k in result if k != "last")
    return [
        {
            "ts": int(c[0]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
        }
        for c in result[key]
    ]


def directional_return(direction: str, entry: float, close: float) -> float | None:
    if not entry or not close or direction not in ("LONG", "SHORT"):
        return None
    raw = (close - entry) / entry
    return raw if direction == "LONG" else -raw


def evaluate_signal(signal: dict, candles: list[dict], now: datetime) -> dict:
    ts = _parse_ts(signal["timestamp_utc"])
    entry = float(signal.get("price", 0) or 0)
    direction = str(signal.get("direction", "NEUTRO")).upper()
    future = [c for c in candles if datetime.fromtimestamp(c["ts"], tz=timezone.utc) >= ts]
    result = dict(signal)
    result["evaluated_at_utc"] = now.isoformat()
    result["outcomes"] = {}

    for hours in HORIZONS_H:
        target = ts + timedelta(hours=hours)
        window = [c for c in future if datetime.fromtimestamp(c["ts"], tz=timezone.utc) <= target]
        key = f"{hours}h"
        if not window:
            result["outcomes"][key] = {"status": "PENDING"}
            continue

        close = window[-1]["close"]
        returns = directional_return(direction, entry, close)
        favorable = None
        adverse = None
        if direction == "LONG":
            favorable = max((c["high"] - entry) / entry for c in window) if entry else None
            adverse = min((c["low"] - entry) / entry for c in window) if entry else None
        elif direction == "SHORT":
            favorable = max((entry - c["low"]) / entry for c in window) if entry else None
            adverse = min((entry - c["high"]) / entry for c in window) if entry else None

        result["outcomes"][key] = {
            "status": "READY" if datetime.fromtimestamp(window[-1]["ts"], tz=timezone.utc) >= target else "PENDING",
            "close": close,
            "directional_return_pct": returns * 100 if returns is not None else None,
            "mfe_pct": favorable * 100 if favorable is not None else None,
            "mae_pct": adverse * 100 if adverse is not None else None,
            "observed_until_utc": datetime.fromtimestamp(window[-1]["ts"], tz=timezone.utc).isoformat(),
        }

    plan = signal.get("trade_plan") or {}
    if plan and direction in ("LONG", "SHORT"):
        tp = float(plan.get("take_profit", 0) or 0)
        sl = float(plan.get("stop_loss", 0) or 0)
        if tp and sl:
            tp_hit = any((c["high"] >= tp if direction == "LONG" else c["low"] <= tp) for c in future)
            sl_hit = any((c["low"] <= sl if direction == "LONG" else c["high"] >= sl) for c in future)
            result["trade_plan_outcome"] = {"tp_hit": tp_hit, "sl_hit": sl_hit}
    return result


def build_summary(rows: list[dict]) -> dict:
    ready = [r for r in rows if r.get("outcomes")]
    summary = {"signals": len(rows), "ready_by_horizon": {}, "direction": {}, "level": {}}
    for h in HORIZONS_H:
        values = [
            r["outcomes"].get(f"{h}h", {}).get("directional_return_pct")
            for r in ready
            if r["outcomes"].get(f"{h}h", {}).get("status") == "READY"
        ]
        summary["ready_by_horizon"][f"{h}h"] = {
            "count": len(values),
            "mean_return_pct": sum(values) / len(values) if values else None,
            "positive_count": sum(v > 0 for v in values),
            "negative_count": sum(v < 0 for v in values),
        }
    for field in ("direction", "level"):
        groups = {}
        for r in rows:
            value = str(r.get(field, "UNKNOWN"))
            groups.setdefault(value, 0)
            groups[value] += 1
        summary[field] = groups
    return summary


def main() -> None:
    now = datetime.now(timezone.utc)
    records = collect_signal_records()
    cache = {}
    rows = []
    for signal in records:
        pair = str(signal.get("pair", "")).upper()
        if not pair:
            continue
        try:
            if pair not in cache:
                cache[pair] = fetch_ohlc(pair, INTERVAL_MIN)
            rows.append(evaluate_signal(signal, cache[pair], now))
        except Exception as exc:
            row = dict(signal)
            row["outcomes"] = {"error": str(exc)}
            rows.append(row)
        time.sleep(0.05)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_JSONL.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    OUT_SUMMARY.write_text(json.dumps(build_summary(rows), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Outcome tracker: {len(rows)} unique signals; artifacts scanned from recent retention window.")


if __name__ == "__main__":
    main()
