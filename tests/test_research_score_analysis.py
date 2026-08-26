import unittest

from research_score_analysis import analyze_records, compare_timeframes


class ResearchScoreAnalysisTests(unittest.TestCase):
    def _records(self):
        rows = []
        for idx, score, outcome in [
            (10, 20, "SL"),
            (20, 30, "SL"),
            (30, 50, "TP"),
            (40, 70, "TP"),
            (50, 90, "TP"),
            (60, 90, "TP"),
        ]:
            rows.append({
                "candle_index": idx,
                "partition": "oos",
                "score": score,
                "outcome": outcome,
                "entry": 100,
                "exit": 101 if outcome == "TP" else 99,
                "direction": "LONG",
                "regime": "TREND_UP" if idx <= 30 else "RANGE",
            })
        return rows

    def test_score_buckets_are_threshold_free_and_bounded(self):
        report = analyze_records(self._records())
        self.assertEqual(report["overall"]["0-40"]["closed"], 2)
        self.assertEqual(report["overall"]["80-100"]["win_rate_pct"], 100.0)
        self.assertEqual(report["stability"]["high_minus_low_win_rate_pp"], 100.0)
        self.assertEqual(report["stability"]["oos_high_minus_low_win_rate_pp"], 100.0)
        self.assertEqual(report["stability"]["research_status"], "PROMISING_BUT_UNSTABLE")

    def test_partition_is_respected(self):
        report = analyze_records(self._records())
        self.assertEqual(report["partitions"]["oos"]["signals"], 6)
        self.assertEqual(report["partitions"]["train"]["signals"], 0)

    def test_regime_stratification_is_present(self):
        report = analyze_records(self._records())
        self.assertEqual(set(report["regimes"]), {"TREND_UP", "RANGE"})
        self.assertEqual(report["regimes"]["TREND_UP"]["closed"], 3)
        self.assertEqual(report["regimes"]["RANGE"]["closed"], 3)
        self.assertEqual(report["stability"]["positive_separation_regimes"], 1)

    def test_chronological_windows_are_reported(self):
        report = analyze_records(self._records())
        self.assertEqual(report["stability"]["walk_forward_windows"], 4)
        self.assertEqual(len(report["walk_forward"]), 4)
        self.assertEqual(sum(w["signals"] for w in report["walk_forward"]), 6)

    def test_timeframe_comparison_ranks_separation(self):
        strong = self._records()
        weak = [dict(r, score=score) for r, score in zip(strong, [20, 30, 40, 50, 60, 70])]
        comparison = compare_timeframes({"1h": strong, "5m": weak})
        self.assertEqual(comparison["score_separation_rank"][0], "1h")


if __name__ == "__main__":
    unittest.main()
