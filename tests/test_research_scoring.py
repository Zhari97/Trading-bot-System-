import unittest

from research_scoring import continuous_categories


class FakeContext:
    i = 2
    chiusure = [100.0, 101.0, 102.0]
    ema50 = [100.0, 100.5, 101.0]
    rsi14 = [50.0, 60.0, 75.0]
    macd_istogramma = [-0.1, 0.2, 0.5]


class ResearchScoringTests(unittest.TestCase):
    def test_scores_are_continuous_and_bounded(self):
        results = [
            {"nome": "Ichimoku semplificato", "voto": "LONG"},
            {"nome": "Bollinger Bands", "voto": "LONG"},
            {"nome": "Fibonacci retracement", "voto": "NEUTRO"},
            {"nome": "Price Action", "voto": "LONG"},
        ]
        scores = continuous_categories(FakeContext(), results)
        for key in ("trend", "momentum", "setup"):
            self.assertGreaterEqual(scores[key], 0.0)
            self.assertLessEqual(scores[key], 100.0)
        self.assertGreater(scores["trend"], 50.0)
        self.assertGreater(scores["momentum"], 50.0)
        self.assertGreater(scores["setup"], 50.0)
        self.assertEqual(scores["scoring_version"], "research_continuous_v1")


if __name__ == "__main__":
    unittest.main()
