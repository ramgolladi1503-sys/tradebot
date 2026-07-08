from core.executable_truth import classify_executable_truth
from core.movement_contract import StrategyCandidate

def test_executable_truth_wires_candidate_feed_truth():
    # If a quote has fallback_used=True, it should fail CandidateFeedTruth and then fail ExecutableTruth
    candidate = {
        "schema_version": 1,
        "strategy_id": "test",
        "movement_type": "BREAKOUT",
        "symbol": "NIFTY",
        "direction": "BUY_CALL",
        "status": "VALIDATED_CANDIDATE",
        "entry_trigger": "price",
        "invalid_if": "price",
        "rank_reason": "edge",
        "fallback_used": True
    }
    # mock it
    candidate["source_flags"] = {"quote_truth": {"fallback_used": True}}
    
    result = classify_executable_truth(candidate)
    assert result.execution_allowed is False
    assert "FALLBACK_USED" in result.reasons
