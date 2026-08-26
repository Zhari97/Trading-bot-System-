import unittest
from datetime import datetime, timezone, timedelta

from signal_timing_guard import candle_is_closed, should_emit_signal


class SignalTimingGuardTests(unittest.TestCase):
    def setUp(self):
        self.open_time = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)

    def test_open_candle_is_rejected(self):
        result = candle_is_closed(self.open_time, 15, self.open_time + timedelta(minutes=14, seconds=59))
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "CANDLE_STILL_OPEN")

    def test_closed_candle_is_accepted(self):
        result = candle_is_closed(self.open_time, 15, self.open_time + timedelta(minutes=15))
        self.assertTrue(result.accepted)

    def test_duplicate_signal_is_suppressed(self):
        previous = ("BTCUSDT", self.open_time.isoformat(), "SHORT", 36.0)
        result = should_emit_signal("BTCUSDT", self.open_time, "SHORT", 38.0, 100.0, previous)
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "DUPLICATE_SIGNAL")

    def test_meaningful_score_change_is_allowed(self):
        previous = ("BTCUSDT", self.open_time.isoformat(), "SHORT", 36.0)
        result = should_emit_signal("BTCUSDT", self.open_time, "SHORT", 42.0, 100.0, previous)
        self.assertTrue(result.accepted)
        self.assertEqual(result.reason, "MEANINGFUL_SCORE_CHANGE")

    def test_direction_change_is_allowed(self):
        previous = ("BTCUSDT", self.open_time.isoformat(), "SHORT", 36.0)
        result = should_emit_signal("BTCUSDT", self.open_time, "LONG", 36.0, 100.0, previous)
        self.assertTrue(result.accepted)


if __name__ == "__main__":
    unittest.main()
