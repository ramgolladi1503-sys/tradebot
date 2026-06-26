from __future__ import annotations

from types import SimpleNamespace

import core.orchestrator as orch


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
        execution_blocked=False,
        hard_blockers=[],
        blockers=[],
        unresolved_contract=False,
        execution_entry=101.0,
        source_flags={},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_candidate_trace_payload_marks_real_executable_consistent():
    payload = orch._candidate_trace_payload(_candidate())

    assert payload["visibility_bucket"] == "executable"
    assert payload["reportable_executable"] is True
    assert payload["runtime_truth_consistent"] is True
    assert payload["runtime_truth_reasons"] == []
    assert "execution_status" in payload["executable_signals"]


def test_candidate_trace_payload_exposes_executable_looking_queue_only_mismatch():
    payload = orch._candidate_trace_payload(
        _candidate(
            candidate_status="advisory_only",
            permission="QUEUE_ONLY",
            final_action="QUEUE_ONLY",
            readiness="QUEUE_ONLY",
            execution_status="executable",
            execution_entry_status="executable",
            execution_allowed=True,
            eligible_for_execution=False,
            execution_entry=None,
        )
    )

    assert payload["visibility_bucket"] == "advisory"
    assert payload["reportable_executable"] is False
    assert payload["runtime_truth_consistent"] is False
    assert "executable_signals_not_reportable" in payload["runtime_truth_reasons"]
    assert "blocked_or_advisory_candidate_has_executable_signals" in payload["runtime_truth_reasons"]


def test_candidate_trace_payload_does_not_flag_intentional_queue_only_block():
    payload = orch._candidate_trace_payload(
        _candidate(
            candidate_status="advisory_only",
            permission="QUEUE_ONLY",
            final_action="QUEUE_ONLY",
            readiness="QUEUE_ONLY",
            execution_status="queue_only",
            execution_entry_status="blocked_contract",
            execution_allowed=False,
            eligible_for_execution=False,
            execution_entry=None,
        )
    )

    assert payload["visibility_bucket"] == "advisory"
    assert payload["reportable_executable"] is False
    assert payload["runtime_truth_consistent"] is True
    assert payload["runtime_truth_reasons"] == []


def test_regime_unstable_diagnostic_payload_contains_threshold_context(monkeypatch):
    monkeypatch.setattr(orch.cfg, "REGIME_PROB_MIN", 0.45, raising=False)

    payload = orch._regime_unstable_diagnostic_payload(
        {
            "symbol": "NIFTY",
            "execution_mode": "LIVE",
            "primary_regime": "TREND",
            "regime_prob_max": 0.41,
            "regime_entropy": 1.42,
            "unstable_reasons": ["prob_too_low", "entropy_too_high"],
            "regime_unstable_streak": 4,
            "regime_unstable_block_after": 2,
            "regime_unstable_debounced": False,
            "feed_health": {"is_fresh": True, "ws_connected": True},
            "quote_health": {"state": "OK"},
        },
        ["REGIME_UNSTABLE"],
    )

    assert payload["symbol"] == "NIFTY"
    assert payload["execution_mode"] == "LIVE"
    assert payload["regime_prob_max"] == 0.41
    assert payload["regime_prob_min"] == 0.45
    assert payload["regime_entropy"] == 1.42
    assert "regime_entropy_max" in payload
    assert payload["regime_unstable_streak"] == 4
    assert payload["feed_health"]["is_fresh"] is True


def test_regime_unstable_diagnostic_payload_ignores_unrelated_gate_reason():
    assert orch._regime_unstable_diagnostic_payload(
        {"symbol": "NIFTY"},
        ["NO_LIVE_OPTION_FEED"],
    ) == {}
