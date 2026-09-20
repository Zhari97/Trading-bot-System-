import unittest

from outcome_tracker import build_summary, directional_return


class OutcomeTrackerTests(unittest.TestCase):
    def test_long_return(self):
        self.assertAlmostEqual(directional_return("LONG", 100, 105), 0.05)

    def test_short_return(self):
        self.assertAlmostEqual(directional_return("SHORT", 100, 95), 0.05)

    def test_neutral_return_is_none(self):
        self.assertIsNone(directional_return("NEUTRO", 100, 105))

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
