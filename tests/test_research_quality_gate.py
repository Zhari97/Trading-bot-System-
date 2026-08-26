import unittest

from research_quality_gate import evaluate


class ResearchQualityGateTests(unittest.TestCase):
    def test_insufficient_sample(self):
        out = evaluate({"oos_closed": 4, "oos_profit_factor": 3.0, "oos_expectancy_pct": 0.5})
        self.assertEqual(out["status"], "INSUFFICIENT_SAMPLE")

    def test_risk_rejection(self):
        out = evaluate({"oos_closed": 40, "oos_profit_factor": 1.4, "oos_expectancy_pct": 0.1, "oos_max_drawdown_pct": 12.0})
        self.assertEqual(out["status"], "REJECT_RISK")

    def test_no_edge(self):
        out = evaluate({"oos_closed": 40, "oos_profit_factor": 0.9, "oos_expectancy_pct": -0.1, "oos_max_drawdown_pct": 4.0})
        self.assertEqual(out["status"], "NO_EDGE")

    def test_candidate(self):
        out = evaluate({"oos_closed": 40, "oos_profit_factor": 1.4, "oos_expectancy_pct": 0.1, "oos_max_drawdown_pct": 4.0})
        self.assertEqual(out["status"], "CANDIDATE")


if __name__ == "__main__":
    unittest.main()
