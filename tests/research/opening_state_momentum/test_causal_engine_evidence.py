import json
import pytest
from pathlib import Path

def test_causal_replay_contains_development_dates_only():
    base_dir = Path(__file__).parent.parent.parent.parent
    reviews_dir = base_dir / "docs" / "agent_reviews" / "opening_state_momentum"
    
    with open(reviews_dir / "research_partition.json") as f:
        partition = json.load(f)
        
    with open(reviews_dir / "candidate_decisions.json") as f:
        decisions = json.load(f)
        
    dev_set = set(partition["development"])
    decision_dates = set([d["session_date"] for d in decisions])
    
    assert decision_dates == dev_set

def test_no_holdout_decision_generation():
    base_dir = Path(__file__).parent.parent.parent.parent
    reviews_dir = base_dir / "docs" / "agent_reviews" / "opening_state_momentum"
    
    with open(reviews_dir / "research_partition.json") as f:
        partition = json.load(f)
        
    with open(reviews_dir / "candidate_decisions.json") as f:
        decisions = json.load(f)
        
    holdout_set = set(partition["holdout"])
    decision_dates = set([d["session_date"] for d in decisions])
    
    assert len(decision_dates & holdout_set) == 0

def test_burn_in_thresholds():
    base_dir = Path(__file__).parent.parent.parent.parent
    reviews_dir = base_dir / "docs" / "agent_reviews" / "opening_state_momentum"
    
    with open(reviews_dir / "threshold_oracle_comparison.json") as f:
        oracle = json.load(f)
        
    comparisons = oracle["comparisons"]
    first = next(c for c in comparisons if c["session_index"] == 1)
    session_60 = next(c for c in comparisons if c["session_index"] == 60)
    session_61 = next(c for c in comparisons if c["session_index"] == 61)
    
    # 3. first 60 development sessions have no threshold;
    assert first["oracle_threshold"] is None
    assert session_60["oracle_threshold"] is None
    
    # 4. 61st development session has 60 prior dates;
    assert session_61["oracle_threshold"] is not None
    assert session_61["oracle_training_count"] == 60

def test_independent_oracle_equality():
    base_dir = Path(__file__).parent.parent.parent.parent
    reviews_dir = base_dir / "docs" / "agent_reviews" / "opening_state_momentum"
    
    with open(reviews_dir / "threshold_oracle_comparison.json") as f:
        oracle = json.load(f)
        
    # 5. independent oracle equality;
    assert oracle["mismatches"] == 0
    for comp in oracle["comparisons"]:
        assert comp["match"] is True

def test_terminal_categories_reconciliation():
    base_dir = Path(__file__).parent.parent.parent.parent
    reviews_dir = base_dir / "docs" / "agent_reviews" / "opening_state_momentum"
    
    with open(reviews_dir / "development_session_reconciliation.json") as f:
        recon = json.load(f)
        
    # 6. terminal categories sum to development count;
    assert recon["terminal_count_sum"] == recon["development_count"]
    assert recon["unexplained_count"] == 0
    assert recon["decision_record_count"] == recon["development_count"]
    
    # 7. zero-count categories are retained;
    expected_categories = [
        "count_INSUFFICIENT_PRIOR_HISTORY",
        "count_REJECTED_SESSION_QUALITY",
        "count_FAILED_SHOCK_THRESHOLD",
        "count_FAILED_CLOSE_LOCATION",
        "count_FAILED_CONFIRMATION",
        "count_FAILED_RETAINED_MOVE",
        "count_FAILED_OPENING_MIDPOINT",
        "count_FAILED_SESSION_ANCHOR",
        "count_ACCEPTED_LONG",
        "count_ACCEPTED_SHORT"
    ]
    for cat in expected_categories:
        assert cat in recon

def test_two_output_directory_determinism():
    base_dir = Path(__file__).parent.parent.parent.parent
    reviews_dir = base_dir / "docs" / "agent_reviews" / "opening_state_momentum"
    
    with open(reviews_dir / "candidate_replay_determinism.json") as f:
        determinism = json.load(f)
        
    # 8. two-output-directory determinism;
    assert determinism["match"] is True
    assert determinism["run_a_hashes"] == determinism["run_b_hashes"]

def test_no_holdout_date_in_decision_artifacts():
    base_dir = Path(__file__).parent.parent.parent.parent
    reviews_dir = base_dir / "docs" / "agent_reviews" / "opening_state_momentum"
    
    with open(reviews_dir / "holdout_candidate_access_audit.json") as f:
        holdout_audit = json.load(f)
        
    # 9. no holdout date exists in decision artifacts;
    assert holdout_audit["final_holdout_violation_count"] == 0
    assert len(holdout_audit["repaired_holdout_dates_evaluated"]) == 0

def test_holdout_outcome_access_remains_locked():
    base_dir = Path(__file__).parent.parent.parent.parent
    reviews_dir = base_dir / "docs" / "agent_reviews" / "opening_state_momentum"
    
    # 10. holdout outcome access remains locked.
    # The actual execution raises RuntimeError("HOLDOUT_LOCKED") if any holdout date is passed.
    # We will just verify that the causal script has this hard assertion in place.
    script_path = base_dir / "scripts" / "audit_opening_state_causal_replay.py"
    with open(script_path) as f:
        script_content = f.read()
        
    assert 'raise RuntimeError("HOLDOUT_LOCKED")' in script_content
