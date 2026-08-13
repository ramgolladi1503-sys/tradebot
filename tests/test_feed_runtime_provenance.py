from core.feed.runtime_provenance import validate_feed_runtime_provenance
from core.runtime_boot_identity import RuntimeBootIdentity
import core.orchestrator_truth as orchestrator_truth
import core.feed.runtime_store as runtime_store
import core.feed_debug as feed_debug


def _identity():
    return RuntimeBootIdentity(run_id="run-current", boot_epoch=100.0, pid=1)


def _payload(**overrides):
    payload = {
        "run_id": "run-current",
        "boot_epoch": 100.0,
        "recovery_generation_id": 5,
        "feed_ok": True,
    }
    payload.update(overrides)
    return payload


def test_current_session_and_generation_are_accepted():
    result = validate_feed_runtime_provenance(_payload(), current_generation=5, current_identity=_identity())
    assert result["valid"] is True


def test_old_session_fails_closed():
    result = validate_feed_runtime_provenance(_payload(run_id="run-old"), current_generation=5, current_identity=_identity())
    assert result["valid"] is False
    assert "run_id_mismatch" in result["reasons"]


def test_old_generation_fails_closed_even_when_feed_ok_true():
    result = validate_feed_runtime_provenance(_payload(recovery_generation_id=4), current_generation=5, current_identity=_identity())
    assert result["valid"] is False
    assert "recovery_generation_id_mismatch" in result["reasons"]


def test_missing_session_and_generation_fail_closed():
    result = validate_feed_runtime_provenance({}, current_generation=5, current_identity=_identity())
    assert result["valid"] is False
    assert "missing_run_id" in result["reasons"]
    assert "missing_or_invalid_recovery_generation_id" in result["reasons"]


def test_missing_current_generation_fails_closed():
    result = validate_feed_runtime_provenance(_payload(), current_generation=None, current_identity=_identity())
    assert result["valid"] is False
    assert "missing_current_recovery_generation_id" in result["reasons"]


def test_orchestrator_loader_rejects_old_generation(monkeypatch, tmp_path):
    path = tmp_path / "feed_runtime_latest.json"
    path.write_text(__import__("json").dumps(_payload(recovery_generation_id=4)))
    monkeypatch.setattr(orchestrator_truth, "logs_dir", lambda: tmp_path)
    monkeypatch.setattr(orchestrator_truth, "get_feed_debug", lambda: {"recovery_generation_id": 5})
    payload, _ = orchestrator_truth.read_latest_feed_runtime_payload()
    assert payload["feed_ok"] is False
    assert payload["execution_feed_ready"] is False
    assert payload["provenance"]["valid"] is False


def test_runtime_store_reuses_current_generation_for_queued_payload(monkeypatch):
    monkeypatch.setattr(feed_debug, "get_feed_debug", lambda: {"recovery_generation_id": 7})
    payload = runtime_store._canonical_runtime_artifact_payload(
        {"ws_connected": False, "runtime_state": "STARTING", "market_open": True},
        ts_epoch=100.0,
    )
    assert payload["recovery_generation_id"] == 7
