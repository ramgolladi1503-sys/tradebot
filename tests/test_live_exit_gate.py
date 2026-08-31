import json

from core.live_runtime_artifacts import write_session_exit_gate


def test_exit_gate_never_infers_e2e_from_shutdown(tmp_path):
    payload = write_session_exit_gate(
        tmp_path, session_id="s1", source_sha="a" * 40,
        auth_valid=True, feed_current=False, persistence_advancing=True,
        instrument_authority_current=True, shutdown_drain_complete=True,
    )
    assert payload["verdict"] == "BLOCKED_RUNTIME_GATES_PENDING"
    assert payload["live_observation_e2e_ready"] is False
    assert payload["broker_order_calls"] == 0
    stored = json.loads((tmp_path / "session_exit_gate.json").read_text())
    assert stored["option_surface_ran"] is False
    assert stored["cas_freeze"] is False
