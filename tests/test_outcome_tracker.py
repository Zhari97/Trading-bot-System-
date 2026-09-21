import unittest
from datetime import datetime, timezone

from outcome_tracker import build_summary, directional_return, evaluate_signal


class OutcomeTrackerTests(unittest.TestCase):
    def test_long_return(self):
        self.assertAlmostEqual(directional_return("LONG", 100, 105), 0.05)

    def test_short_return(self):
        self.assertAlmostEqual(directional_return("SHORT", 100, 95), 0.05)

    def test_neutral_return_is_none(self):
        self.assertIsNone(directional_return("NEUTRO", 100, 105))

    def test_completed_candle_is_required(self):
        signal = {
            "timestamp_utc": "2026-09-21T09:00:00+00:00",
            "pair": "ETHUSD",
            "price": 100.0,
            "direction": "LONG",
        }
        candles = [
            {"ts": int(datetime(2026, 9, 21, 9, 30, tzinfo=timezone.utc).timestamp()), "high": 101, "low": 99, "close": 100.5},
            {"ts": int(datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc).timestamp()), "high": 103, "low": 98, "close": 102},
        ]
        now = datetime(2026, 9, 21, 10, 5, tzinfo=timezone.utc)
        result = evaluate_signal(signal, candles, now)
        self.assertEqual(result["outcomes"]["1h"]["status"], "PENDING")

    def test_summary_keeps_signal_counts(self):
        rows = [
            {"direction": "LONG", "level": "WATCH", "pair": "ETHUSD", "score": 72.5,
             "outcomes": {"1h": {"status": "READY", "directional_return_pct": 2.0, "mfe_pct": 3.0, "mae_pct": -1.0}}},
            {"direction": "SHORT", "level": "SETUP", "pair": "XMRUSD", "score": 10,
             "outcomes": {"1h": {"status": "READY", "directional_return_pct": -1.0, "mfe_pct": 1.5, "mae_pct": -2.5}}},
        ]
        summary = build_summary(rows)
        self.assertEqual(summary["signals"], 2)
        self.assertEqual(summary["outcome_errors"], 0)
        self.assertEqual(summary["ready_by_horizon"]["1h"]["pending_count"], 0)
        self.assertEqual(summary["ready_by_horizon"]["4h"]["pending_count"], 0)
        self.assertEqual(summary["ready_by_horizon"]["1h"]["count"], 2)
        self.assertAlmostEqual(summary["ready_by_horizon"]["1h"]["coverage_pct"], 100.0)
        self.assertAlmostEqual(summary["ready_by_horizon"]["1h"]["mean_return_pct"], 0.5)
        self.assertAlmostEqual(summary["ready_by_horizon"]["1h"]["mean_mfe_pct"], 2.25)
        self.assertAlmostEqual(summary["ready_by_horizon"]["1h"]["mean_mae_pct"], -1.75)
        self.assertAlmostEqual(summary["by_direction"]["LONG"]["positive_rate_1h_pct"], 100.0)
        self.assertAlmostEqual(summary["by_direction"]["SHORT"]["positive_rate_1h_pct"], 0.0)
        self.assertEqual(summary["by_pair"]["ETHUSD"]["signals"], 1)
        self.assertEqual(summary["by_score_bucket"]["60-79"]["signals"], 1)


if __name__ == "__main__":
    unittest.main()
