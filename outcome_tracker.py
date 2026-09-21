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
    interval = timedelta(minutes=INTERVAL_MIN)
    future = [
        c for c in candles
        if datetime.fromtimestamp(c["ts"], tz=timezone.utc) >= ts
        and datetime.fromtimestamp(c["ts"], tz=timezone.utc) + interval <= now
    ]
    result = dict(signal)
    result["evaluated_at_utc"] = now.isoformat()
    result["outcomes"] = {}

    for hours in HORIZONS_H:
        target = ts + timedelta(hours=hours)
        horizon_candle = next(
            (
                c for c in future
                if datetime.fromtimestamp(c["ts"], tz=timezone.utc) + interval >= target
            ),
            None,
        )
        key = f"{hours}h"
        if horizon_candle is None:
            result["outcomes"][key] = {"status": "PENDING"}
            continue

        window = [c for c in future if c["ts"] <= horizon_candle["ts"]]
        close = horizon_candle["close"]
        returns = directional_return(direction, entry, close)
        favorable = None
        adverse = None
        if direction == "LONG":
            favorable = max((c["high"] - entry) / entry for c in window) if entry else None
            adverse = min((c["low"] - entry) / entry for c in window) if entry else None
        elif direction == "SHORT":
            favorable = max((entry - c["low"]) / entry for c in window) if entry else None
            adverse = min((entry - c["high"]) / entry for c in window) if entry else None

        candle_close_ts = datetime.fromtimestamp(horizon_candle["ts"], tz=timezone.utc) + interval
        result["outcomes"][key] = {
            "status": "READY" if candle_close_ts >= target else "PENDING",
            "close": close,
            "directional_return_pct": returns * 100 if returns is not None else None,
            "mfe_pct": favorable * 100 if favorable is not None else None,
            "mae_pct": adverse * 100 if adverse is not None else None,
            "observed_until_utc": candle_close_ts.isoformat(),
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


def _score_bucket(value) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if score < 20:
        return "0-19"
    if score < 40:
        return "20-39"
    if score < 60:
        return "40-59"
    if score < 80:
        return "60-79"
    return "80-100"


def _group_stats(rows: list[dict], field: str) -> dict:
    groups = {}
    for row in rows:
        value = str(row.get(field, "UNKNOWN"))
        groups.setdefault(
            value,
            {
                "signals": 0,
                "ready_1h": 0,
                "positive_1h": 0,
                "_returns": [],
                "_mfe": [],
                "_mae": [],
            },
        )
        groups[value]["signals"] += 1
        outcome = row.get("outcomes", {}).get("1h", {})
        if outcome.get("status") == "READY" and outcome.get("directional_return_pct") is not None:
            ret = float(outcome["directional_return_pct"])
            groups[value]["ready_1h"] += 1
            groups[value]["positive_1h"] += int(ret > 0)
            groups[value]["_returns"].append(ret)
            if outcome.get("mfe_pct") is not None:
                groups[value]["_mfe"].append(float(outcome["mfe_pct"]))
            if outcome.get("mae_pct") is not None:
                groups[value]["_mae"].append(float(outcome["mae_pct"]))

    for stats in groups.values():
        values = stats.pop("_returns")
        mfe = stats.pop("_mfe")
        mae = stats.pop("_mae")
        stats["mean_return_1h_pct"] = sum(values) / len(values) if values else None
        stats["mean_mfe_1h_pct"] = sum(mfe) / len(mfe) if mfe else None
        stats["mean_mae_1h_pct"] = sum(mae) / len(mae) if mae else None
        stats["positive_rate_1h_pct"] = (
            100 * stats["positive_1h"] / stats["ready_1h"] if stats["ready_1h"] else None
        )
    return groups


def build_summary(rows: list[dict]) -> dict:
    ready = [r for r in rows if r.get("outcomes")]
    summary = {
        "signals": len(rows),
        "outcome_errors": sum(1 for r in rows if r.get("outcomes", {}).get("error")),
        "latest_signal_timestamp_utc": max(
            (str(r.get("timestamp_utc")) for r in rows if r.get("timestamp_utc")),
            default=None,
        ),
        "latest_evaluated_at_utc": max(
            (str(r.get("evaluated_at_utc")) for r in rows if r.get("evaluated_at_utc")),
            default=None,
        ),
        "latest_observed_until_utc": max(
            (
                str(outcome.get("observed_until_utc"))
                for row in rows
                for outcome in (row.get("outcomes") or {}).values()
                if isinstance(outcome, dict) and outcome.get("observed_until_utc")
            ),
            default=None,
        ),
        "ready_by_horizon": {},
    }
    for h in HORIZONS_H:
        horizon_key = f"{h}h"
        horizon_outcomes = [
            r.get("outcomes", {}).get(horizon_key, {})
            for r in ready
            if r.get("outcomes", {}).get(horizon_key)
        ]
        values = [
            o.get("directional_return_pct")
            for o in horizon_outcomes
            if o.get("status") == "READY" and o.get("directional_return_pct") is not None
        ]
        horizon_rows = [
            o for o in horizon_outcomes
            if o.get("status") == "READY"
        ]
        pending_count = sum(o.get("status") == "PENDING" for o in horizon_outcomes)
        mfe_values = [
            float(o["mfe_pct"]) for o in horizon_rows if o.get("mfe_pct") is not None
        ]
        mae_values = [
            float(o["mae_pct"]) for o in horizon_rows if o.get("mae_pct") is not None
        ]
        summary["ready_by_horizon"][f"{h}h"] = {
            "count": len(values),
            "pending_count": pending_count,
            "coverage_pct": 100 * len(values) / len(rows) if rows else None,
            "mean_return_pct": sum(values) / len(values) if values else None,
            "positive_count": sum(v > 0 for v in values),
            "negative_count": sum(v < 0 for v in values),
            "mean_mfe_pct": sum(mfe_values) / len(mfe_values) if mfe_values else None,
            "mean_mae_pct": sum(mae_values) / len(mae_values) if mae_values else None,
        }

    summary["by_direction"] = _group_stats(rows, "direction")
    summary["by_level"] = _group_stats(rows, "level")
    summary["by_pair"] = _group_stats(rows, "pair")

    score_rows = []
    for row in rows:
        item = dict(row)
        item["score_bucket"] = _score_bucket(row.get("score"))
        score_rows.append(item)
    summary["by_score_bucket"] = _group_stats(score_rows, "score_bucket")
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
