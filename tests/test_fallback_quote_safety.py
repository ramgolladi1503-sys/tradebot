import pytest
from core.candidate_pool_quality import _is_executable, _is_near_executable

def test_fallback_quotes_cannot_become_executable():
    """
    Test proving that candidates generated from fallback or recovered_fallback
    quotes cannot become executable, regardless of edge score or permission.
    """
    # A candidate that looks perfectly executable in every other way
    base_candidate = {
        "expectancy_status": "KEEP",
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "execution_truth_state": "EXECUTABLE",
        "reportable_executable": True,
        "execution_allowed": True,
    }
    
    # 1. Without fallback, it should be executable
    assert _is_executable(base_candidate) is True, "Base candidate should be executable."
    
    # 2. With fallback quote_source
    candidate_with_fallback = dict(base_candidate)
    candidate_with_fallback["quote_source"] = "REST_FALLBACK"
    assert _is_executable(candidate_with_fallback) is False, "REST_FALLBACK quote_source must not be executable."
    assert _is_near_executable(candidate_with_fallback) is False, "REST_FALLBACK quote_source must not be near_executable."

    # 3. With recovered_fallback row_kind
    candidate_recovered = dict(base_candidate)
    candidate_recovered["row_kind"] = "recovered_fallback"
    assert _is_executable(candidate_recovered) is False, "recovered_fallback row_kind must not be executable."
    
    # 4. With fallback origin
    candidate_origin = dict(base_candidate)
    candidate_origin["candidate_origin"] = "fallback_min_breadth"
    assert _is_executable(candidate_origin) is False, "fallback origin must not be executable."
