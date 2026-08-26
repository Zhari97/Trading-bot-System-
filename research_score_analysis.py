"""Research-only score calibration and stability diagnostics.

The analyzer deliberately avoids choosing an optimal threshold. It measures
whether higher continuous research scores correspond to better outcomes across
train, validation and out-of-sample partitions, chronological windows and
market regimes.
"""
from __future__ import annotations

BUCKETS = ((0.0, 40.0), (40.0, 60.0), (60.0, 80.0), (80.0, 100.000001))
PARTITIONS = ("train", "validation", "oos")
WALK_FORWARD_WINDOWS = 4


def _closed(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("outcome") in ("TP", "SL")]


def _win_rate(records: list[dict]) -> float:
    closed = _closed(records)
    return 100.0 * sum(r.get("outcome") == "TP" for r in closed) / len(closed) if closed else 0.0


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _bucket_name(low: float, high: float) -> str:
    return f"{int(low)}-{int(high if high <= 100 else 100)}"


def _score(record: dict) -> float | None:
    value = record.get("score")
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(100.0, value))


def _bucket_stats(records: list[dict]) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    for low, high in BUCKETS:
        selected = [r for r in records if (s := _score(r)) is not None and low <= s < high]
        closed = _closed(selected)
        returns = []
        for r in closed:
            try:
                entry = float(r.get("entry", 0) or 0)
                exit_price = float(r.get("exit", 0) or 0)
                if entry <= 0 or exit_price <= 0:
                    continue
                raw = (exit_price / entry - 1.0) * 100.0
                returns.append(raw if r.get("direction") == "LONG" else -raw)
            except (TypeError, ValueError):
                continue
        name = _bucket_name(low, high)
        stats[name] = {
            "signals": len(selected),
            "closed": len(closed),
            "wins": sum(r.get("outcome") == "TP" for r in closed),
            "losses": sum(r.get("outcome") == "SL" for r in closed),
            "win_rate_pct": round(_win_rate(selected), 4),
            "expectancy_pct": round(_mean(returns), 6),
        }
    return stats


def _monotonicity(bucket_stats: dict[str, dict]) -> dict:
    ordered = [bucket_stats[_bucket_name(low, high)] for low, high in BUCKETS]
    available = [x for x in ordered if x["closed"] > 0]
    if len(available) < 2:
        return {"available_buckets": len(available), "non_decreasing_win_rate": None, "win_rate_lift_pp": None}
    wins = [x["win_rate_pct"] for x in available]
    non_decreasing = all(b >= a for a, b in zip(wins, wins[1:]))
    return {
        "available_buckets": len(available),
        "non_decreasing_win_rate": non_decreasing,
        "win_rate_lift_pp": round(wins[-1] - wins[0], 4),
    }


def _partition_records(records: list[dict], partition: str) -> list[dict]:
    if "partition" in records[0] if records else False:
        return [r for r in records if r.get("partition") == partition]
    if not records:
        return []
    max_index = max(int(r.get("candle_index", 0)) for r in records)
    train_end = max_index * 0.50
    validation_end = max_index * (0.50 + 1 / 6)
    if partition == "train":
        return [r for r in records if int(r.get("candle_index", 0)) < train_end]
    if partition == "validation":
        return [r for r in records if train_end <= int(r.get("candle_index", 0)) < validation_end]
    return [r for r in records if int(r.get("candle_index", 0)) >= validation_end]


def _partition_separation(partitions: dict[str, dict]) -> dict[str, float | None]:
    """Expose score separation per chronological partition without thresholds."""
    return {
        name: data["monotonicity"]["win_rate_lift_pp"]
        for name, data in partitions.items()
    }


def _regime_reports(records: list[dict]) -> dict[str, dict]:
    """Measure score separation independently inside each observed regime."""
    grouped: dict[str, list[dict]] = {}
    for record in records:
        regime = str(record.get("regime") or "UNKNOWN")
        grouped.setdefault(regime, []).append(record)

    reports: dict[str, dict] = {}
    for regime, rows in sorted(grouped.items()):
        buckets = _bucket_stats(rows)
        reports[regime] = {
            "signals": len(rows),
            "closed": len(_closed(rows)),
            "win_rate_pct": round(_win_rate(rows), 4),
            "buckets": buckets,
            "monotonicity": _monotonicity(buckets),
        }
    return reports


def _chronological_windows(records: list[dict], count: int = WALK_FORWARD_WINDOWS) -> list[dict]:
    """Return fixed chronological stability windows without OOS optimization."""
    if not records or count <= 0:
        return []
    indices = [int(r.get("candle_index", 0)) for r in records]
    minimum, maximum = min(indices), max(indices)
    if minimum == maximum:
        windows = [records]
    else:
        width = (maximum - minimum + 1) / count
        windows = []
        for window_index in range(count):
            start = minimum + window_index * width
            end = minimum + (window_index + 1) * width
            if window_index == count - 1:
                selected = [r for r in records if start <= int(r.get("candle_index", 0)) <= maximum]
            else:
                selected = [r for r in records if start <= int(r.get("candle_index", 0)) < end]
            windows.append(selected)

    reports = []
    for index, rows in enumerate(windows, start=1):
        buckets = _bucket_stats(rows)
        reports.append({
            "window": index,
            "signals": len(rows),
            "closed": len(_closed(rows)),
            "win_rate_pct": round(_win_rate(rows), 4),
            "buckets": buckets,
            "monotonicity": _monotonicity(buckets),
        })
    return reports


def analyze_records(records: list[dict]) -> dict:
    """Return threshold-free score stability diagnostics for one timeframe."""
    if not records:
        return {
            "signals": 0,
            "partitions": {},
            "regimes": {},
            "walk_forward": [],
            "overall": _bucket_stats([]),
            "stability": {},
        }

    partitions = {}
    for partition in PARTITIONS:
        part = _partition_records(records, partition)
        buckets = _bucket_stats(part)
        partitions[partition] = {
            "signals": len(part),
            "closed": len(_closed(part)),
            "win_rate_pct": round(_win_rate(part), 4),
            "buckets": buckets,
            "monotonicity": _monotonicity(buckets),
        }

    overall = _bucket_stats(records)
    regimes = _regime_reports(records)
    oos_records = _partition_records(records, "oos")
    oos_regimes = _regime_reports(oos_records)
    walk_forward = _chronological_windows(records)

    stable_flags = [
        p["monotonicity"]["non_decreasing_win_rate"]
        for p in partitions.values()
        if p["monotonicity"]["non_decreasing_win_rate"] is not None
    ]
    high = overall["80-100"]
    low = overall["0-40"]
    partition_lifts = _partition_separation(partitions)
    positive_partition_lifts = [
        value for value in partition_lifts.values() if value is not None and value > 0
    ]
    oos_lift = partition_lifts.get("oos")
    all_partitions_covered = len(stable_flags) == len(PARTITIONS)

    regime_flags = [
        report["monotonicity"]["non_decreasing_win_rate"]
        for report in regimes.values()
        if report["monotonicity"]["non_decreasing_win_rate"] is not None
    ]
    positive_regime_lifts = [
        report["monotonicity"]["win_rate_lift_pp"]
        for report in regimes.values()
        if report["monotonicity"]["win_rate_lift_pp"] is not None
        and report["monotonicity"]["win_rate_lift_pp"] > 0
    ]
    positive_oos_regime_lifts = [
        report["monotonicity"]["win_rate_lift_pp"]
        for report in oos_regimes.values()
        if report["monotonicity"]["win_rate_lift_pp"] is not None
        and report["monotonicity"]["win_rate_lift_pp"] > 0
    ]
    walk_forward_lifts = [
        report["monotonicity"]["win_rate_lift_pp"]
        for report in walk_forward
        if report["monotonicity"]["win_rate_lift_pp"] is not None
    ]
    walk_forward_flags = [
        report["monotonicity"]["non_decreasing_win_rate"]
        for report in walk_forward
        if report["monotonicity"]["non_decreasing_win_rate"] is not None
    ]

    if all_partitions_covered and all(stable_flags) and oos_lift is not None and oos_lift > 0:
        research_status = "STABLE_SIGNAL_RELATIONSHIP"
    elif oos_lift is not None and oos_lift > 0:
        research_status = "PROMISING_BUT_UNSTABLE"
    else:
        research_status = "NO_STABLE_SCORE_EDGE"

    stability = {
        "partitions_with_monotonicity": len(stable_flags),
        "partitions_monotonic": sum(flag is True for flag in stable_flags),
        "monotonicity_consistent": bool(stable_flags) and all(stable_flags),
        "partition_high_minus_low_win_rate_pp": partition_lifts,
        "positive_separation_partitions": len(positive_partition_lifts),
        "oos_high_minus_low_win_rate_pp": oos_lift,
        "high_score_closed": high["closed"],
        "high_score_win_rate_pct": high["win_rate_pct"],
        "low_score_closed": low["closed"],
        "low_score_win_rate_pct": low["win_rate_pct"],
        "high_minus_low_win_rate_pp": round(high["win_rate_pct"] - low["win_rate_pct"], 4),
        "regimes_with_monotonicity": len(regime_flags),
        "regimes_monotonic": sum(flag is True for flag in regime_flags),
        "positive_separation_regimes": len(positive_regime_lifts),
        "positive_separation_oos_regimes": len(positive_oos_regime_lifts),
        "walk_forward_windows": len(walk_forward),
        "walk_forward_positive_lift_windows": sum(lift > 0 for lift in walk_forward_lifts),
        "walk_forward_monotonic_windows": sum(flag is True for flag in walk_forward_flags),
        "research_status": research_status,
    }
    return {
        "signals": len(records),
        "closed": len(_closed(records)),
        "overall": overall,
        "partitions": partitions,
        "regimes": regimes,
        "oos_regimes": oos_regimes,
        "walk_forward": walk_forward,
        "stability": stability,
    }


def compare_timeframes(timeframe_records: dict[str, list[dict]]) -> dict[str, dict]:
    """Compare score separation by timeframe without selecting a threshold."""
    reports = {tf: analyze_records(records) for tf, records in timeframe_records.items()}

    def rank_key(tf: str) -> tuple:
        stability = reports[tf]["stability"]
        oos_lift = stability.get("oos_high_minus_low_win_rate_pp")
        return (
            oos_lift is not None and oos_lift > 0,
            stability.get("partitions_monotonic", 0),
            stability.get("positive_separation_partitions", 0),
            oos_lift if oos_lift is not None else float("-inf"),
            stability.get("high_score_closed", 0),
        )

    ranked = sorted(reports, key=rank_key, reverse=True)
    return {"timeframes": reports, "score_separation_rank": ranked}
