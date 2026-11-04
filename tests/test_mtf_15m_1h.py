import unittest

from research.mtf_15m_1h import align_15m_with_1h, build_report


def record(timestamp, direction, partition="train", outcome="TP"):
    return {
        "timestamp": timestamp,
        "direction": direction,
        "partition": partition,
        "entry": 100.0,
        "exit": 105.0 if direction == "LONG" else 95.0,
        "outcome": outcome,
        "bars": 2,
    }


class Mtf15m1hResearchTests(unittest.TestCase):
    def test_alignment_uses_only_a_previously_closed_1h_signal(self):
        high = [record("2025-01-01T10:00:00Z", "LONG", outcome="SL")]
        low = [
            record("2025-01-01T10:15:00Z", "LONG"),  # closes at 10:30; 1h closes at 11:00
            record("2025-01-01T10:45:00Z", "LONG"),  # same close; rejected as ambiguous
            record("2025-01-01T11:00:00Z", "LONG"),  # closes at 11:15; safely after 1h close
        ]

        aligned, counts = align_15m_with_1h(low, high)

        self.assertEqual(counts["rejected_no_closed_1h"], 2)
        self.assertEqual(len(aligned), 1)
        self.assertEqual(aligned[0]["timestamp"], "2025-01-01T11:00:00Z")
        self.assertEqual(aligned[0]["mtf_high_available_at"], "2025-01-01T11:00:00Z")
        self.assertNotIn("mtf_high_outcome", aligned[0])

        # An ex-post 1h outcome must not influence the pre-entry selection.
        equivalent_high = [record("2025-01-01T10:00:00Z", "LONG", outcome="TP")]
        equivalent_aligned, _ = align_15m_with_1h(low, equivalent_high)
        self.assertEqual(aligned, equivalent_aligned)

    def test_alignment_rejects_stale_or_disagreeing_confirmation(self):
        high = [record("2025-01-01T10:00:00Z", "LONG")]
        low = [
            record("2025-01-01T11:15:00Z", "SHORT"),
            record("2025-01-01T15:15:00Z", "LONG"),
        ]

        aligned, counts = align_15m_with_1h(low, high)

        self.assertEqual(aligned, [])
        self.assertEqual(counts["rejected_direction_disagreement"], 1)
        self.assertEqual(counts["rejected_stale_1h"], 1)

    def test_report_has_metrics_for_each_chronological_partition(self):
        high = [
            record("2025-01-01T10:00:00Z", "LONG"),
            record("2025-01-02T10:00:00Z", "LONG"),
            record("2025-01-03T10:00:00Z", "LONG"),
        ]
        low = [
            record("2025-01-01T11:00:00Z", "LONG", "train", "TP"),
            record("2025-01-02T11:00:00Z", "LONG", "validation", "SL"),
            record("2025-01-03T11:00:00Z", "LONG", "oos", "TP"),
        ]
        payload = {
            "generated_at": "2025-01-04T00:00:00Z",
            "symbol": "BTCUSDT",
            "history_days": 183,
            "allocation_pct": 5.0,
            "timeframes": {
                "15m": {"records": low},
                "1h": {"records": high},
            },
        }

        report = build_report(payload)

        self.assertTrue(report["research_only"])
        self.assertFalse(report["method"]["optimization_on_oos"])
        self.assertFalse(report["method"]["automatic_orders"])
        self.assertEqual(report["alignment_counts"]["aligned"], 3)
        for partition in ("train", "validation", "oos"):
            self.assertEqual(report["metrics"][partition]["signals"], 1)
            self.assertEqual(report["metrics"][partition]["closed"], 1)

    def test_report_refuses_any_symbol_other_than_btcusdt(self):
        with self.assertRaisesRegex(ValueError, "BTCUSDT"):
            build_report({"symbol": "ETHUSDT", "timeframes": {}})


if __name__ == "__main__":
    unittest.main()
