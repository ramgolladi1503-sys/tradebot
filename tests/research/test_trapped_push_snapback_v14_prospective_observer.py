#!/usr/bin/env python3
"""
Unit tests for V14 Trapped Push Prospective Observer (Repaired Scope V15 Metadata Bound)
Verifies zero-order enforcement, opening window scope filtering, completed bar handling,
trigger logging, outcome status, and dynamic commit binding.
"""
import os
import sys
import unittest
import tempfile
import json
import pandas as pd
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root / "scripts" / "research" / "hypothesis_factory"))

from run_trapped_push_snapback_v14_prospective_observer import run_observer

class TestV14ProspectiveObserverRepaired(unittest.TestCase):
    
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.input_path = os.path.join(self.tmp_dir.name, "fixture_bars.csv")
        
        # Create fixture data across two times: opening (09:15-11:30) and afternoon (13:00-14:00)
        data = {
            'datetime': [
                "2026-08-10 09:15:00",
                "2026-08-10 09:20:00",
                "2026-08-10 09:25:00",
                "2026-08-10 09:30:00",
                "2026-08-10 09:35:00",
                "2026-08-10 09:40:00",
                "2026-08-10 09:45:00",
                "2026-08-10 09:50:00",
                "2026-08-10 13:00:00",
                "2026-08-10 13:05:00"
            ],
            'open': [100.0, 100.0, 100.5, 100.2, 100.0, 99.8, 99.5, 99.2, 100.0, 100.5],
            'high': [100.2, 100.7, 100.6, 100.3, 100.1, 99.9, 99.6, 99.3, 100.7, 100.6],
            'low': [99.9, 99.9, 100.1, 100.0, 99.8, 99.6, 99.3, 99.0, 99.9, 100.1],
            'close': [100.1, 100.2, 100.2, 100.1, 99.9, 99.7, 99.4, 99.1, 100.2, 100.2],
            'range_bps': [10.0, 80.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 80.0, 10.0],
            'upper_wick_bps': [2.0, 50.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 50.0, 2.0],
            'body_bps': [5.0, 20.0, -30.0, 5.0, 5.0, 5.0, 5.0, 5.0, 20.0, -30.0]
        }
        df = pd.DataFrame(data)
        df.to_csv(self.input_path, index=False)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_refuse_order_authority(self):
        """Test that runner raises ValueError if order_authority is True."""
        with self.assertRaises(ValueError):
            run_observer("historical_replay", self.input_path, self.tmp_dir.name, "RUN_FAIL", "H1", order_authority=True)

    def test_refuse_broker_write_authority(self):
        """Test that runner raises ValueError if broker_write_authority is True."""
        with self.assertRaises(ValueError):
            run_observer("historical_replay", self.input_path, self.tmp_dir.name, "RUN_FAIL", "H1", broker_write_authority=True)

    def test_refuse_paper_authorized_true(self):
        """Test that runner raises ValueError if paper_authorized is True."""
        with self.assertRaises(ValueError):
            run_observer("historical_replay", self.input_path, self.tmp_dir.name, "RUN_FAIL", "H1", paper_authorized=True)

    def test_refuse_live_authorized_true(self):
        """Test that runner raises ValueError if live_authorized is True."""
        with self.assertRaises(ValueError):
            run_observer("historical_replay", self.input_path, self.tmp_dir.name, "RUN_FAIL", "H1", live_authorized=True)

    def test_opening_window_filter_excludes_out_of_scope_trigger(self):
        """Test that triggers outside 09:15-11:30 IST are logged as out-of-scope and not counted as in-scope triggers."""
        manifest = run_observer("historical_replay", self.input_path, self.tmp_dir.name, "RUN_SCOPE", "H1_TRAPPED_PUSH_SNAPBACK")
        self.assertEqual(manifest["bars_total"], 10)
        self.assertEqual(manifest["bars_in_scope_opening_window"], 8)
        self.assertEqual(manifest["bars_out_of_scope"], 2)
        self.assertEqual(manifest["triggers_in_scope"], 1)

    def test_completed_bar_h1_trigger_detected(self):
        """Test that in-scope H1 trigger is correctly detected on completed bar."""
        manifest = run_observer("historical_replay", self.input_path, self.tmp_dir.name, "RUN_TRIG", "H1_TRAPPED_PUSH_SNAPBACK")
        self.assertEqual(manifest["triggers_in_scope"], 1)
        run_dir = Path(self.tmp_dir.name) / "RUN_TRIG"
        trig_log = run_dir / "candidate_trigger_log.jsonl"
        lines = [json.loads(l) for l in trig_log.read_text().splitlines() if l]
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0]["completed_bar_only"])
        self.assertIn("timestamp_utc", lines[0])
        self.assertIn("timestamp_ist", lines[0])

    def test_outcome_pending_when_less_than_6_future_bars(self):
        """Test that when < 6 future bars exist after trigger, outcome_status is OUTCOME_PENDING_INSUFFICIENT_FUTURE_BARS."""
        data = {
            'datetime': [f"2026-08-10 09:{15+i*5:02d}:00" for i in range(5)],
            'open': [100.0, 100.0, 100.5, 100.2, 100.0],
            'high': [100.2, 100.7, 100.6, 100.3, 100.1],
            'low': [99.9, 99.9, 100.1, 100.0, 99.8],
            'close': [100.1, 100.2, 100.2, 100.1, 99.9],
            'range_bps': [10.0, 80.0, 10.0, 10.0, 10.0],
            'upper_wick_bps': [2.0, 50.0, 2.0, 2.0, 2.0],
            'body_bps': [5.0, 20.0, -30.0, 5.0, 5.0]
        }
        df = pd.DataFrame(data)
        path = os.path.join(self.tmp_dir.name, "short_fixture.csv")
        df.to_csv(path, index=False)

        manifest = run_observer("manual_append", path, self.tmp_dir.name, "RUN_PENDING", "H1_TRAPPED_PUSH_SNAPBACK")
        self.assertEqual(manifest["triggers_in_scope"], 1)
        self.assertEqual(manifest["pending_outcomes"], 1)
        self.assertEqual(manifest["available_outcomes"], 0)

        run_dir = Path(self.tmp_dir.name) / "RUN_PENDING"
        out_log = run_dir / "post_event_return_log.jsonl"
        lines = [json.loads(l) for l in out_log.read_text().splitlines() if l]
        self.assertEqual(lines[0]["outcome_status"], "OUTCOME_PENDING_INSUFFICIENT_FUTURE_BARS")
        self.assertIsNone(lines[0]["exit_close_6b"])

    def test_outcome_available_when_6_future_bars_exist(self):
        """Test that when >= 6 future bars exist after trigger, outcome_status is OUTCOME_AVAILABLE."""
        manifest = run_observer("historical_replay", self.input_path, self.tmp_dir.name, "RUN_AVAIL", "H1_TRAPPED_PUSH_SNAPBACK")
        self.assertEqual(manifest["available_outcomes"], 1)
        self.assertEqual(manifest["pending_outcomes"], 0)

        run_dir = Path(self.tmp_dir.name) / "RUN_AVAIL"
        out_log = run_dir / "post_event_return_log.jsonl"
        lines = [json.loads(l) for l in out_log.read_text().splitlines() if l]
        self.assertEqual(lines[0]["outcome_status"], "OUTCOME_AVAILABLE")
        self.assertIsNotNone(lines[0]["exit_close_6b"])

    def test_logs_created_and_no_order_instructions(self):
        """Test that all required log files are created with zero orders."""
        manifest = run_observer("historical_replay", self.input_path, self.tmp_dir.name, "RUN_LOGS", "H1_TRAPPED_PUSH_SNAPBACK")
        self.assertEqual(manifest["orders_created"], 0)
        self.assertEqual(manifest["broker_writes_created"], 0)

        run_dir = Path(self.tmp_dir.name) / "RUN_LOGS"
        self.assertTrue((run_dir / "candidate_trigger_log.jsonl").exists())
        self.assertTrue((run_dir / "out_of_scope_bar_log.jsonl").exists())
        self.assertTrue((run_dir / "governance_verdict_log.jsonl").exists())
        self.assertTrue((run_dir / "CONTROLLED_VERDICT.json").exists())

    def test_governance_verdict_all_authority_flags_false(self):
        """Test that governance verdict records all authority flags as False."""
        manifest = run_observer("historical_replay", self.input_path, self.tmp_dir.name, "RUN_GOV", "H1_TRAPPED_PUSH_SNAPBACK")
        self.assertTrue(manifest["authority_flags_all_false"])

        run_dir = Path(self.tmp_dir.name) / "RUN_GOV"
        verdict = json.loads((run_dir / "CONTROLLED_VERDICT.json").read_text())
        self.assertFalse(verdict["broker_write_authority"])
        self.assertFalse(verdict["order_authority"])
        self.assertFalse(verdict["paper_authorized"])
        self.assertFalse(verdict["live_authorized"])
        self.assertFalse(verdict["prospective_supported"])

    def test_evidence_commit_passed_through_to_run_verdict(self):
        """Test that evidence_commit argument is correctly bound and logged."""
        manifest = run_observer("historical_replay", self.input_path, self.tmp_dir.name, "RUN_COMM", "H1_TRAPPED_PUSH_SNAPBACK", evidence_commit="78676a3e2d74cbbb2f8739cce9b5cde80f0e44b6")
        self.assertEqual(manifest["evidence_commit"], "78676a3e2d74cbbb2f8739cce9b5cde80f0e44b6")
        self.assertEqual(manifest["metadata_status"], "COMMIT_BOUND")

        run_dir = Path(self.tmp_dir.name) / "RUN_COMM"
        verdict = json.loads((run_dir / "CONTROLLED_VERDICT.json").read_text())
        self.assertEqual(verdict["evidence_commit"], "78676a3e2d74cbbb2f8739cce9b5cde80f0e44b6")
        self.assertEqual(verdict["metadata_status"], "COMMIT_BOUND")

    def test_missing_evidence_commit_records_unknown_not_provided(self):
        """Test that missing evidence_commit records UNKNOWN_NOT_PROVIDED and COMMIT_NOT_BOUND."""
        manifest = run_observer("historical_replay", self.input_path, self.tmp_dir.name, "RUN_NOCOMM", "H1_TRAPPED_PUSH_SNAPBACK")
        self.assertEqual(manifest["evidence_commit"], "UNKNOWN_NOT_PROVIDED")
        self.assertEqual(manifest["metadata_status"], "COMMIT_NOT_BOUND")

    def test_registry_commit_passed_through_if_provided(self):
        """Test that registry_commit argument is correctly recorded."""
        manifest = run_observer("historical_replay", self.input_path, self.tmp_dir.name, "RUN_REGCOMM", "H1_TRAPPED_PUSH_SNAPBACK", registry_commit="b57197b5643b0e99087dbfac091eb9a2054a5e1b")
        self.assertEqual(manifest["registry_commit"], "b57197b5643b0e99087dbfac091eb9a2054a5e1b")

if __name__ == "__main__":
    unittest.main()
