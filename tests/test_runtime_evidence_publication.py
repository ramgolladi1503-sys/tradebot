import json

from core.live_runtime_artifacts import publish_runtime_evidence


def test_runtime_evidence_publishes_current_truth(tmp_path):
    publish_runtime_evidence(
        tmp_path, session_id="s", source_sha="a" * 40, pid=7,
        feed_payload={"ws_connected": True, "runtime_state": "RUNNING", "intended_tokens_count": 73, "subscribed_tokens_count": 71},
        cycle_payload={"cycle_id": "s:1:x", "cycle_ok": True, "cycle_outcome": "NO_ELIGIBLE_CANDIDATE"},
    )
    heartbeat = json.loads((tmp_path / "heartbeat.json").read_text())
    feed = json.loads((tmp_path / "feed_health.json").read_text())
    stage = json.loads((tmp_path / "pipeline_stage_state.json").read_text())
    assert heartbeat["state"] == "RUNNING" and heartbeat["cycle_id"] == "s:1:x"
    assert feed["websocket_connected"] is True
    assert feed["subscription_truth_complete"] is False
    assert stage["current_stage"] == "ADVISORY_READY"
    assert stage["cycle_ok"] is True
    assert all(not payload["live_execution_authorized"] for payload in (heartbeat, feed, stage))
