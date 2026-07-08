from core.canonical_ranked_ui_adapter import adapt_candidate_rank_record_to_ui

def test_fallback_quote_is_advisory_in_ui():
    record = {
        "ranked_report_id": "test-123",
        "executable_candidate": True,
        "safety_flags": ["fallback_used"]
    }
    
    ui_record = adapt_candidate_rank_record_to_ui(record)
    
    # Even if upstream claimed executable_candidate = True, if fallback_used is in safety_flags, it MUST be advisory
    assert ui_record["advisory_only"] is True

def test_non_executable_candidate_is_advisory():
    record = {
        "ranked_report_id": "test-123",
        "executable_candidate": False,
        "safety_flags": []
    }
    
    ui_record = adapt_candidate_rank_record_to_ui(record)
    assert ui_record["advisory_only"] is True

def test_executable_candidate_is_not_advisory():
    record = {
        "ranked_report_id": "test-123",
        "executable_candidate": True,
        "safety_flags": []
    }
    
    ui_record = adapt_candidate_rank_record_to_ui(record)
    assert ui_record["advisory_only"] is False
