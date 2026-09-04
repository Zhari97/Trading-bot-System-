import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trade_history import append_sent_trade, prune_trade_history


class TradeHistoryTests(unittest.TestCase):
    def test_append_and_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trades.jsonl"
            old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
            path.write_text(
                '{"timestamp_utc":"' + old + '","pair":"OLDUSD"}\n',
                encoding="utf-8",
            )

            append_sent_trade(
                {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "pair": "BTCUSD",
                    "direction": "LONG",
                    "trade_plan": {
                        "entry": 100.0,
                        "take_profit": 105.0,
                        "stop_loss": 99.0,
                    },
                },
                path,
            )

            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
            self.assertEqual(len(lines), 1)
            self.assertIn("BTCUSD", lines[0])
            self.assertIn("SENT", lines[0])

    def test_prune_keeps_recent_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trades.jsonl"
            recent = datetime.now(timezone.utc).isoformat()
            path.write_text(
                '{"timestamp_utc":"' + recent + '","pair":"ETHUSD"}\n',
                encoding="utf-8",
            )
            prune_trade_history(path)
            self.assertIn("ETHUSD", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
