from __future__ import annotations

from types import SimpleNamespace

import core.orchestrator as orchestrator
from core.feed_truth_contract import build_feed_truth_contract
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
    context = build_execution_truth_context(
        market_data={
            "runtime_state": "RECOVERY_BLOCKED",
            "ws_connected": False,
            "reconnect_blocked_reason": "ws1006_process_restart_required",
        },
        latency_guard={},
    )
    assert build_feed_truth_contract(context["feed_truth_contract"]["source_snapshot"]).state == "RECOVERY_BLOCKED"
    payload = orchestrator._candidate_trace_payload(_candidate(), execution_truth_context=context)

    assert payload["execution_entry_status"] == "executable"
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


def test_execution_truth_decision_dedupes_blockers_and_skips_ok_markers():
    context = build_execution_truth_context(
        market_data={
            "runtime_state": "RECOVERY_BLOCKED",
            "ws_connected": False,
            "feed_truth_state": "RECOVERY_BLOCKED",
            "feed_truth_reason_code": "WS_DISCONNECTED",
            "reconnect_blocked_reason": "ws1006_process_restart_required",
            "quote_health": {"state": "OK"},
        },
        latency_guard={
            "latency_guard_triggered": True,
            "latency_guard_action": "OK",
            "latency_guard_reason": "LATENCY_GUARD_OK",
        },
    )

    assert context["quote_health_state"] == "BLOCKED"
    assert context["quote_health_stale_reasons"] == ["RECOVERY_BLOCKED"]
    assert context["feed_truth_contract_state"] == "RECOVERY_BLOCKED"
    assert context["feed_truth_contract_entries_allowed"] is False
    assert context["feed_truth_contract_quotes_trusted"] is False

    truth = orchestrator.normalize_candidate_execution_truth_payload(
        {
            "execution_entry_status": "executable",
            "execution_allowed": True,
            "eligible_for_execution": True,
            "permission": "EXECUTE",
            "final_action": "EXECUTE",
            "readiness": "READY",
            "execution_status": "executable",
            "candidate_status": "executable",
        },
        execution_truth_context=context,
    )

    assert truth["reportable_executable"] is False
    assert truth["execution_truth_blocked"] is True
    assert truth["execution_truth_blockers"] == [
        "RECOVERY_BLOCKED",
        "WS_DISCONNECTED",
        "WS1006_PROCESS_RESTART_REQUIRED",
    ]
    assert "LATENCY_GUARD_OK" not in truth["execution_truth_blockers"]


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
    assert payload["execution_entry_status"] == "executable"


def test_runtime_execution_truth_blocks_when_feedtruth_disconnected():
    contract = build_feed_truth_contract(
        {
            "runtime_state": "RUNNING",
            "ws_connected": False,
            "feed_truth_state": "DEAD",
            "quote_health": {"state": "OK"},
        }
    )
    truth = orchestrator.normalize_candidate_execution_truth_payload(
        _candidate().__dict__,
        execution_truth_context={
            "feed_truth_contract": contract.to_payload(),
            "runtime_state": "RUNNING",
            "ws_connected": False,
            "feed_truth_state": "DEAD",
            "quote_health_state": "OK",
        },
    )

    assert contract.state == "DISCONNECTED"
    assert truth["reportable_executable"] is False
    assert truth["execution_truth_blocked"] is True
    assert "WS_DISCONNECTED" in truth["execution_truth_blockers"]


def test_runtime_truth_blocker_overrides_executable_candidate_fields():
    truth = orchestrator.normalize_candidate_execution_truth_payload(
        {
            "execution_entry_status": "executable",
            "execution_allowed": True,
            "eligible_for_execution": True,
            "permission": "EXECUTE",
            "final_action": "EXECUTE",
            "readiness": "READY",
            "execution_status": "executable",
            "candidate_status": "executable",
            "execution_truth_blocked": True,
            "execution_truth_blockers": ["STALE", "WS_DISCONNECTED", "LATENCY_GUARD_DEGRADE_EXIT_ONLY"],
        },
        execution_truth_context=build_execution_truth_context(
            market_data={
                "runtime_state": "RUNNING",
                "ws_connected": True,
                "feed_truth_state": "LIVE",
                "quote_health": {"state": "OK", "stale_reasons": []},
            },
            latency_guard={},
        ),
    )

    assert truth["reportable_executable"] is False
    assert truth["execution_allowed"] is False
    assert truth["eligible_for_execution"] is False
    assert truth["permission"] == "BLOCK"
    assert truth["final_action"] == "BLOCK"
    assert truth["execution_status"] == "blocked"
    assert truth["candidate_status"] == "blocked"
    assert truth["visibility_bucket"] == "blocked"
    assert truth["execution_truth_blocked"] is True
    assert truth["execution_truth_blockers"] == ["STALE", "WS_DISCONNECTED", "LATENCY_GUARD_DEGRADE_EXIT_ONLY"]


def test_runtime_execution_truth_blocks_when_feedtruth_recovery_blocked_even_if_candidate_looks_executable():
    contract = build_feed_truth_contract(
        {
            "runtime_state": "RECOVERY_BLOCKED",
            "ws_connected": False,
            "reconnect_blocked_reason": "reactor_not_restartable_process_restart_required",
            "quote_health": {"state": "OK"},
        }
    )
    truth = orchestrator.normalize_candidate_execution_truth_payload(
        _candidate().__dict__,
        execution_truth_context={
            "feed_truth_contract": contract.to_payload(),
            "runtime_state": "RECOVERY_BLOCKED",
            "ws_connected": False,
            "reconnect_blocked_reason": "reactor_not_restartable_process_restart_required",
            "quote_health_state": "OK",
        },
    )

    assert contract.state == "RECOVERY_BLOCKED"
    assert truth["reportable_executable"] is False
    assert truth["execution_truth_blocked"] is True
    assert "RECOVERY_BLOCKED" in truth["execution_truth_blockers"]


def test_runtime_execution_truth_blocks_when_feedtruth_stale_option_ltp():
    contract = build_feed_truth_contract(
        {
            "runtime_state": "RUNNING",
            "ws_connected": True,
            "feed_truth_state": "LIVE",
            "feed_truth_reason_code": "STALE_OPTION_LTP",
            "quote_health": {"state": "STALE", "stale_reasons": ["LTP_STALE"]},
        }
    )
    truth = orchestrator.normalize_candidate_execution_truth_payload(
        _candidate().__dict__,
        execution_truth_context={
            "feed_truth_contract": contract.to_payload(),
            "runtime_state": "RUNNING",
            "ws_connected": True,
            "feed_truth_state": "LIVE",
            "feed_truth_reason_code": "STALE_OPTION_LTP",
            "quote_health_state": "STALE",
            "quote_health_stale_reasons": ["LTP_STALE"],
        },
    )

    assert contract.state == "STALE"
    assert truth["reportable_executable"] is False
    assert truth["execution_truth_blocked"] is True
    assert "STALE" in truth["execution_truth_blockers"]


def test_runtime_execution_truth_blocks_when_feedtruth_auth_blocked():
    contract = build_feed_truth_contract({"runtime_state": "AUTH_BLOCKED", "ws_connected": False})
    truth = orchestrator.normalize_candidate_execution_truth_payload(
        _candidate().__dict__,
        execution_truth_context={"feed_truth_contract": contract.to_payload()},
    )

    assert contract.state == "AUTH_BLOCKED"
    assert truth["reportable_executable"] is False
    assert truth["execution_truth_blocked"] is True
    assert "AUTH_BLOCKED" in truth["execution_truth_blockers"]


def test_runtime_execution_truth_dedupes_feedtruth_and_existing_blockers():
    contract = build_feed_truth_contract(
        {
            "runtime_state": "RECOVERY_BLOCKED",
            "ws_connected": False,
            "reconnect_blocked_reason": "ws1006_process_restart_required",
            "quote_health": {"state": "OK"},
        }
    )
    payload = orchestrator.normalize_candidate_execution_truth_payload(
        {
            "execution_entry_status": "executable",
            "execution_allowed": True,
            "eligible_for_execution": True,
            "permission": "EXECUTE",
            "final_action": "EXECUTE",
            "readiness": "READY",
            "execution_status": "executable",
            "candidate_status": "executable",
            "execution_truth_blockers": ["RECOVERY_BLOCKED", "RECOVERY_BLOCKED", "WS_DISCONNECTED"],
        },
        execution_truth_context={"feed_truth_contract": contract.to_payload()},
    )

    assert payload["execution_truth_blockers"] == ["RECOVERY_BLOCKED", "WS_DISCONNECTED"]


def test_runtime_execution_truth_excludes_feedtruth_ok_markers():
    contract = build_feed_truth_contract(
        {
            "runtime_state": "RUNNING",
            "ws_connected": True,
            "feed_truth_state": "LIVE",
            "latency_guard": {
                "latency_guard_triggered": True,
                "latency_guard_action": "OK",
                "latency_guard_reason": "LATENCY_GUARD_OK",
            },
            "quote_health": {"state": "OK"},
        }
    )
    truth = orchestrator.normalize_candidate_execution_truth_payload(
        _candidate().__dict__,
        execution_truth_context={"feed_truth_contract": contract.to_payload()},
    )

    assert contract.state == "LIVE"
    assert truth.get("reportable_executable", True) is True
    assert truth["execution_truth_state"] == "executable"
    assert "LATENCY_GUARD_OK" not in truth["execution_truth_blockers"]


def test_runtime_execution_truth_fails_closed_when_feedtruth_unknown_or_missing():
    truth = orchestrator.normalize_candidate_execution_truth_payload(
        _candidate().__dict__,
        execution_truth_context={"feed_truth_contract": {"state": "UNKNOWN", "entries_allowed": False, "quotes_trusted": False}},
    )

    assert truth["reportable_executable"] is False
    assert truth["execution_truth_blocked"] is True
    assert truth["execution_truth_state"] == "blocked"


def test_top_opportunities_payload_blocks_executable_when_feed_truth_snapshot_is_stale_even_if_market_looks_live(monkeypatch):
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
            market_data={
                "runtime_state": "RUNNING",
                "ws_connected": True,
                "feed_truth_state": "LIVE",
                "quote_health": {"state": "OK", "stale_reasons": []},
            },
            feed_truth={
                "ws_connected": True,
                "feed_fresh": False,
                "underlying_tick_fresh": True,
                "option_tick_fresh": False,
                "depth_fresh": False,
                "stale_reason": ["option_tick_stale_or_missing"],
            },
            latency_guard={},
        ),
    )

    candidate_payload = orchestrator._candidate_trace_payload(
        candidate,
        execution_truth_context=build_execution_truth_context(
            market_data={
                "runtime_state": "RUNNING",
                "ws_connected": True,
                "feed_truth_state": "LIVE",
                "quote_health": {"state": "OK", "stale_reasons": []},
            },
            feed_truth={
                "ws_connected": True,
                "feed_fresh": False,
                "underlying_tick_fresh": True,
                "option_tick_fresh": False,
                "depth_fresh": False,
                "stale_reason": ["option_tick_stale_or_missing"],
            },
            latency_guard={},
        ),
    )

    assert candidate_payload["reportable_executable"] is False
    assert candidate_payload["execution_truth_blocked"] is True
    assert candidate_payload["visibility_bucket"] == "blocked"
    assert candidate_payload["candidate_status"] == "blocked"
    assert payload["top_executable_count"] == 0
    assert payload["top_executable_opportunities"] == []
    assert payload["selector_outcome"] == "NO_EXECUTABLE_OPPORTUNITY"


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
