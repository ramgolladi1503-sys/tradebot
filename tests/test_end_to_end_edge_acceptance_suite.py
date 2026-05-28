from __future__ import annotations

from core.end_to_end_edge_acceptance_suite import (
    EDGE_ACCEPTANCE_SUITE_BLOCKED,
    EDGE_ACCEPTANCE_SUITE_PASSED,
    EDGE_CANDIDATE_ACCEPTED,
    EDGE_CANDIDATE_REJECTED,
    REQUIRED_EDGE_ACCEPTANCE_STAGES,
    REASON_MISSING_STAGE_EVIDENCE,
    REASON_NO_CANDIDATES,
    build_end_to_end_edge_acceptance_report,
)
from core.final_executable_quality_gate import FINAL_EXECUTABLE_QUALITY_BLOCKED, FINAL_EXECUTABLE_QUALITY_PASSED
from core.strategy_replay_proof_pack import STRATEGY_REPLAY_PROOF_BLOCKED, STRATEGY_REPLAY_PROOF_PASSED


def _candidate(candidate_id: str = "cand-1", *, strategy_id: str = "breakout") -> dict:
    return {
        "candidate_id": candidate_id,
        "strategy_id": strategy_id,
        "symbol": "NIFTY",
        "direction": "LONG",
        "movement_type": "BREAKOUT",
    }


def _stage(candidate_id: str = "cand-1", *, status: str = "PASSED", **extra: object) -> dict:
    return {
        "candidate_id": candidate_id,
        "status": status,
        "passed": True,
        **extra,
    }


def _all_stage_inputs(candidate_id: str = "cand-1") -> dict:
    return {
        "candidate_intent": [_stage(candidate_id, status="VALID")],
        "candidate_pool": [_stage(candidate_id, status="PASSED")],
        "strategy_generator": [_stage(candidate_id, status="GENERATED")],
        "option_chain_confirmation": [_stage(candidate_id, status="CONFIRMED", confirmed=True)],
        "exit_model": [_stage(candidate_id, status="PASSED")],
        "conflict_consensus": [_stage(candidate_id, status="PASSED")],
        "no_trade_oracle": [_stage(candidate_id, status="PASSED", no_trade_required=False)],
        "final_quality_gate": [
            _stage(
                candidate_id,
                status=FINAL_EXECUTABLE_QUALITY_PASSED,
                executable_quality_passed=True,
            )
        ],
        "replay_proof_pack": [
            _stage(
                candidate_id,
                status=STRATEGY_REPLAY_PROOF_PASSED,
                strategy_summaries=[{"candidate_id": candidate_id, "status": "PASSED"}],
            )
        ],
    }


def test_end_to_end_edge_acceptance_accepts_candidate_when_all_proofs_pass() -> None:
    report = build_end_to_end_edge_acceptance_report([_candidate()], **_all_stage_inputs())

    assert report.status == EDGE_ACCEPTANCE_SUITE_PASSED
    assert report.candidate_count == 1
    assert report.accepted_candidate_count == 1
    assert report.rejected_candidate_count == 0
    assert report.reasons == ()

    accepted = report.candidates[0]
    assert accepted.status == EDGE_CANDIDATE_ACCEPTED
    assert accepted.accepted is True
    assert accepted.reasons == ()
    assert [stage.stage for stage in accepted.stage_evidence] == list(REQUIRED_EDGE_ACCEPTANCE_STAGES)
    assert all(stage.passed for stage in accepted.stage_evidence)

    payload = report.to_payload()
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert payload["metadata"]["does_not_rank_candidates"] is True
    assert payload["metadata"]["does_not_call_brokers"] is True


def test_end_to_end_edge_acceptance_fails_closed_when_required_stage_missing() -> None:
    inputs = _all_stage_inputs()
    inputs.pop("option_chain_confirmation")

    report = build_end_to_end_edge_acceptance_report([_candidate()], **inputs)

    assert report.status == EDGE_ACCEPTANCE_SUITE_BLOCKED
    assert report.accepted_candidate_count == 0
    assert report.rejected_candidate_count == 1
    rejected = report.candidates[0]
    assert rejected.status == EDGE_CANDIDATE_REJECTED
    assert "option_chain_confirmation:MISSING_STAGE_EVIDENCE" in rejected.reasons
    option_stage = next(stage for stage in rejected.stage_evidence if stage.stage == "option_chain_confirmation")
    assert option_stage.passed is False
    assert option_stage.reasons == (REASON_MISSING_STAGE_EVIDENCE,)


def test_end_to_end_edge_acceptance_rejects_when_no_trade_oracle_blocks() -> None:
    inputs = _all_stage_inputs()
    inputs["no_trade_oracle"] = [
        _stage(
            "cand-1",
            status="NO_TRADE_REQUIRED",
            passed=False,
            no_trade_required=True,
            primary_reason="MARKET_CLOSED",
        )
    ]

    report = build_end_to_end_edge_acceptance_report([_candidate()], **inputs)

    assert report.status == EDGE_ACCEPTANCE_SUITE_BLOCKED
    assert report.accepted_candidate_count == 0
    assert report.rejected_candidate_count == 1
    assert "no_trade_oracle:MARKET_CLOSED" in report.candidates[0].reasons


def test_end_to_end_edge_acceptance_rejects_when_final_quality_blocks() -> None:
    inputs = _all_stage_inputs()
    inputs["final_quality_gate"] = [
        _stage(
            "cand-1",
            status=FINAL_EXECUTABLE_QUALITY_BLOCKED,
            passed=False,
            executable_quality_passed=False,
            primary_reason="missing_executable_truth_evidence",
        )
    ]

    report = build_end_to_end_edge_acceptance_report([_candidate()], **inputs)

    assert report.status == EDGE_ACCEPTANCE_SUITE_BLOCKED
    assert "final_quality_gate:missing_executable_truth_evidence" in report.candidates[0].reasons


def test_end_to_end_edge_acceptance_rejects_when_replay_proof_pack_blocks() -> None:
    inputs = _all_stage_inputs()
    inputs["replay_proof_pack"] = [
        _stage(
            "cand-1",
            status=STRATEGY_REPLAY_PROOF_BLOCKED,
            passed=False,
            reasons=["feed_fault:WEBSOCKET_DISCONNECTED"],
        )
    ]

    report = build_end_to_end_edge_acceptance_report([_candidate()], **inputs)

    assert report.status == EDGE_ACCEPTANCE_SUITE_BLOCKED
    assert "replay_proof_pack:feed_fault:WEBSOCKET_DISCONNECTED" in report.candidates[0].reasons


def test_end_to_end_edge_acceptance_groups_candidates_deterministically() -> None:
    candidate_a = _candidate("cand-a", strategy_id="breakout")
    candidate_b = _candidate("cand-b", strategy_id="vwap")
    inputs = _all_stage_inputs("cand-a")
    for stage_name, values in _all_stage_inputs("cand-b").items():
        inputs[stage_name].extend(values)

    report = build_end_to_end_edge_acceptance_report([candidate_b, candidate_a], **inputs)

    assert report.status == EDGE_ACCEPTANCE_SUITE_PASSED
    assert [candidate.candidate_id for candidate in report.candidates] == ["cand-a", "cand-b"]
    assert report.accepted_candidate_count == 2
    assert report.rejected_candidate_count == 0


def test_end_to_end_edge_acceptance_fails_closed_without_candidates() -> None:
    report = build_end_to_end_edge_acceptance_report([], **_all_stage_inputs())

    assert report.status == EDGE_ACCEPTANCE_SUITE_BLOCKED
    assert report.candidate_count == 0
    assert report.accepted_candidate_count == 0
    assert report.rejected_candidate_count == 0
    assert report.reasons == (REASON_NO_CANDIDATES,)


def test_end_to_end_edge_acceptance_rejects_action_or_broker_evidence() -> None:
    inputs = _all_stage_inputs()
    inputs["candidate_intent"] = [_stage("cand-1", status="PASSED", is_order_action=True)]
    inputs["candidate_pool"] = [_stage("cand-1", status="PASSED", broker_api_called=True)]

    report = build_end_to_end_edge_acceptance_report([_candidate()], **inputs)

    assert report.status == EDGE_ACCEPTANCE_SUITE_BLOCKED
    assert "candidate_intent:ORDER_ACTION_EVIDENCE_NOT_ALLOWED" in report.candidates[0].reasons
    assert "candidate_pool:BROKER_API_CALL_EVIDENCE_NOT_ALLOWED" in report.candidates[0].reasons
