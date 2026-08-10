import unittest
import sys
from pathlib import Path

# Add scripts directory to path
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root / "scripts" / "research" / "hypothesis_factory"))

from economic_shape_metrics_v11 import compute_trade_shape_metrics, classify_negative_control_severity

class TestEconomicShapeMetricsV11(unittest.TestCase):

    def test_low_win_rate_high_payoff_passes_economic_shape(self):
        # 30% win rate, but wins are +100bps, losses are -20bps
        returns = [100.0, -20.0, -20.0, 100.0, -20.0, -20.0, -20.0, 100.0, -20.0, -20.0]
        res = compute_trade_shape_metrics(returns, cost_bps=3.0, initial_risk_bps=20.0)
        self.assertAlmostEqual(res["win_rate"], 0.30)
        self.assertGreater(res["expectancy_bps"], 10.0)
        self.assertGreater(res["payoff_ratio"], 4.0)

    def test_high_win_rate_poor_payoff_fails_economic_shape(self):
        # 80% win rate (+5bps), 20% massive losses (-50bps)
        returns = [5.0, 5.0, 5.0, 5.0, -50.0, 5.0, 5.0, 5.0, 5.0, -50.0]
        res = compute_trade_shape_metrics(returns, cost_bps=3.0, initial_risk_bps=20.0)
        self.assertAlmostEqual(res["win_rate"], 0.80)
        self.assertLess(res["cost_adjusted_expectancy_bps"], 0.0)

    def test_control_stronger_yields_hard_reject(self):
        real_m = {"cost_adjusted_expectancy_bps": 5.0, "profit_factor": 1.2, "trade_count": 50}
        ctrl_m = {"cost_adjusted_expectancy_bps": 8.0, "profit_factor": 1.5, "trade_count": 45}
        res = classify_negative_control_severity(real_m, ctrl_m)
        self.assertEqual(res["severity"], "HARD_REJECT")
        self.assertEqual(res["candidate_status"], "CONTROL_REJECTED")

    def test_control_small_sample_yields_diagnostic_caution(self):
        real_m = {"cost_adjusted_expectancy_bps": 15.0, "profit_factor": 2.0, "trade_count": 50}
        ctrl_m = {"cost_adjusted_expectancy_bps": 2.0, "profit_factor": 1.1, "trade_count": 4}
        res = classify_negative_control_severity(real_m, ctrl_m)
        self.assertEqual(res["severity"], "DIAGNOSTIC_CAUTION")

    def test_strong_real_signal_yields_pass(self):
        real_m = {"cost_adjusted_expectancy_bps": 20.0, "profit_factor": 2.5, "trade_count": 50}
        ctrl_m = {"cost_adjusted_expectancy_bps": -2.0, "profit_factor": 0.8, "trade_count": 50}
        res = classify_negative_control_severity(real_m, ctrl_m)
        self.assertEqual(res["severity"], "PASS")

if __name__ == "__main__":
    unittest.main()
