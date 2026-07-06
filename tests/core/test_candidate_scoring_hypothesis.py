import pytest
from hypothesis import given, strategies as st
from core.candidate_scoring import _regime_fit, _canonical_regime_label

# Strategy for candidates
candidate_strategy = st.fixed_dictionaries({
    "regime": st.sampled_from(["TREND", "RANGE", "EXPIRY", "CHOP", "EVENT", "NOISE", "UNKNOWN", None]),
    "countertrend": st.booleans(),
    "market_open": st.booleans(),
    "regime_alignment_score": st.one_of(st.floats(min_value=0.0, max_value=1.0), st.none()),
})

# Strategy for market data
market_data_strategy = st.fixed_dictionaries({
    "regime": st.sampled_from(["TREND", "RANGE", "EXPIRY", "CHOP", "EVENT", "NOISE", "UNKNOWN", None]),
    "market_open": st.booleans(),
})

@given(candidate=candidate_strategy, market_data=market_data_strategy)
def test_candidate_scoring_regime_fit_hypothesis(candidate, market_data):
    score_inputs_used = {}
    
    fit = _regime_fit(candidate, market_data, score_inputs_used)
    
    # Invariant: Score must be clamped between 0.0 and 1.0
    assert 0.0 <= fit <= 1.0
    
    # Invariant: Score inputs dict is populated
    assert "regime" in score_inputs_used
    assert "market_open" in score_inputs_used
    
    # Invariant: if countertrend is True, there should be a penalty (unless explicit alignment overrides heavily)
    if candidate["countertrend"] and candidate["regime_alignment_score"] is None:
        assert fit < 0.65  # Base max for trend is 0.82 - 0.22 = 0.6
