import unittest

from outcome_tracker import build_summary, directional_return, _score_bucket


class OutcomeTrackerTests(unittest.TestCase):
    def test_long_return(self):
        self.assertAlmostEqual(directional_return("LONG", 100, 105), 0.05)

    def test_short_return(self):
        self.assertAlmostEqual(directional_return("SHORT", 100, 95), 0.05)

    def test_neutral_return_is_none(self):
        self.assertIsNone(directional_return("NEUTRO", 100, 105))

    def test_score_buckets(self):
        self.assertEqual(_score_bucket(10), "0-19")
        self.assertEqual(_score_bucket(55), "40-59")
        self.assertEqual(_score_bucket(90), "80-100")

    def test_summary_has_analytics_breakdowns(self):
        rows = [
            {"pair": "BNBUSD", "direction": "LONG", "level": "FORTE", "score": 90,
             "outcomes": {"1h": {"status": "READY", "directional_return_pct": 2.0}}},
            {"pair": "ETHUSD", "direction": "SHORT", "level": "WATCH", "score": 30,
             "outcomes": {"1h": {"status": "READY", "directional_return_pct": -1.0}}},
        ]
        summary = build_summary(rows)
        self.assertEqual(summary["by_pair"]["BNBUSD"]["ready_1h"], 1)
        self.assertEqual(summary["by_direction"]["LONG"]["positive_1h"], 1)
        self.assertEqual(summary["by_score_bucket"]["80-100"]["mean_return_1h_pct"], 2.0)

    def test_summary_keeps_signal_counts(self):
        rows = [
            {"direction": "LONG", "level": "WATCH", "outcomes": {"1h": {"status": "READY", "directional_return_pct": 2.0}}},
            {"direction": "SHORT", "level": "SETUP", "outcomes": {"1h": {"status": "READY", "directional_return_pct": -1.0}}},
        ]
        summary = build_summary(rows)
        self.assertEqual(summary["signals"], 2)
        self.assertEqual(summary["ready_by_horizon"]["1h"]["count"], 2)
        self.assertAlmostEqual(summary["ready_by_horizon"]["1h"]["mean_return_pct"], 0.5)


if __name__ == "__main__":
    unittest.main()
