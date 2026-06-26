import json
from unittest import mock
import core.orchestrator as orchestrator_module
from core.orchestrator import Orchestrator, _feed_truth_cycle_gate
from core.recovery_state_machine import evaluate_feed_state, RecoveryState, is_fatal_state

def test_split_brain_agreement_and_no_legacy_reads(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator_module, "is_market_open_ist", lambda now=None: True)
    monkeypatch.setattr(orchestrator_module, "now_utc_epoch", lambda: 1772800000.0)
    monkeypatch.setattr(orchestrator_module, "logs_dir", lambda: tmp_path)
    
    # Spy on build_canonical_feed_truth_state
    spy_called = []
    original_build = orchestrator_module.build_canonical_feed_truth_state
    def dummy_build(*args, **kwargs):
        spy_called.append(args)
        return original_build(*args, **kwargs)
    monkeypatch.setattr(orchestrator_module, "build_canonical_feed_truth_state", dummy_build)

    payload = {
        "ts_epoch": 1772800000.0,
        "ws_connected": True,
        "effective_ws_connected": True,
        "market_open": True,
        "runtime_state": "LIVE",
        "feed_ok": True,
        "feed_ok_hysteresis_state": {"consecutive_good": 3, "consecutive_bad": 0, "feed_ok": True},
    }
    
    from core.paths import feed_runtime_snapshot_path
    feed_runtime_path = feed_runtime_snapshot_path(lambda: tmp_path)
    feed_runtime_path.write_text(json.dumps(payload), encoding="utf-8")
    
    orch = Orchestrator.__new__(Orchestrator)
    monkeypatch.setattr(orch, "_latest_decision_rows", lambda max_age_sec=None: {})
    
    # 1. Run cycle gate and pilot ok check
    gate_result = _feed_truth_cycle_gate(payload)
    pilot_ok, pilot_reasons = orch._pilot_feed_ok()
    
    # Verify they agree (both should say OK/not skip)
    assert gate_result["skip"] is False
    assert pilot_ok is True
    assert pilot_reasons == []
    
    # Verify build_canonical_feed_truth_state was NOT called during these checks
    assert len(spy_called) == 0, "build_canonical_feed_truth_state was called when it shouldn't have been!"
    
    # 2. Test DOWN alone is non-fatal in recovery machine
    payload_down = {
        "ts_epoch": 1772800000.0,
        "ws_connected": True,
        "effective_ws_connected": True,
        "market_open": False,
        "runtime_state": "DOWN",
        "feed_ok_hysteresis_state": {"consecutive_good": 3, "consecutive_bad": 0, "feed_ok": True},
    }
    rec_state = evaluate_feed_state(payload_down)
    assert rec_state == RecoveryState.DOWN
    assert is_fatal_state(rec_state) is False
    
    # 3. Test process_restart_required forces fatal restart
    payload_fatal = {
        "ts_epoch": 1772800000.0,
        "market_open": True,
        "process_restart_required": True,
    }
    rec_state_fatal = evaluate_feed_state(payload_fatal)
    assert rec_state_fatal == RecoveryState.FATAL
    assert is_fatal_state(rec_state_fatal) is True
