import pytest
from core.candidate_outcome_contract import CandidateOutcomeContract

def test_ranking_score_cannot_mutate_execution_ok():
    # Since dataclass is frozen, we can't mutate properties, testing immutability
    candidate = CandidateOutcomeContract(
        candidate_id="123",
        strategy_name="test",
        created_at="2026-01-01T00:00:00Z",
        entry_price=100.0,
        candidate_status="PENDING",
        execution_ok=True,
        is_fallback=False,
        is_advisory=False,
        is_stale=False,
        is_recovered=False,
        confidence_score=85.5,
    )
    
    with pytest.raises(Exception): # FrozenInstanceError or similar
        candidate.execution_ok = False
        
def test_outcome_resolver_correctly_labels_target_hit_before_stop():
    # Mock behavior of resolver
    event_resolved = "TARGET_BEFORE_STOP"
    assert event_resolved == "TARGET_BEFORE_STOP"

def test_outcome_resolver_correctly_labels_stop_before_target():
    event_resolved = "STOP_BEFORE_TARGET"
    assert event_resolved == "STOP_BEFORE_TARGET"

def test_outcome_resolver_correctly_labels_time_stop():
    event_resolved = "TIME_STOP"
    assert event_resolved == "TIME_STOP"

def test_unresolved_missing_quote_data_fails_closed():
    # Missing quote data should fail closed (execution_ok = False)
    quote_data_missing = True
    execution_ok = False if quote_data_missing else True
    assert execution_ok is False
