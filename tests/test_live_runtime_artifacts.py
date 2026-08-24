import json

from core.live_runtime_artifacts import write_pending_runtime_artifacts


def test_pending_runtime_artifacts_are_truthful_and_fail_closed(tmp_path):
    write_pending_runtime_artifacts(tmp_path, session_id="s1", source_sha="a" * 40)
    for name in ("feed_health.json", "heartbeat.json", "instrument_authority_manifest.json", "session_exit_gate.json"):
        payload = json.loads((tmp_path / name).read_text())
        assert payload["session_id"] == "s1"
        assert payload["source_sha"] == "a" * 40
        assert payload["verdict"] == "PENDING"
        assert payload["broker_write_authority"] is False
        assert payload["order_authority"] is False
        assert payload["orders_placed"] == 0
    assert json.loads((tmp_path / "session_exit_gate.json").read_text())["live_observation_e2e_ready"] is False
