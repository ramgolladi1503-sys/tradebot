from core import review_queue


def test_recovered_fallback_entry_never_executable():
    entry = {
        "trade_id": "T-FALLBACK-EXEC",
        "symbol": "NIFTY",
        "execution_entry": 125.0,
        "execution_entry_source": "recovered_fallback",
        "execution_entry_status": "executable",
        "display_entry": 125.0,
        "display_entry_source": "recovered_fallback",
        "display_entry_status": "displayable",
        "entry": 125.0,
        "entry_status": "displayable",
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "readiness": "READY",
    }
    out = review_queue._enforce_executable_entry_invariant(entry)
    assert out.get("execution_entry_status") == "non_executable"
    out = review_queue._refresh_opportunity_survival_state(out)
    assert out.get("execution_allowed") is False
    assert out.get("execution_status") != "executable"
