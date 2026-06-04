from __future__ import annotations

from types import SimpleNamespace

import core.orchestrator as orchestrator
from core.runtime_execution_truth import build_execution_truth_context, normalize_candidate_execution_truth_payload
from core.runtime_phase2_rejection_evidence import build_phase2_rejection_evidence_payload


def _candidate(**overrides):
    base = dict(
        trade_id="real-1",
        symbol="NIFTY",
        strategy_family="trend",
        candidate_type="directional",
        rank_score=0.87,
        candidate_status="executable",
        execution_status="executable",
        execution_entry_status="executable",
        permission="EXECUTE",
        final_action="EXECUTE",
        readiness="READY",
        execution_allowed=True,
        eligible_for_execution=True,
        execution_entry=101.0,
        reason="ok",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_candidate_trace_payload_normalizes_recovery_block_to_non_executable():
    payload = orchestrator._candidate_trace_payload(
        _candidate(),
        execution_truth_context=build_execution_truth_context(
            market_data={
                "runtime_state": "RECOVERY_BLOCKED",
                "ws_connected": False,
                "reconnect_blocked_reason": "ws1006_process_restart_required",
            },
            latency_guard={},
        ),
    )

    assert payload["reportable_executable"] is False
    assert payload["visibility_bucket"] == "blocked"
    assert payload["execution_allowed"] is False
    assert payload["eligible_for_execution"] is False
    assert payload["permission"] == "BLOCK"
    assert payload["final_action"] == "BLOCK"
    assert payload["candidate_status"] == "blocked"
    assert payload["runtime_truth_consistent"] is False
    assert "RECOVERY_BLOCKED" in payload["execution_truth_blockers"]
    assert "WS_DISCONNECTED" in payload["execution_truth_blockers"]


def test_candidate_trace_payload_normalizes_latency_degrade_exit_only_to_advisory():
    payload = orchestrator._candidate_trace_payload(
        _candidate(),
        execution_truth_context=build_execution_truth_context(
            latency_guard={
                "latency_guard_triggered": True,
                "latency_guard_mode": "LIVE",
                "latency_guard_action": "DEGRADE_EXIT_ONLY",
                "latency_guard_reason": "latency_sustained_breach",
            },
        ),
    )

    assert payload["reportable_executable"] is False
    assert payload["visibility_bucket"] == "advisory"
    assert payload["execution_allowed"] is False
    assert payload["eligible_for_execution"] is False
    assert payload["permission"] == "QUEUE_ONLY"
    assert payload["final_action"] == "QUEUE_ONLY"
    assert payload["candidate_status"] == "advisory_only"
    assert payload["runtime_truth_consistent"] is False
    assert "LATENCY_GUARD_DEGRADE_EXIT_ONLY" in payload["execution_truth_blockers"]


def test_top_opportunities_payload_suppresses_executable_output_when_feed_truth_blocked(monkeypatch):
    candidate = _candidate()

    monkeypatch.setattr(
        orchestrator,
        "run_engine_phase2",
        lambda candidates, active_trade=None, top_n=5, min_enter_score=0.70: {
            "state": "ENTER",
            "reason": "selected",
            "ranked": [dict(candidate.__dict__)],
            "selected": dict(candidate.__dict__),
            "next_active_trade": None,
        },
        raising=True,
    )

    payload = orchestrator._build_top_opportunities_payload(
        candidates=[dict(candidate.__dict__)],
        executable_top_n=5,
        advisory_top_n=5,
        active_trade=None,
        execution_truth_context=build_execution_truth_context(
            feed_truth={
                "feed_ok": False,
                "ws_connected": False,
                "feed_truth_state": "RECONNECT_BLOCKED",
                "feed_truth_strict_live": False,
            },
            latency_guard={},
        ),
    )

    assert payload["top_executable_count"] == 0
    assert payload["top_executable_opportunities"] == []
    assert payload["top_blocked_count"] == 1
    assert payload["top_blocked_opportunities"][0]["candidate_status"] == "blocked"
    assert payload["top_blocked_opportunities"][0]["runtime_truth_consistent"] is False
    assert "GLOBAL_FEED_UNHEALTHY" in payload["top_executable_block_reasons"]
    assert payload["selector_outcome"] == "NO_EXECUTABLE_OPPORTUNITY"




def test_candidate_trace_payload_blocks_ltp_stale_even_when_candidate_looks_executable():
    payload = orchestrator._candidate_trace_payload(
        _candidate(),
        execution_truth_context=build_execution_truth_context(
            market_data={
                "runtime_state": "RUNNING",
                "ws_connected": True,
                "feed_truth_state": "LIVE",
                "feed_truth_reason_code": "STALE_OPTION_LTP",
                "option_feed_block_reason": "STALE_OPTION_LTP",
                "quote_health": {"state": "STALE", "stale_reasons": ["LTP_STALE AGE=4.17 MAX=2.50"]},
            },
            latency_guard={},
        ),
    )

    assert payload["reportable_executable"] is False
    assert payload["execution_allowed"] is False
    assert payload["eligible_for_execution"] is False
    assert payload["permission"] == "BLOCK"
    assert payload["final_action"] == "BLOCK"
    assert payload["execution_status"] == "blocked"
    assert payload["candidate_status"] == "blocked"
    assert payload["visibility_bucket"] == "blocked"
    assert payload["readiness"] == "BLOCKED"
    assert payload["execution_truth_state"] == "blocked"
    assert payload["execution_truth_blocked"] is True
    assert "STALE_OPTION_LTP" in payload["execution_truth_blockers"]
    assert any("LTP_STALE" in reason for reason in payload["execution_truth_blockers"])

def test_phase2_rejection_evidence_emits_hard_execution_blocker_details():
    payload = build_phase2_rejection_evidence_payload(
        phase2_state="ENTER",
        raw_candidates=[
            {
                "trade_id": "T1",
                "symbol": "BANKNIFTY",
                "instrument": "OPT",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": False,
                "quote_source": "option_chain_live",
                "quote_age_sec": 1.0,
                "spread_pct": 0.002,
                "liquidity_score": 1.0,
                "candidate_status": "blocked",
                "hard_blockers": ["STALE_OPTION_LTP", "latency_guard_degrade_exit_only"],
            }
        ],
        ranked_candidates=[
            {
                "trade_id": "T1",
                "symbol": "BANKNIFTY",
                "candidate_status": "blocked",
                "execution_ok": False,
                "hard_blockers": ["STALE_OPTION_LTP", "latency_guard_degrade_exit_only"],
            }
        ],
        drop_reason_counts={"hard_feed_stale": 1},
    )

    details = {row["reason_code"]: row for row in payload["hard_execution_blocker_details"]}
    assert details["STALE_OPTION_LTP"]["category"] == "feed"
    assert details["LATENCY_GUARD_DEGRADE_EXIT_ONLY"]["category"] == "latency_guard"
    assert payload["hard_blocker_counts"]["stale_option_ltp"] == 1
    assert payload["hard_blocker_counts"]["latency_guard_degrade_exit_only"] == 1
