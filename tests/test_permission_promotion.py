from config import config as cfg
from core import review_queue


def _candidate(**overrides):
    row = {
        "trade_id": "T-PROMOTE",
        "symbol": "NIFTY",
        "permission": "QUEUE_ONLY",
        "permission_reason": "medium_global_conf",
        "final_action": "QUEUE_ONLY",
        "readiness": "QUEUE_ONLY",
        "execution_status": "queue_only",
        "execution_entry": 102.0,
        "execution_entry_status": "executable",
        "execution_entry_source": "last",
        "display_entry": 101.5,
        "display_entry_status": "displayable",
        "entry": 101.5,
        "entry_status": "displayable",
        "current_ltp": 102.0,
        "quote_source": "tick_store",
        "option_ltp_source": "tick_store",
        "quote_validation_status": "OK",
        "quote_age_sec": 0.5,
        "tradable": True,
        "execution_allowed": False,
        "approval_blocked": False,
        "unresolved_contract": False,
        "hard_blockers": [],
        "blockers": [],
        "confidence_final": 0.78,
        "gating_final_confidence": 0.78,
        "selected_for_execution": True,
        "rank_global": 1,
    }
    row.update(overrides)
    return row


def test_strong_queue_only_candidate_with_execution_entry_gets_promoted(tmp_path, monkeypatch):
    monkeypatch.setattr(
        cfg,
        "PERMISSION_PROMOTION_TRACE_PATH",
        str(tmp_path / "permission_promotion_trace.jsonl"),
        raising=False,
    )

    out = review_queue._maybe_promote_execute_candidate(_candidate())

    assert out["permission"] == "EXECUTE"
    assert out["final_action"] == "EXECUTE"
    assert out["readiness"] == "READY"
    assert out["execution_allowed"] is True
    assert out["execution_status"] == "executable"
    assert out["permission_promoted_from"] == "QUEUE_ONLY"
    assert out["final_action_promoted_from"] == "QUEUE_ONLY"
    assert out["promotion_reason"] == "ranked_top_candidate_promoted"


def test_moderate_queue_only_candidate_stays_queue_only():
    out = review_queue._maybe_promote_execute_candidate(
        _candidate(confidence_final=0.55, gating_final_confidence=0.55)
    )

    assert out["permission"] == "QUEUE_ONLY"
    assert out["final_action"] == "QUEUE_ONLY"
    assert out["execution_allowed"] is False
    assert out.get("promotion_reason") in (None, "")


def test_blocked_candidate_never_promotes():
    out = review_queue._maybe_promote_execute_candidate(
        _candidate(hard_blockers=["MISSING_ENTRY"], blockers=["MISSING_ENTRY"])
    )

    assert out["permission"] == "QUEUE_ONLY"
    assert out["final_action"] == "QUEUE_ONLY"
    assert out["execution_allowed"] is False
    assert out.get("promotion_reason") in (None, "")


def test_unresolved_contract_never_promotes():
    out = review_queue._maybe_promote_execute_candidate(
        _candidate(unresolved_contract=True)
    )

    assert out["permission"] == "QUEUE_ONLY"
    assert out["final_action"] == "QUEUE_ONLY"
    assert out["execution_allowed"] is False
    assert out.get("promotion_reason") in (None, "")
