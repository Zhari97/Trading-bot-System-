import unittest

from market_regime import classify


def candles(values):
    return [
        {"close": float(v), "high": float(v) * 1.005, "low": float(v) * 0.995}
        for v in values
    ]


class MarketRegimeTests(unittest.TestCase):
    def test_insufficient_history_is_unknown(self):
        self.assertEqual(classify(candles([100] * 20)), "UNKNOWN")

    def test_flat_market_is_range(self):
        self.assertEqual(classify(candles([100] * 60)), "RANGE")

    def test_uptrend_is_trend_up(self):
        self.assertEqual(classify(candles([100 + i * 0.5 for i in range(80)])), "TREND_UP")

    def test_downtrend_is_trend_down(self):
        self.assertEqual(classify(candles([140 - i * 0.5 for i in range(80)])), "TREND_DOWN")


if __name__ == "__main__":
    unittest.main()
