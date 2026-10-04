from __future__ import annotations

import json
import time

from core.feed_health_truth import classify_feed_health_truth
from core.feed_hold_gate import FEED_HOLD_BLOCKER, apply_feed_hold_to_ranking, classify_feed_hold
from core.opportunity_scoring import SCORE_ELIGIBLE, OpportunityScoreBreakdown, OpportunityScoreRecord, OpportunityScoreReport

# stale_feed safety regression coverage: unsafe feed truth cannot produce executable rankings.


def _breakdown(final_score: float = 0.7) -> OpportunityScoreBreakdown:
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


def _score(strategy_id: str = "s1", final_score: float = 0.7, *, symbol: str = "NIFTY") -> OpportunityScoreRecord:
    return OpportunityScoreRecord(
        strategy_id=strategy_id,
        symbol=symbol,
        direction="BUY_CALL",
        movement_type="COMPRESSION_BREAKOUT",
        bucket="EXECUTABLE_CANDIDATE",
        score_eligibility=SCORE_ELIGIBLE,
        final_score=final_score,
        executable_candidate=True,
        score_explanation="unit",
        downgrade_reasons=(),
        safety_flags=(),
        blockers=(),
        warnings=(),
        breakdown=_breakdown(final_score),
    )


def _report(scores: list[OpportunityScoreRecord]) -> OpportunityScoreReport:
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
        scores=tuple(scores),
        blockers=(),
        warnings=(),
        safety_flags=(),
        metadata={"scorer": "opportunity_score_v1"},
    )


def _healthy_feed():
    return classify_feed_health_truth(
        {
            "feed_ok": True,
            "effective_ws_connected": True,
            "runtime_state": "RUNNING",
            "state_machine": {"state": "LIVE"},
            "last_tick_age_sec": 0.4,
            "last_depth_age_sec": 1.0,
            "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
            "option_last_tick_age_by_symbol": {"NIFTY": 0.2},
        },
        symbols=("NIFTY",),
        max_ltp_age_sec=2.5,
        max_depth_age_sec=6.0,
    )


def _unhealthy_feed():
    return classify_feed_health_truth(
        {
            "feed_ok": True,
            "effective_ws_connected": False,
            "runtime_state": "RUNNING",
            "state_machine": {"state": "DOWN"},
            "last_tick_age_sec": 0.4,
            "last_depth_age_sec": 1.0,
            "option_feed_block_reason_by_symbol": {"NIFTY": "SUBSCRIPTION_FAILED"},
            "option_last_tick_age_by_symbol": {"NIFTY": 0.2},
        },
        symbols=("NIFTY",),
        max_ltp_age_sec=2.5,
        max_depth_age_sec=6.0,
    )


def test_stale_feed_hold_decision_is_read_only_and_non_action():
    hold = classify_feed_hold(_unhealthy_feed())

    assert hold.read_only is True
    assert hold.is_order_action is False
    assert hold.append is False
    assert hold.hold_active is True
    assert FEED_HOLD_BLOCKER in hold.blockers
    assert hold.feed_health_truth["feed_ok"] is False


def test_stale_feed_unhealthy_feed_truth_suppresses_all_executable_ranks():
    score_report = _report([_score("a", 0.9), _score("b", 0.8)])

    ranking = apply_feed_hold_to_ranking(score_report, _unhealthy_feed())

    assert ranking.read_only is True
    assert ranking.is_order_action is False
    assert ranking.append is False
    assert ranking.rank_count == 0
    assert ranking.executable_count == 0
    assert ranking.ranks == ()
    assert FEED_HOLD_BLOCKER in ranking.blockers
    assert ranking.safety_flags == (FEED_HOLD_BLOCKER,)
    assert ranking.metadata["feed_hold_active"] is True
    assert ranking.metadata["source_score_count"] == 2


def test_stale_feed_healthy_feed_truth_preserves_normal_ranking_order():
    score_report = _report([_score("low", 0.5), _score("high", 0.9)])

    ranking = apply_feed_hold_to_ranking(score_report, _healthy_feed())

    assert ranking.rank_count == 2
    assert ranking.executable_count == 2
    assert [rank.strategy_id for rank in ranking.ranks] == ["high", "low"]
    assert FEED_HOLD_BLOCKER not in ranking.blockers


def _mixed_symbol_feed(
    *, ws_connected=True, global_blocked=False, missing_target=False,
    runtime_state="RUNNING", feed_state="LIVE", last_depth_age=1.0,
):
    observed_epoch = time.time()
    session_identity = {
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "feed_session_id": "session-test",
        "feed_epoch": 9,
        "reconnect_generation": 3,
        "observed_epoch": observed_epoch,
    }
    underlying_by_symbol = {
        symbol: {
            "status": "HEALTHY",
            "symbol": symbol,
            "identity_domain": "INDEX_SPOT",
            "instrument_token": token,
            "feed_session_id": "session-test",
            "feed_epoch": 9,
            "reconnect_generation": 3,
            "active_subscription": True,
            "subscription_succeeded": True,
            "receipt_epoch": observed_epoch - 0.3,
            "age_sec": 0.3,
            "max_age_sec": 2.5,
            "generated_epoch": observed_epoch,
        }
        for symbol, token in (("NIFTY", 256265), ("BANKNIFTY", 260105))
    }
    payload = {
        "ts_epoch": observed_epoch,
        "feed_session_identity": session_identity,
        "underlying_feed_identity_by_symbol": underlying_by_symbol,
        "feed_ok": False,
        "feed_ok_scope": "symbol_aggregate",
        "global_feed_blocked": global_blocked,
        "effective_ws_connected": ws_connected,
        "runtime_state": runtime_state,
        "state_machine": {"state": feed_state},
        "last_tick_age_sec": 0.4,
        "last_depth_age_sec": last_depth_age,
        "option_feed_block_reason_by_symbol": {"BANKNIFTY": "SUBSCRIPTION_FAILED"},
        "option_last_tick_age_by_symbol": {"BANKNIFTY": 0.2},
    }
    if not missing_target:
        payload["option_feed_block_reason_by_symbol"]["NIFTY"] = "OK"
        payload["option_last_tick_age_by_symbol"]["NIFTY"] = 0.3
    return classify_feed_health_truth(
        payload,
        symbols=("NIFTY", "BANKNIFTY"),
        max_ltp_age_sec=2.5,
        max_depth_age_sec=6.0,
    )


def test_stale_other_symbol_does_not_hold_explicitly_healthy_symbol():
    score_report = _report([_score("nifty", 0.9)])

    ranking = apply_feed_hold_to_ranking(score_report, _mixed_symbol_feed(), symbol="NIFTY")

    assert ranking.rank_count == 1
    assert FEED_HOLD_BLOCKER not in ranking.blockers


def test_stale_target_symbol_remains_held_under_symbol_scope():
    score_report = _report([_score("banknifty", 0.9, symbol="BANKNIFTY")])

    ranking = apply_feed_hold_to_ranking(score_report, _mixed_symbol_feed(), symbol="BANKNIFTY")

    assert ranking.rank_count == 0
    assert FEED_HOLD_BLOCKER in ranking.blockers


def test_symbol_isolation_fails_closed_for_shared_or_unknown_health():
    score_report = _report([_score("nifty", 0.9)])

    for decision in (
        _mixed_symbol_feed(ws_connected=False),
        _mixed_symbol_feed(global_blocked=True),
        _mixed_symbol_feed(missing_target=True),
        _mixed_symbol_feed(runtime_state="AUTH_BLOCKED"),
        _mixed_symbol_feed(feed_state="DOWN"),
        _mixed_symbol_feed(last_depth_age=99.0),
    ):
        ranking = apply_feed_hold_to_ranking(score_report, decision, symbol="NIFTY")
        assert ranking.rank_count == 0
        assert FEED_HOLD_BLOCKER in ranking.blockers


def test_symbol_isolation_rejects_persisted_snapshot_and_opaque_decisions():
    score_report = _report([_score("nifty", 0.9)])
    stale_snapshot = _mixed_symbol_feed().to_payload()
    stale_snapshot["context"] = {
        **stale_snapshot["context"],
        "runtime_snapshot_source": "runtime_feed_truth_snapshot_v1",
        "runtime_snapshot_feed_fresh": False,
    }
    opaque = {"feed_ok": False, "websocket_ok": True, "symbols": []}

    for decision in (stale_snapshot, opaque):
        ranking = apply_feed_hold_to_ranking(score_report, decision, symbol="NIFTY")
    assert ranking.rank_count == 0
    assert FEED_HOLD_BLOCKER in ranking.blockers


def test_symbol_isolation_rejects_boolean_or_inconsistent_identity_times():
    score_report = _report([_score("nifty", 0.9)])
    for field, value in (("receipt_epoch", True), ("generated_epoch", True), ("age_sec", True)):
        decision = _mixed_symbol_feed().to_payload()
        row = decision["symbols"][0]
        row["context"]["underlying_feed_identity"][field] = value
        ranking = apply_feed_hold_to_ranking(score_report, decision, symbol="NIFTY")
        assert ranking.rank_count == 0
        assert FEED_HOLD_BLOCKER in ranking.blockers


def test_symbol_isolation_requires_exact_current_underlying_identity():
    score_report = _report([_score("nifty", 0.9)])
    base = _mixed_symbol_feed().to_payload()
    cases = []
    stale_reconnect = json.loads(json.dumps(base))
    stale_reconnect["symbols"][0]["context"]["underlying_feed_identity"]["reconnect_generation"] = 2
    cases.append(stale_reconnect)
    missing_identity = json.loads(json.dumps(base))
    missing_identity["symbols"][0]["context"]["underlying_feed_identity"].pop("instrument_token")
    cases.append(missing_identity)
    false_health = json.loads(json.dumps(base))
    false_health["symbols"][0]["context"]["underlying_feed_identity"]["status"] = "UNHEALTHY"
    cases.append(false_health)

    for decision in cases:
        ranking = apply_feed_hold_to_ranking(score_report, decision, symbol="NIFTY")
        assert ranking.rank_count == 0
        assert FEED_HOLD_BLOCKER in ranking.blockers


def test_stale_feed_invalid_feed_truth_fails_closed():
    score_report = _report([_score("candidate", 0.9)])

    ranking = apply_feed_hold_to_ranking(score_report, None)

    assert ranking.rank_count == 0
    assert ranking.executable_count == 0
    assert FEED_HOLD_BLOCKER in ranking.blockers
    assert "invalid_payload" in ranking.blockers


def test_stale_feed_hold_report_is_json_serializable():
    hold = classify_feed_hold(_unhealthy_feed())
    payload = json.loads(hold.to_json())

    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["hold_active"] is True
    assert payload["metadata"]["gate"] == "feed_hold_gate_v1"
