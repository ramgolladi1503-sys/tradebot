import pytest
from core.review_queue import _downgrade_execution_intent, _maybe_promote_execute_candidate

def test_stale_execute_downgrade():
    out = {
        "final_action": "EXECUTE",
        "permission": "EXECUTE",
        "execution_allowed": True,
        "eligible_for_execution": True,
        "is_executable": True
    }
    _downgrade_execution_intent(out, "REJECT", "poor_liquidity")
    assert out["final_action"] == "REJECT"
    assert out["execution_allowed"] is False
    assert out["eligible_for_execution"] is False
    assert out["is_executable"] is False
    assert out["promotion_block_reason"] == "poor_liquidity"

def test_queue_only_downgrade():
    out = {
        "final_action": "EXECUTE",
        "permission": "EXECUTE",
        "execution_allowed": True,
        "eligible_for_execution": True,
        "is_executable": True
    }
    _downgrade_execution_intent(out, "QUEUE_ONLY", "queue_fallback")
    assert out["final_action"] == "QUEUE_ONLY"
    assert out["execution_allowed"] is False
    assert out["eligible_for_execution"] is False
    assert out["is_executable"] is False
    assert out["promotion_block_reason"] == "queue_fallback"

def test_regression_old_bug_shape_execution_ok_false():
    # If final_action is EXECUTE but downstream execution_ok is False, it MUST downgrade.
    out = {
        "final_action": "EXECUTE",
        "permission": "EXECUTE",
        "execution_allowed": True,
        "eligible_for_execution": True,
        "is_executable": True,
        "execution_ok": False,
        "readiness": "READY",
        "execution_entry": 100.0,
        "execution_entry_status": "executable",
        "tradable": True
    }
    
    res = _maybe_promote_execute_candidate(out)
    assert res["final_action"] == "REJECT"
    assert res["permission"] == "REJECT"
    assert res["execution_allowed"] is False
    assert res["eligible_for_execution"] is False
    assert res["is_executable"] is False
    assert res["promotion_block_reason"] == "execution_ok_false"

def test_regression_old_bug_shape_order_policy_reject():
    # If order_policy is reject, it MUST downgrade.
    out = {
        "final_action": "EXECUTE",
        "permission": "EXECUTE",
        "execution_allowed": True,
        "eligible_for_execution": True,
        "is_executable": True,
        "execution_ok": True,
        "order_policy": "reject",
        "readiness": "READY",
        "execution_entry": 100.0,
        "execution_entry_status": "executable",
        "tradable": True
    }
    
    res = _maybe_promote_execute_candidate(out)
    assert res["final_action"] == "REJECT"
    assert res["permission"] == "REJECT"
    assert res["execution_allowed"] is False
    assert res["eligible_for_execution"] is False
    assert res["is_executable"] is False
    assert res["promotion_block_reason"] == "order_policy_reject"

def test_regression_old_bug_shape_decision_action_reject():
    # If decision_action is REJECT (e.g. decision engine ran before final_action became EXECUTE?), downgrade
    out = {
        "final_action": "EXECUTE",
        "permission": "EXECUTE",
        "execution_allowed": True,
        "eligible_for_execution": True,
        "is_executable": True,
        "execution_ok": True,
        "decision_action": "REJECT",
        "readiness": "READY",
        "execution_entry": 100.0,
        "execution_entry_status": "executable",
        "tradable": True
    }
    
    res = _maybe_promote_execute_candidate(out)
    assert res["final_action"] == "REJECT"
    assert res["permission"] == "REJECT"
    assert res["execution_allowed"] is False
    assert res["eligible_for_execution"] is False
    assert res["is_executable"] is False
    assert res["promotion_block_reason"] == "decision_engine_reject"

