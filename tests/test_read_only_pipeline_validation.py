import json

from core.read_only_pipeline_validation import validate_session_artifacts


def _write(root, name, payload):
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def test_validation_blocks_without_e2e(tmp_path):
    identity = {
        "source_sha": "a" * 40, "pipeline_sha": "a" * 40,
        "broker_write_authority": False, "order_authority": False,
        "paper_authorized": False, "live_execution_authorized": False,
    }
    _write(tmp_path, "SESSION_MANIFEST.json", identity)
    _write(tmp_path, "CONSUMERS.json", {**identity, "execution_capable": False})
    _write(tmp_path, "STRATEGY_REGISTRY.json", identity)
    _write(tmp_path, "SIDECAR_HEALTH.json", {**identity, "canonical_feed_owner_count": 1, "pr_sidecars_isolated": True, "broker_order_calls": 0, "live_db_writes": 0})
    _write(tmp_path, "session_exit_gate.json", {**identity, "broker_order_calls": 0, "live_observation_e2e_ready": False, "verdict": "BLOCKED_RUNTIME_GATES_PENDING"})
    result = validate_session_artifacts(runtime_root=tmp_path, source_sha="a" * 40, require_e2e=True)
    assert result["verdict"] == "BLOCKED"
    assert "current_session_e2e_not_proven" in result["failures"]
    assert result["promotion_eligible"] is False
