from core import review_queue


def test_execute_row_remains_execute():
    entry = {
        "trade_id": "T-PERSIST-EXEC",
        "symbol": "NIFTY",
        "permission": "EXECUTE",
        "permission_reason": "engine_decision",
        "readiness": "READY",
        "final_action": "EXECUTE",
        "execution_status": "executable",
        "execution_entry": 121.5,
        "execution_entry_status": "executable",
        "display_entry": 121.5,
        "display_entry_status": "displayable",
        "entry_status": "displayable",
        "blockers": [],
        "hard_blockers": [],
        "soft_penalties": [],
        "warnings": [],
    }
    out = review_queue._finalize_review_queue_entry(
        entry,
        mode_for_entry="LIVE",
        allow_stale_quotes_for_entry=False,
        market_open_for_entry=True,
    )
    assert out["permission"] == "EXECUTE"
    assert out["readiness"] == "READY"
    assert out["final_action"] == "EXECUTE"
    assert out["execution_status"] == "executable"
    assert out["decision_parity"]["ok"] is True


def test_advisory_row_preserves_display_entry_and_blockers():
    entry = {
        "trade_id": "T-PERSIST-ADVISORY",
        "symbol": "NIFTY",
        "permission": "ADVISORY_ONLY",
        "permission_reason": "engine_decision",
        "readiness": "ADVISORY_ONLY",
        "final_action": "ADVISORY_ONLY",
        "execution_status": "advisory_only",
        "execution_entry": None,
        "execution_entry_status": "non_executable",
        "display_entry": 88.0,
        "display_entry_status": "displayable",
        "entry_status": "displayable",
        "blockers": ["SOFT_SPREAD_WARN"],
        "hard_blockers": [],
        "soft_penalties": ["SPREAD_PCT_HIGH"],
        "warnings": ["STALE_OPTION_LTP"],
    }
    out = review_queue._finalize_review_queue_entry(
        entry,
        mode_for_entry="LIVE",
        allow_stale_quotes_for_entry=False,
        market_open_for_entry=True,
    )
    assert out["permission"] == "ADVISORY_ONLY"
    assert out["readiness"] == "ADVISORY_ONLY"
    assert out["final_action"] == "ADVISORY_ONLY"
    assert out["execution_status"] == "advisory_only"
    assert "MISSING_ENTRY" not in (out.get("blockers") or [])
    assert out.get("blockers") == ["SOFT_SPREAD_WARN"]
    assert out.get("hard_blockers") == []
    assert out.get("soft_penalties") == ["SPREAD_PCT_HIGH"]
    assert out.get("warnings") == ["STALE_OPTION_LTP"]
    assert out["decision_parity"]["ok"] is True
