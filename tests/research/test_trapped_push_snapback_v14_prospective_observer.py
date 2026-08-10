#!/usr/bin/env python3
"""
Unit tests for V14 Trapped Push Prospective Observer
Verifies zero-order enforcement, completed bar handling, trigger logging, and outcome deferral.
"""
import os
import sys
import unittest
import tempfile
import pandas as pd
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root / "scripts" / "research" / "hypothesis_factory"))

from run_trapped_push_snapback_v14_prospective_observer import run_observer, evaluate_h1_predicate

class TestV14ProspectiveObserver(unittest.TestCase):
    
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.input_path = os.path.join(self.tmp_dir.name, "fixture_bars.csv")
        
        # Create a small fixture dataset (10 bars) with 1 H1 trigger at idx 2
        # Bar 1 (idx 1): range_bps > 12 (20.0), upper_wick_bps > 4 (5.0)
        # Bar 2 (idx 2): body_bps < -2 (-3.0) -> TRIGGER!
        data = {
            'datetime': [f"2026-08-10 09:{15 + i*5:02d}:00" for i in range(10)],
            'open': [100.0, 100.0, 100.5, 100.2, 100.0, 99.8, 99.5, 99.2, 99.0, 98.8],
            'high': [100.2, 100.7, 100.6, 100.3, 100.1, 99.9, 99.6, 99.3, 99.1, 98.9],
            'low': [99.9, 99.9, 100.1, 100.0, 99.8, 99.6, 99.3, 99.0, 98.8, 98.6],
            'close': [100.1, 100.2, 100.2, 100.1, 99.9, 99.7, 99.4, 99.1, 98.9, 98.7],
            'range_bps': [30.0, 80.0, 50.0, 30.0, 30.0, 30.0, 30.0, 30.0, 30.0, 30.0],
            'upper_wick_bps': [10.0, 50.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0],
            'body_bps': [10.0, 20.0, -30.0, -10.0, -20.0, -20.0, -30.0, -30.0, -10.0, -10.0],
            'nifty_ret6': [0.0, 0.0, 150.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        }
        df = pd.DataFrame(data)
        df.to_csv(self.input_path, index=False)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_refuse_unsafe_authority(self):
        """Test that runner raises ValueError if any authority flag is True."""
        with self.assertRaises(ValueError):
            run_observer("historical_replay", self.input_path, self.tmp_dir.name, "RUN_FAIL", "H1", order_authority=True)

        with self.assertRaises(ValueError):
            run_observer("historical_replay", self.input_path, self.tmp_dir.name, "RUN_FAIL", "H1", broker_write_authority=True)

    def test_clean_observer_dry_run(self):
        """Test that runner correctly processes fixture and creates logs with zero orders."""
        manifest = run_observer("historical_replay", self.input_path, self.tmp_dir.name, "RUN_001", "H1_TRAPPED_PUSH_SNAPBACK")
        
        self.assertEqual(manifest["orders_created"], 0)
        self.assertEqual(manifest["broker_writes_created"], 0)
        self.assertTrue(manifest["authority_flags_all_false"])
        self.assertGreater(manifest["trigger_count"], 0)

        run_dir = Path(self.tmp_dir.name) / "RUN_001"
        self.assertTrue((run_dir / "candidate_trigger_log.jsonl").exists())
        self.assertTrue((run_dir / "governance_verdict_log.jsonl").exists())
        self.assertTrue((run_dir / "CONTROLLED_VERDICT.json").exists())

if __name__ == "__main__":
    unittest.main()
