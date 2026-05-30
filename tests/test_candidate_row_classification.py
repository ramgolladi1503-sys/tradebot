from __future__ import annotations

from core.candidate_row_classification import classify_candidate_row


def test_executable_class_requires_execution_ok_and_not_fallback():
    cls = classify_candidate_row(
        row={"execution_ok": True, "quote_source": "option_chain_live"},
        phase2_state="ENTER",
        cycle_primary_reason=None,
    )
    assert cls.row_class == "EXECUTABLE"
    assert cls.is_executable is True

    cls2 = classify_candidate_row(
        row={"execution_ok": True, "quote_source": "option_chain_live", "source_flags": {"recovered_fallback": True}},
        phase2_state="ENTER",
        cycle_primary_reason=None,
    )
    assert cls2.row_class != "EXECUTABLE"


def test_feed_stale_and_unresolved_contract_are_debug_rejected():
    cls = classify_candidate_row(
        row={"hard_blockers": ["FEED_STALE"], "execution_ok": True},
        phase2_state="WATCHLIST",
        cycle_primary_reason=None,
    )
    assert cls.row_class == "DEBUG_REJECTED"
    assert cls.is_debug is True

    cls2 = classify_candidate_row(
        row={"hard_blockers": ["UNRESOLVED_CONTRACT"], "execution_ok": True},
        phase2_state="WATCHLIST",
        cycle_primary_reason=None,
    )
    assert cls2.row_class == "DEBUG_REJECTED"


def test_market_closed_cycle_marks_market_closed_class():
    cls = classify_candidate_row(
        row={"execution_ok": True},
        phase2_state="NO_TRADE",
        cycle_primary_reason="market_closed",
    )
    assert cls.row_class == "MARKET_CLOSED_NO_TRADE"

