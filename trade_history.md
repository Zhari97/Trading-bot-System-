# Telegram Trade History

Runtime history is written to `data/trade_history/trades.jsonl` and uploaded by the signal workflow as a GitHub Actions artifact with retention longer than 7 days.

Each record includes the UTC signal timestamp, pair, direction, score, entry, TP, SL, timeframe context, and Telegram delivery status.
