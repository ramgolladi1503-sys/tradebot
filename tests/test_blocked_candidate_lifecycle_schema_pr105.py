from __future__ import annotations

from core.review_queue import _normalize_blocked_candidate_lifecycle_schema


def test_blocked_readiness_gets_non_empty_hard_blockers_from_soft_penalty():
    out = _normalize_blocked_candidate_lifecycle_schema(
        {
            "trade_id": "t1",
            "symbol": "NIFTY",
            "readiness": "BLOCKED",
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "execution_status": "queue_only",
            "candidate_status": "blocked",
            "execution_allowed": False,
            "hard_blockers": [],
            "blockers": [],
            "soft_penalties": ["PRICE_MISMATCH"],
        }
    )

    assert out["readiness"] == "BLOCKED"
    assert out["hard_blockers"] == ["PRICE_MISMATCH"]
    assert "PRICE_MISMATCH" in out["blockers"]
    assert out["permission_reason"] == "PRICE_MISMATCH"
    assert out["execution_allowed"] is False


def test_final_block_forces_permission_block_and_hard_blocker():
    out = _normalize_blocked_candidate_lifecycle_schema(
        {
            "trade_id": "t2",
            "symbol": "SENSEX",
            "readiness": "QUEUE_ONLY",
            "permission": "QUEUE_ONLY",
            "final_action": "BLOCK",
            "execution_status": "queue_only",
            "candidate_status": "advisory_only",
            "execution_allowed": True,
            "hard_blockers": [],
            "blockers": [],
            "soft_penalties": [],
            "permission_reason": "medium_global_conf",
        }
    )

    assert out["readiness"] == "BLOCKED"
    assert out["permission"] == "BLOCK"
    assert out["final_action"] == "BLOCK"
    assert out["execution_status"] == "blocked"
    assert out["candidate_status"] == "blocked"
    assert out["execution_allowed"] is False
    assert out["eligible_for_execution"] is False
    assert out["hard_blockers"] == ["MEDIUM_GLOBAL_CONF"]


def test_stale_option_ltp_blocked_emit_gets_schema_blocker():
    out = _normalize_blocked_candidate_lifecycle_schema(
        {
            "trade_id": "t3",
            "symbol": "NIFTY",
            "readiness": "BLOCKED",
            "permission": "BLOCK",
            "final_action": "BLOCK",
            "execution_status": "blocked",
            "candidate_status": "blocked",
            "execution_allowed": False,
            "hard_blockers": [],
            "blockers": ["STALE_OPTION_LTP"],
            "soft_penalties": [],
        }
    )

    assert out["hard_blockers"] == ["STALE_OPTION_LTP"]
    assert "STALE_OPTION_LTP" in out["blockers"]


def test_queue_only_medium_conf_without_block_stays_queue_only():
    out = _normalize_blocked_candidate_lifecycle_schema(
        {
            "trade_id": "t4",
            "symbol": "BANKNIFTY",
            "readiness": "QUEUE_ONLY",
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "execution_status": "queue_only",
            "candidate_status": "advisory_only",
            "execution_allowed": False,
            "hard_blockers": [],
            "blockers": [],
            "soft_penalties": [],
            "permission_reason": "medium_global_conf",
        }
    )

    assert out["readiness"] == "QUEUE_ONLY"
    assert out["permission"] == "QUEUE_ONLY"
    assert out["final_action"] == "QUEUE_ONLY"
    assert out["hard_blockers"] == []


def test_review_queue_normalizes_blocked_lifecycle_before_serialization():
    source = open("core/review_queue.py", "r", encoding="utf-8").read()

    assert "def _normalize_blocked_candidate_lifecycle_schema(" in source
    assert (
        "advisory_payload = _normalize_blocked_candidate_lifecycle_schema(advisory_payload)\n"
        "    _print_final_emit_truth(advisory_payload)"
    ) in source

def test_blocked_contract_lifecycle_is_preserved():
    out = _normalize_blocked_candidate_lifecycle_schema(
        {
            "trade_id": "t5",
            "symbol": "NIFTY",
            "readiness": "BLOCKED",
            "permission": "BLOCK",
            "final_action": "BLOCK",
            "execution_status": "blocked",
            "candidate_status": "blocked_contract",
            "execution_allowed": False,
            "hard_blockers": [],
            "blockers": ["UNRESOLVED_CONTRACT"],
            "soft_penalties": [],
            "reason": "unresolved_contract",
        }
    )

    assert out["readiness"] == "BLOCKED"
    assert out["permission"] == "BLOCK"
    assert out["final_action"] == "BLOCK"
    assert out["execution_status"] == "blocked"
    assert out["candidate_status"] == "blocked_contract"
    assert out["hard_blockers"] == ["UNRESOLVED_CONTRACT"]
    assert out["execution_allowed"] is False

