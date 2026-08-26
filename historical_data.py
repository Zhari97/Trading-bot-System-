"""Historical OHLC loader for Binance public data archives.

GitHub-hosted runners can receive HTTP 451 from api.binance.com. The official
Binance public data archive is therefore used for historical research data.
No API key is required and this module never places orders.
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timedelta, timezone

import requests

ARCHIVE_BASE = "https://data.binance.vision/data/spot"
INTERVALS = {"5m": "5m", "15m": "15m", "1h": "1h"}
TIMEOUT = 60


def _parse_rows(raw: bytes, start_ms: int, end_ms: int) -> list[dict]:
    rows: list[dict] = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise ValueError("Binance archive contains no CSV")
        with archive.open(names[0]) as fh:
            reader = csv.reader(io.TextIOWrapper(fh, encoding="utf-8"))
            for row in reader:
                if not row or not row[0].isdigit():
                    continue
                ts = int(row[0])
                if ts < start_ms or ts >= end_ms:
                    continue
                rows.append({
                    "timestamp": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                    "close_timestamp": int(row[6]),
                })
    return rows


def _download(url: str) -> bytes | None:
    response = requests.get(url, timeout=TIMEOUT)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.content


def _monthly_url(symbol: str, interval: str, year: int, month: int) -> str:
    name = f"{symbol.upper()}-{interval}-{year:04d}-{month:02d}.zip"
    return f"{ARCHIVE_BASE}/monthly/klines/{symbol.upper()}/{interval}/{name}"


def _daily_url(symbol: str, interval: str, day: datetime) -> str:
    name = f"{symbol.upper()}-{interval}-{day:%Y-%m-%d}.zip"
    return f"{ARCHIVE_BASE}/daily/klines/{symbol.upper()}/{interval}/{name}"


def fetch_klines(symbol: str, interval: str, start: datetime, end: datetime) -> list[dict]:
    if interval not in INTERVALS:
        raise ValueError(f"Unsupported interval: {interval}")
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start/end must be timezone-aware")

    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    rows: list[dict] = []

    cursor = datetime(start.year, start.month, 1, tzinfo=timezone.utc)
    while cursor < end:
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = min(next_month, end)
        full_month = cursor >= start and next_month <= end

        if full_month:
            raw = _download(_monthly_url(symbol, interval, cursor.year, cursor.month))
            if raw is not None:
                rows.extend(_parse_rows(raw, start_ms, end_ms))
            else:
                day = cursor
                while day < month_end:
                    raw_day = _download(_daily_url(symbol, interval, day))
                    if raw_day is not None:
                        rows.extend(_parse_rows(raw_day, start_ms, end_ms))
                    day += timedelta(days=1)
        else:
            day = cursor
            while day < month_end:
                raw_day = _download(_daily_url(symbol, interval, day))
                if raw_day is not None:
                    rows.extend(_parse_rows(raw_day, start_ms, end_ms))
                day += timedelta(days=1)

        cursor = next_month

    rows.sort(key=lambda x: x["timestamp"])
    deduped = []
    seen = set()
    for row in rows:
        if row["timestamp"] in seen:
            continue
        seen.add(row["timestamp"])
        deduped.append(row)
    return deduped


def load_six_months(symbol: str, end: datetime) -> dict[str, list[dict]]:
    start = end - timedelta(days=183)
    return {tf: fetch_klines(symbol, tf, start, end) for tf in INTERVALS}
