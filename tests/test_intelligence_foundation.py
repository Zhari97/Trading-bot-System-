import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from audit_ledger import append_event, verify
from execution_realism import ExecutionScenario, cap_order_notional, estimate_cost
from market_data_quality import validate_ohlcv
from research.evidence_store import EvidenceRecord, append_evidence, verify_chain
from strategy_lifecycle import DecayThresholds, StrategyStatus, assess_decay, transition


class IntelligenceFoundationTests(unittest.TestCase):
    def test_evidence_hash_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.jsonl"
            append_evidence(EvidenceRecord("e1", "candidate-1", "OOS", "btc-183d", "1h", "abc", "a.json", {"pf": 1.2}, "WARNING"), path)
            append_evidence(EvidenceRecord("e2", "candidate-1", "SHADOW", "btc-183d", "1h", "def", "b.json", {"pf": 1.3}, "PASS"), path)
            self.assertTrue(verify_chain(path)["valid"])
            rows = path.read_text(encoding="utf-8").splitlines()
            rows[0] = rows[0].replace("WARNING", "PASS")
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")
            self.assertFalse(verify_chain(path)["valid"])

    def test_lifecycle_rejects_unsafe_transition(self):
        self.assertEqual(transition(StrategyStatus.CANDIDATE, StrategyStatus.SHADOW), StrategyStatus.SHADOW)
        with self.assertRaises(ValueError):
            transition(StrategyStatus.RESEARCH, StrategyStatus.LIVE)

    def test_decay_needs_enough_data(self):
        result = assess_decay({"return_pct": 10, "profit_factor": 1.5}, {"observations": 10, "return_pct": 1, "profit_factor": 0.5})
        self.assertEqual(result.status, "INSUFFICIENT_DATA")
        result = assess_decay({"return_pct": 10, "profit_factor": 1.5}, {"observations": 40, "return_pct": 4, "profit_factor": 1.0})
        self.assertEqual(result.status, "DECAYED")

    def test_execution_capacity_and_sqrt_impact(self):
        filled, participation, capped = cap_order_notional(2000, 10000, max_participation=0.1)
        self.assertEqual(filled, 1000)
        self.assertAlmostEqual(participation, 0.1)
        self.assertTrue(capped)
        cost = estimate_cost(
            ExecutionScenario("sqrt", fee_bps_round_trip=10, impact_model="sqrt", impact_coefficient=0.1),
            order_notional=1000,
            adv_notional=10000,
            volatility=0.02,
        )
        self.assertGreater(cost.total_cost_pct, 0)
        self.assertAlmostEqual(cost.participation, 0.1)

    def test_market_data_freshness(self):
        now = datetime.now(timezone.utc)
        rows = [{
            "timestamp": (now - timedelta(seconds=30)).isoformat(),
            "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 10,
        }]
        report = validate_ohlcv(rows, now=now, max_age_seconds=60)
        self.assertTrue(report.valid)
        self.assertTrue(report.fresh)

    def test_audit_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.jsonl"
            append_event("SIGNAL_SENT", {"pair": "BTCUSDT", "score": 84}, path=path)
            append_event("OUTCOME", {"result": "TP"}, path=path)
            self.assertTrue(verify(path)["valid"])


if __name__ == "__main__":
    unittest.main()
