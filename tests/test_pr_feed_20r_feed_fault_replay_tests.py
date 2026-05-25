from __future__ import annotations

import json

from core.feed_health_truth import classify_feed_health_truth
from core.feed_hold_gate import FEED_HOLD_BLOCKER, apply_feed_hold_to_ranking, classify_feed_hold
from core.feed_policy import LIVE_FEED_POLICY, PAPER_FEED_POLICY
from core.feed_runtime_evidence import build_feed_runtime_evidence_bundle
from core.opportunity_scoring import (
    SCORE_ELIGIBLE,
    OpportunityScoreBreakdown,
    OpportunityScoreRecord,
    OpportunityScoreReport,
)


def _payload(
    *,
    feed_ok: bool = True,
    ws_connected=True,
    feed_state: str = "LIVE",
    runtime_state: str = "RUNNING",
    option_block_reason: str = "OK",
    option_age: float = 0.5,
    ltp_age: float = 0.5,
    depth_age: float = 1.0,
):
    return {
        "feed_ok": feed_ok,
        "effective_ws_connected": ws_connected,
        "runtime_state": runtime_state,
        "state_machine": {"state": feed_state, "runtime_state": runtime_state},
        "last_tick_age_sec": ltp_age,
        "last_depth_age_sec": depth_age,
        "option_feed_block_reason_by_symbol": {"NIFTY": option_block_reason},
        "option_last_tick_age_by_symbol": {"NIFTY": option_age},
    }


def _breakdown(final_score: float = 0.9) -> OpportunityScoreBreakdown:
    return OpportunityScoreBreakdown(
        component_scores={},
        component_weights={},
        weighted_component_scores={},
        base_score=final_score,
        penalties={},
        total_penalty=0.0,
        bucket_cap=1.0,
        trap_risk_penalty=0.0,
        final_score=final_score,
    )


def _score(strategy_id: str = "replay_candidate", final_score: float = 0.9) -> OpportunityScoreRecord:
    return OpportunityScoreRecord(
        strategy_id=strategy_id,
        symbol="NIFTY",
        direction="BUY_CALL",
        movement_type="COMPRESSION_BREAKOUT",
        bucket="EXECUTABLE_CANDIDATE",
        score_eligibility=SCORE_ELIGIBLE,
        final_score=final_score,
        executable_candidate=True,
        score_explanation="feed replay candidate",
        downgrade_reasons=(),
        safety_flags=(),
        blockers=(),
        warnings=(),
        breakdown=_breakdown(final_score),
    )


def _score_report() -> OpportunityScoreReport:
    scores = (_score(),)
    return OpportunityScoreReport(
        schema_version=1,
        read_only=True,
        is_order_action=False,
        append=False,
        score_count=len(scores),
        score_eligible_count=len(scores),
        needs_confirmation_count=0,
        advisory_count=0,
        suppressed_count=0,
        no_trade_count=0,
        scores=scores,
        blockers=(),
        warnings=(),
        safety_flags=(),
        metadata={"scorer": "feed_fault_replay_test"},
    )


def _paper_truth(payload):
    return classify_feed_health_truth(
        payload,
        symbols=("NIFTY",),
        max_option_tick_age_sec=5.0,
        max_ltp_age_sec=5.0,
        max_depth_age_sec=10.0,
    )


def _live_truth(payload):
    return classify_feed_health_truth(
        payload,
        symbols=("NIFTY",),
        max_option_tick_age_sec=2.0,
        max_ltp_age_sec=2.0,
        max_depth_age_sec=4.0,
    )


def test_feed_fault_replay_healthy_to_stale_to_recovered_preserves_hold_state_transitions():
    score_report = _score_report()
    frames = [
        ("healthy", _payload()),
        ("stale", _payload(option_age=8.0, ltp_age=8.0, depth_age=12.0)),
        ("recovered", _payload(option_age=0.4, ltp_age=0.4, depth_age=0.8)),
    ]

    replay = []
    for label, payload in frames:
        bundle = build_feed_runtime_evidence_bundle(payload, mode="PAPER", symbols=("NIFTY",), cycle_id=label)
        truth = _paper_truth(payload)
        hold = classify_feed_hold(truth)
        ranking = apply_feed_hold_to_ranking(score_report, truth)
        replay.append((label, bundle, hold, ranking))

    assert [item[0] for item in replay] == ["healthy", "stale", "recovered"]
    assert [item[1].feed_ok for item in replay] == [True, False, True]
    assert [item[2].hold_active for item in replay] == [False, True, False]
    assert [item[3].executable_count for item in replay] == [1, 0, 1]
    assert replay[1][3].rank_count == 0
    assert FEED_HOLD_BLOCKER in replay[1][3].blockers
    assert replay[2][3].ranks[0].strategy_id == "replay_candidate"


def test_feed_fault_replay_websocket_disconnect_blocks_until_reconnected():
    score_report = _score_report()
    disconnected = _payload(ws_connected=False)
    reconnected = _payload(ws_connected=True)

    disconnected_bundle = build_feed_runtime_evidence_bundle(disconnected, mode="PAPER", symbols=("NIFTY",))
    disconnected_ranking = apply_feed_hold_to_ranking(score_report, _paper_truth(disconnected))
    reconnected_bundle = build_feed_runtime_evidence_bundle(reconnected, mode="PAPER", symbols=("NIFTY",))
    reconnected_ranking = apply_feed_hold_to_ranking(score_report, _paper_truth(reconnected))

    assert disconnected_bundle.feed_ok is False
    assert "websocket_disconnected" in disconnected_bundle.reasons
    assert disconnected_ranking.executable_count == 0
    assert FEED_HOLD_BLOCKER in disconnected_ranking.blockers
    assert reconnected_bundle.feed_ok is True
    assert reconnected_ranking.executable_count == 1


def test_feed_fault_replay_subscription_failed_blocks_symbol_level_feed():
    payload = _payload(option_block_reason="SUBSCRIPTION_FAILED", option_age=0.2)

    bundle = build_feed_runtime_evidence_bundle(payload, mode="PAPER", symbols=("NIFTY",))
    truth = _paper_truth(payload)
    hold = classify_feed_hold(truth)
    ranking = apply_feed_hold_to_ranking(_score_report(), truth)

    assert bundle.feed_ok is False
    assert "NIFTY:option_feed_blocked" in bundle.reasons
    assert truth.symbols[0].option_feed_block_reason == "subscription_failed"
    assert hold.hold_active is True
    assert ranking.rank_count == 0
    assert ranking.executable_count == 0


def test_feed_fault_replay_same_payload_can_pass_paper_and_fail_live():
    payload = _payload(option_age=3.0, ltp_age=3.0, depth_age=6.0)

    paper_bundle = build_feed_runtime_evidence_bundle(payload, mode="PAPER", symbols=("NIFTY",))
    live_bundle = build_feed_runtime_evidence_bundle(payload, mode="LIVE", symbols=("NIFTY",))
    paper_ranking = apply_feed_hold_to_ranking(_score_report(), _paper_truth(payload))
    live_ranking = apply_feed_hold_to_ranking(_score_report(), _live_truth(payload))

    assert paper_bundle.feed_policy_decision["policy_name"] == PAPER_FEED_POLICY
    assert paper_bundle.feed_ok is True
    assert paper_ranking.executable_count == 1
    assert live_bundle.feed_policy_decision["policy_name"] == LIVE_FEED_POLICY
    assert live_bundle.feed_ok is False
    assert "ltp_ticks_stale" in live_bundle.reasons
    assert "NIFTY:option_ticks_stale" in live_bundle.reasons
    assert live_ranking.executable_count == 0
    assert FEED_HOLD_BLOCKER in live_ranking.blockers


def test_feed_fault_replay_evidence_is_json_serializable_and_non_action():
    payload = _payload(option_age=8.0, ltp_age=8.0, depth_age=12.0)
    bundle = build_feed_runtime_evidence_bundle(payload, mode="PAPER", symbols=("NIFTY",), cycle_id="stale-frame")
    ranking = apply_feed_hold_to_ranking(_score_report(), _paper_truth(payload))

    bundle_payload = json.loads(bundle.to_json())
    ranking_payload = ranking.to_dict()

    assert bundle_payload["read_only"] is True
    assert bundle_payload["append"] is False
    assert bundle_payload["is_order_action"] is False
    assert bundle_payload["broker_api_called"] is False
    assert bundle_payload["metadata"]["cycle_id"] == "stale-frame"
    assert ranking_payload["read_only"] is True
    assert ranking_payload["append"] is False
    assert ranking_payload["is_order_action"] is False
    assert ranking_payload["metadata"]["feed_hold_active"] is True
