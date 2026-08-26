"""Central research configuration.

Keeps the production signal loop lightweight while defining datasets and
experiments for offline research/backtesting.
"""

HISTORICAL_DAYS = 183
TIMEFRAMES = ("5m", "15m", "1h")
TRAIN_FRACTION = 0.50
VALIDATION_FRACTION = 1 / 6
OOS_FRACTION = 1 - TRAIN_FRACTION - VALIDATION_FRACTION

TRADE_PLAN = {
    "max_account_allocation_pct": 5.0,
    "take_profit_pct": 5.0,
    "leverage": 1,
    "execution": "manual_review_only",
}

MULTI_EXCHANGE = {
    "enabled_in_live_signal_loop": False,
    "exchanges": ("binance", "kraken", "coinbase"),
    "purpose": "offline_research_only",
}

METRICS = (
    "win_rate_pct",
    "profit_factor",
    "expectancy_pct",
    "max_drawdown_pct",
    "avg_bars_held",
    "signal_count",
)
