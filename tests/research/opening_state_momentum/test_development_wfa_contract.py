import pytest
from research.opening_state_momentum.development_wfa_contract import WFAContract, build_contract, assign_folds

def test_contract_defaults():
    c = build_contract()
    assert c["contract_id"] == "OPENING_STATE_MOMENTUM_DEVELOPMENT_WFA_V1"
    assert c["strategy_id"] == "REGIME_CONDITIONED_OPENING_STATE_MOMENTUM_V1"
    assert c["outcome_contract_hash"] == "b5fe38367d9795386f6913a7240cb6ac2bbf4f1796415e80d9a9188207fc8c42"
    assert c["development_only_assertion"] is True
    assert c["holdout_access_prohibition"] is True
    assert len(c["frozen_input_hashes"]) == 6

def test_assign_folds():
    # Test 398 sessions
    import datetime
    base_date = datetime.date(2020, 1, 1)
    dates = [(base_date + datetime.timedelta(days=i)).isoformat() for i in range(398)]
    
    # Randomly shuffle dates to prove mapping relies on chronological sorting
    import random
    random.seed(42)
    shuffled_dates = dates[:]
    random.shuffle(shuffled_dates)
    
    mapping = assign_folds(shuffled_dates)
    
    assert len(mapping) == 398
    
    # Count occurrences
    from collections import Counter
    counts = Counter(mapping.values())
    
    # Folds 0, 1, 2 should have 80, Folds 3, 4 should have 79
    assert counts[0] == 80
    assert counts[1] == 80
    assert counts[2] == 80
    assert counts[3] == 79
    assert counts[4] == 79
    
    # Check it's strictly chronological
    for i in range(397):
        assert mapping[dates[i]] <= mapping[dates[i+1]]

def test_assign_folds_overlap():
    import datetime
    base_date = datetime.date(2020, 1, 1)
    dates = [(base_date + datetime.timedelta(days=i)).isoformat() for i in range(398)]
    mapping = assign_folds(dates)
    
    # Every session belongs to exactly one fold
    for d in dates:
        assert isinstance(mapping[d], int)
        assert 0 <= mapping[d] <= 4
