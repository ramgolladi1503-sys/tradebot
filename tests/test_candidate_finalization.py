from __future__ import annotations

from datetime import datetime

import pytest

from core.candidate_finalization import (
    assert_executable_candidate_ready,
    assert_ranked_candidate_ready,
    mirror_candidate_truth,
)
from core.trade_schema import Trade


def _trade(**overrides) -> Trade:
    base = dict(
        trade_id="T-FINALIZE",
        timestamp=datetime(2026, 4, 21, 10, 0, 0),
        symbol="NIFTY",
        instrument="OPT",
        instrument_token=12345,
        strike=24450,
        expiry="2026-04-21",
        side="BUY",
        entry_price=150.0,
        stop_loss=140.0,
        target=170.0,
        qty=1,
        capital_at_risk=10.0,
        expected_slippage=0.2,
        confidence=0.72,
        strategy="UNIT",
        regime="TREND",
        candidate_status="executable",
        permission="QUEUE_ONLY",
        execution_allowed=True,
        execution_entry=150.0,
        execution_entry_status="executable",
        execution_entry_source="ask",
        display_entry=150.0,
        display_entry_status="displayable",
        display_entry_source="ask",
        tradable=True,
        source_flags={},
    )
    base.update(overrides)
    return Trade(**base)


def test_mirror_candidate_truth_promotes_decision_and_contract_metadata():
    candidate = {
        "trade_id": "T-DICT",
        "symbol": "BANKNIFTY",
        "strategy_family": "breakout",
        "candidate_status": "executable",
        "confidence": 0.81,
        "source_flags": {},
    }
    decision_trace = {
        "rank_score": 0.67,
        "permission": "EXECUTE",
        "permission_reason": "ok",
        "final_action": "EXECUTE",
        "readiness": "READY",
        "execution_status": "executable",
        "execution_allowed": True,
        "execution_entry_status": "executable",
        "gates_failed": [],
        "warnings": ["quote_ok"],
    }
    lifecycle = {
        "execution_entry": 585.95,
        "execution_entry_source": "ask",
        "execution_entry_status": "executable",
        "display_entry": 585.95,
        "display_entry_source": "ask",
        "display_entry_status": "displayable",
        "entry": 585.95,
        "entry_source": "ask",
        "entry_status": "displayable",
        "entry_reason": "execution_from_ask",
        "entry_clear_reason": None,
        "entry_block_code": None,
    }
    contract_resolution = {
        "requested_strike": 57500.0,
        "resolved_strike": 57500.0,
        "requested_expiry": "2026-04-28",
        "resolved_expiry": "2026-04-28",
        "contract_exact_match": True,
        "resolution_mode": "exact",
        "resolution_penalty": 0.0,
        "fallback_used": False,
        "fallback_class": None,
        "fallback_reason": None,
        "fallback_execution_policy": "EXECUTE",
        "tradingsymbol": "BANKNIFTY26APR57500CE",
        "instrument_token": 900001,
        "instrument_id": "BANKNIFTY|2026-04-28|57500|CE",
    }

    out = mirror_candidate_truth(
        candidate,
        decision_trace=decision_trace,
        lifecycle=lifecycle,
        contract_resolution=contract_resolution,
        fallback_metadata=contract_resolution,
        lifecycle_stage="decision_finalized",
    )

    assert out["rank_score"] == 0.67
    assert out["permission"] == "EXECUTE"
    assert out["final_action"] == "EXECUTE"
    assert out["readiness"] == "READY"
    assert out["execution_status"] == "executable"
    assert out["execution_allowed"] is True
    assert out["execution_entry_status"] == "executable"
    assert out["lifecycle_stage"] == "decision_finalized"
    assert out["requested_strike"] == 57500.0
    assert out["resolved_strike"] == 57500.0
    assert out["contract_exact_match"] is True
    assert out["resolution_mode"] == "exact"
    assert out["fallback_used"] is False
    assert out["fallback_execution_policy"] == "EXECUTE"
    assert out["decision_trace"]["rank_score"] == 0.67


def test_mirror_candidate_truth_preserves_trade_dataclass_fields():
    trade = _trade()
    out = mirror_candidate_truth(
        trade,
        decision_trace={
            "rank_score": 0.74,
            "permission": "EXECUTE",
            "permission_reason": "ok",
            "final_action": "EXECUTE",
            "readiness": "READY",
            "execution_status": "executable",
            "execution_allowed": True,
            "execution_entry_status": "executable",
            "gates_failed": [],
            "warnings": [],
        },
        lifecycle={
            "execution_entry": 150.0,
            "execution_entry_source": "ask",
            "execution_entry_status": "executable",
            "display_entry": 150.0,
            "display_entry_source": "ask",
            "display_entry_status": "displayable",
            "entry": 150.0,
            "entry_source": "ask",
            "entry_status": "displayable",
            "entry_reason": "execution_from_ask",
            "entry_clear_reason": None,
            "entry_block_code": None,
        },
        lifecycle_stage="decision_finalized",
    )

    assert out.rank_score == 0.74
    assert out.permission == "EXECUTE"
    assert out.final_action == "EXECUTE"
    assert out.readiness == "READY"
    assert out.execution_status == "executable"
    assert out.gates_failed == []
    assert out.warnings == []
    assert out.lifecycle_stage == "decision_finalized"
    assert out.decision_trace["rank_score"] == 0.74


def test_ranked_candidate_assertion_rejects_missing_rank_score():
    with pytest.raises(AssertionError, match="ranked candidate missing required fields: rank_score"):
        assert_ranked_candidate_ready(
            {
                "trade_id": "T-RANKED-MISSING",
                "symbol": "NIFTY",
                "strategy_family": "breakout",
                "candidate_status": "executable",
                "confidence": 0.7,
            }
        )


def test_executable_candidate_assertion_rejects_missing_final_action():
    with pytest.raises(AssertionError, match="executable candidate missing required fields: final_action"):
        assert_executable_candidate_ready(
            {
                "trade_id": "T-EXEC-MISSING",
                "symbol": "NIFTY",
                "strategy_family": "breakout",
                "candidate_status": "executable",
                "confidence": 0.7,
                "rank_score": 0.65,
                "permission": "EXECUTE",
                "execution_allowed": True,
                "execution_entry_status": "executable",
            }
        )
