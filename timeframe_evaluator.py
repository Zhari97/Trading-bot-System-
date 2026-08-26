"""Multi-timeframe evaluation configuration.

Keeps 5m, 15m and 1h as separate experiments. No timeframe is promoted
without out-of-sample evidence.
"""

TIMEFRAMES = {
    "5m": {"minutes": 5, "role": "entry_timing"},
    "15m": {"minutes": 15, "role": "setup_momentum"},
    "1h": {"minutes": 60, "role": "trend_filter"},
}

EXPERIMENTS = {
    "5m_only": ["5m"],
    "15m_only": ["15m"],
    "1h_only": ["1h"],
    "1h_15m": ["1h", "15m"],
    "1h_15m_5m": ["1h", "15m", "5m"],
}

METRICS = (
    "signals",
    "closed",
    "win_rate_pct",
    "profit_factor",
    "expectancy_pct",
    "max_drawdown_pct",
    "avg_bars_held",
)


def experiment_plan() -> dict:
    return {
        "timeframes": TIMEFRAMES,
        "experiments": EXPERIMENTS,
        "metrics": METRICS,
        "rule": "select only after validation and out-of-sample comparison",
    }
