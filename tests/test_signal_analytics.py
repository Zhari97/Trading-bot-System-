import unittest

from signal_analytics import analyze, enrich, group_summary


class SignalAnalyticsTests(unittest.TestCase):
    def test_enrich_creates_stable_buckets(self):
        row = enrich({"score": 72, "confluence": 85, "outcome": "TP"})
        self.assertEqual(row["score_bucket"], "<80")
        self.assertEqual(row["confluence_bucket"], "<90")
        self.assertEqual(row["regime"], "UNKNOWN")

    def test_group_summary_ignores_small_samples(self):
        rows = [{"outcome": "TP", "score": 70, "confluence": 80}] * 4
        self.assertEqual(group_summary(rows, "score_bucket", min_trades=5), [])

    def test_group_summary_counts_wins_and_losses(self):
        rows = [
            {"outcome": "TP", "score": 70, "confluence": 80},
            {"outcome": "TP", "score": 72, "confluence": 82},
            {"outcome": "SL", "score": 74, "confluence": 84},
            {"outcome": "SL", "score": 76, "confluence": 86},
            {"outcome": "TP", "score": 78, "confluence": 88},
        ]
        result = group_summary(rows, "score_bucket", min_trades=5)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["trades"], 5)
        self.assertEqual(result[0]["wins"], 3)
        self.assertAlmostEqual(result[0]["win_rate_pct"], 60.0)

    def test_analyze_returns_all_dimensions(self):
        rows = [{"outcome": "TP", "score": 70, "confluence": 80}] * 5
        result = analyze(rows, min_trades=5)
        for key in ("timeframe", "direction", "regime", "score_bucket", "confluence_bucket", "trend", "momentum", "setup"):
            self.assertIn(key, result)


if __name__ == "__main__":
    unittest.main()
