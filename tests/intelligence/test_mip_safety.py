import pytest
from core.intelligence.robots_gate import RobotsGate
from core.intelligence.calibration.factors import Factor, CalibrationStatus, build_uncalibrated_factor
from core.intelligence.calibration.relevance_model import RelevanceModel
from core.intelligence.context_adapter import ContextAdapter

def test_robots_disallow_blocks_fetching():
    gate = RobotsGate()
    # Assume parsing error fails closed
    assert gate.can_fetch("http://invalid_domain_that_does_not_exist.com") == False

def test_uncalibrated_events_cannot_influence_execution():
    factor = build_uncalibrated_factor("test_freshness", 100, "sec", "test", "test_ptr")
    assert factor.calibration_status == CalibrationStatus.UNCALIBRATED
    assert factor.execution_influence_allowed is False
    assert factor.ranking_influence_allowed is False

def test_intelligence_adapter_cannot_mutate_executable_state():
    adapter = ContextAdapter()
    candidate = {"execution_ok": False, "candidate_status": "blocked"}
    
    factor = build_uncalibrated_factor("test", 1, "test", "test", "test")
    model = RelevanceModel(factors=[factor])
    
    mutated = adapter.inject_context(candidate, [model])
    
    # Must not change these
    assert mutated["execution_ok"] is False
    assert mutated["candidate_status"] == "blocked"
    # Must append metadata
    assert "advisory_context" in mutated
    assert len(mutated["advisory_context"]) == 1
    assert mutated["advisory_context"][0]["has_execution_influence"] is False

def test_intelligence_adapter_cannot_create_candidates():
    adapter = ContextAdapter()
    assert adapter.inject_context({}, []) == {}

def test_no_hardcoded_impact():
    factor = Factor(
        name="test",
        value=1.0,
        unit="test",
        origin="test",
        evidence_pointer="test",
        reason="test",
        measurement_method="test",
        calibration_status=CalibrationStatus.UNCALIBRATED,
        execution_influence_allowed=True, # Attempted bypass
        ranking_influence_allowed=True
    )
    
    # post_init should crush the bypass
    assert factor.execution_influence_allowed is False
    assert factor.ranking_influence_allowed is False
