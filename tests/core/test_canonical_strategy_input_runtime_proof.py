import os
import sys
import json
import pytest
import tempfile
from unittest.mock import patch

# Add repository root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from scripts.run_canonical_strategy_input_runtime_proof import Harness

def get_harness():
    return Harness()

def test_scenario_a_normal_completed_bar():
    h = get_harness()
    h.scenario_a()
    assert h.evidence["normal_path"]["status"] == "PASS"

def test_scenario_b_warm_seed_startup():
    h = get_harness()
    h.scenario_b()
    assert h.evidence["warm_seed_path"]["status"] == "PASS"
    assert h.evidence["warm_seed_path"]["ohlc_seeded"] is True

def test_scenario_c_exact_completion_boundary():
    h = get_harness()
    h.scenario_c()
    res = h.evidence["boundary_results"]
    assert res.get("2023-01-01 09:30:00") == "PRESENT"
    assert res.get("2023-01-01 09:29:59") == "ABSENT"

def test_scenario_d_late_tick():
    h = get_harness()
    h.scenario_d()
    res = h.evidence["late_tick_result"]
    assert res["accepted"] is False
    assert res["status"] == "REJECTED_LATE_BUCKET"

def test_scenario_e_no_completed_bars():
    h = get_harness()
    h.scenario_e()
    assert h.evidence["no_completed_bars_result"]["status"] == "PASS"

def test_scenario_f_invalid_history():
    h = get_harness()
    h.scenario_f()
    assert h.evidence["invalid_seed_result"]["mutated"] is False

def test_scenario_g_cross_symbol_isolation():
    h = get_harness()
    h.scenario_g()
    assert h.evidence["cross_symbol_result"]["status"] == "ISOLATED"

def test_forward_order_semantic_hash_and_schema():
    with tempfile.TemporaryDirectory() as td:
        h = get_harness()
        h.run_all(reverse=False)
        filepath = os.path.join(td, "evidence.json")
        evidence_hash = h.finish(filepath)
        
        # Check committed evidence schema basics
        assert h.evidence["decision"] == "PASS"
        assert h.evidence["broker_api_called"] is False
        assert h.evidence["is_order_action"] is False
        
        assert evidence_hash != ""
        assert os.path.exists(filepath)
        
        with open(filepath, "r") as f:
            data = json.load(f)
            assert data["decision"] == "PASS"
            assert "scenario_results" in data
            assert data["evidence_hash"] == evidence_hash

def test_reverse_order_semantic_hash():
    with tempfile.TemporaryDirectory() as td:
        h = get_harness()
        h.run_all(reverse=True)
        filepath = os.path.join(td, "evidence_rev.json")
        evidence_hash = h.finish(filepath)
        assert evidence_hash != ""
        assert os.path.exists(filepath)

def test_hash_equality():
    with tempfile.TemporaryDirectory() as td:
        h1 = get_harness()
        h1.run_all(reverse=False)
        hash1 = h1.finish(os.path.join(td, "evidence1.json"))
        
        h2 = get_harness()
        h2.run_all(reverse=True)
        hash2 = h2.finish(os.path.join(td, "evidence2.json"))
        
        assert hash1 == hash2

def test_safety_counters_derived():
    with tempfile.TemporaryDirectory() as td:
        h = get_harness()
        h.run_all()
        # Mock total_broker_calls internally to verify safety counters trigger a failure if >0
        h.total_broker_calls = 1
        h.total_router_calls = 0
        h.finish(os.path.join(td, "evidence.json"))
        assert h.evidence["broker_api_called"] is True
        assert h.evidence["is_order_action"] is True
        assert h.evidence["decision"] == "FAIL"

        h2 = get_harness()
        h2.run_all()
        h2.total_broker_calls = 0
        h2.total_router_calls = 1
        h2.finish(os.path.join(td, "evidence2.json"))
        assert h2.evidence["broker_api_called"] is False
        assert h2.evidence["is_order_action"] is True
        assert h2.evidence["decision"] == "FAIL"
