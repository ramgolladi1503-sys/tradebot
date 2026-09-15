import hashlib
import json

from core.morning_controller import MorningController, STAGES


def _evidence(tmp_path, source_sha="a" * 40):
    result = {}
    for stage in STAGES:
        path = tmp_path / f"{stage}.json"
        payload = {"stage": stage, "session_date": "2026-09-16", "source_sha": source_sha, "status": "PASS", "read_only": True, "broker_api_called": False, "order_authority": False, "orders_placed": 0, "orders_modified": 0, "orders_cancelled": 0}
        raw = json.dumps(payload, sort_keys=True).encode(); path.write_bytes(raw)
        result[stage] = {"evidence_path": str(path), "evidence_sha256": hashlib.sha256(raw).hexdigest()}
    return result


def test_first_run_is_read_only_and_idempotent(tmp_path):
    controller = MorningController(tmp_path)
    first = controller.run(session_date="2026-09-16", source_sha="a" * 40, config_sha="b" * 64, instrument_sha="c" * 64, evidence=_evidence(tmp_path))
    second = controller.run(session_date="2026-09-16", source_sha="a" * 40, config_sha="b" * 64, instrument_sha="c" * 64, evidence={})
    assert first["session_classification"] == "FULL" == second["session_classification"]
    assert second["broker_api_called"] is False and second["orders_placed"] == 0


def test_missing_auth_waits_and_changed_input_invalidates_state(tmp_path):
    controller = MorningController(tmp_path); evidence = _evidence(tmp_path); evidence.pop("AUTH")
    result = controller.run(session_date="2026-09-16", source_sha="a" * 40, config_sha="b" * 64, instrument_sha="c" * 64, evidence=evidence)
    assert result["stages"]["AUTH"]["status"] == "WAITING_HUMAN_AUTH"
    changed = controller.run(session_date="2026-09-16", source_sha="d" * 40, config_sha="b" * 64, instrument_sha="c" * 64)
    assert changed["stages"]["DISCOVER_SOURCE"]["status"] == "BLOCKED"
    assert changed["session_classification"] == "PARTIAL_SESSION"


def test_governor_adapter_does_not_arm_observer_from_static_readiness():
    plan = {"final_state": "READY_FOR_GOVERNED_READ_ONLY_SESSION", "candidate_sha": "a" * 40,
            "certified_release_sha": "a" * 40, "instrument_master_state": "READY",
            "storage_state": "READY", "session_root": "/evidence", "auth_state": "AUTH_TOKEN_PRESENT_UNVERIFIED",
            "truth_feed_state": "READY"}
    evidence = MorningController.evidence_from_governor(plan)
    assert evidence["MROS"]["status"] == "PASS"
    assert evidence["ARM_OBSERVER"]["status"] == "BLOCKED"
    assert evidence["BROKER_READ"]["status"] == "BLOCKED"


def test_stage_evidence_hash_tamper_blocks(tmp_path):
    controller = MorningController(tmp_path); evidence = _evidence(tmp_path)
    evidence["DISCOVER_SOURCE"]["evidence_sha256"] = "0" * 64
    result = controller.run(session_date="2026-09-16", source_sha="a" * 40, config_sha="b" * 64, instrument_sha="c" * 64, evidence=evidence)
    assert result["stages"]["DISCOVER_SOURCE"]["status"] == "BLOCKED"


def test_stage_evidence_outside_governed_root_blocks(tmp_path):
    controller = MorningController(tmp_path / "state"); outside = tmp_path / "outside.json"
    outside.write_text("{}")
    evidence = {"DISCOVER_SOURCE": {"evidence_path": str(outside), "evidence_sha256": hashlib.sha256(outside.read_bytes()).hexdigest()}}
    result = controller.run(session_date="2026-09-16", source_sha="a" * 40, config_sha="b" * 64, instrument_sha="c" * 64, evidence=evidence)
    assert result["stages"]["DISCOVER_SOURCE"]["reason"] == "stage_evidence_path_outside_governed_root"
