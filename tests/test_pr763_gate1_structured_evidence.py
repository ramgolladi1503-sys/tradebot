"""Authority tests for the structured PR #763 Gate-1 evidence collector."""

from pathlib import Path

from tools.pr763_gate1_structured_evidence import (
    SQLITE_OPERATION_CASES,
    STORE_CASES,
    collect_structured_evidence,
    validate_structured_evidence,
)


def test_structured_gate1_evidence_closes_without_live_runtime(tmp_path: Path):
    evidence = collect_structured_evidence(tmp_path / "certification")

    assert evidence["live_started"] is False
    assert evidence["registered_callback_path"].endswith("core.kite_depth_ws.on_ticks")
    assert validate_structured_evidence(evidence) == []
    assert evidence["missing_controls"] == []
    assert evidence["verdict"] == "REAL_CALLBACK_PERSISTENCE_GATE_CLOSED"

    callback = evidence["callback"]
    assert callback["wrapper_entries"] == callback["wrapper_exits"] == 1
    assert callback["delegate_entries"] == callback["delegate_exits"] == 1
    assert callback["exceptions"] == 0
    assert callback["maximum_duration_ms"] < callback["frozen_sla_ms"]
    assert callback["maximum_duration_ms"] < 5_000

    for authority in ("tick", "depth", "runtime"):
        worker = evidence["workers"][authority]
        row = evidence["authorities"][authority]
        assert worker["thread_id"] != callback["thread_id"]
        assert row["accepted_delta"] >= 1
        assert row["persisted_delta"] == row["accepted_delta"]
        assert row["pending_after_drain"] == 0
        assert row["rejected_delta"] == 0
        assert row["failure_delta"] == 0
        assert row["drain_complete"] is True
        assert row["worker_alive_after_drain"] is False

    assert evidence["authorities"]["depth"]["same_instance"] is True
    assert evidence["sqlite"]["normal_violations"] == []
    assert evidence["synchronous_stores"]["normal_violations"] == []
    assert evidence["filesystem"]["normal_violations"] == []

    assert set(evidence["sqlite"]["negative_controls"]) == set(SQLITE_OPERATION_CASES.values())
    assert all(row["detected"] for row in evidence["sqlite"]["negative_controls"].values())
    assert set(evidence["synchronous_stores"]["negative_controls"]) == set(STORE_CASES.values())
    assert all(row["detected"] for row in evidence["synchronous_stores"]["negative_controls"].values())
    assert evidence["filesystem"]["negative_controls"]["builtins.open"]["detected"] is True
    assert evidence["filesystem"]["negative_controls"]["Path.open"]["detected"] is True
    assert evidence["filesystem"]["unscoped_control"]["file_created"] is True
    assert evidence["filesystem"]["unscoped_control"]["detected_as_scoped"] is False

    observer = evidence["launcher_hooks"]["observer"]
    assert observer["configured_state"] is True
    assert observer["effective_state"] is True
    assert observer["observed_traversal_count"] == 1


def test_structured_gate1_validator_fails_closed_on_missing_authority(tmp_path: Path):
    evidence = collect_structured_evidence(tmp_path / "certification")
    evidence["authorities"]["runtime"]["persisted_delta"] = 0
    assert "runtime_exact_reconciliation" in validate_structured_evidence(evidence)


def test_structured_gate1_validator_fails_closed_on_missing_tripwire(tmp_path: Path):
    evidence = collect_structured_evidence(tmp_path / "certification")
    evidence["sqlite"]["negative_controls"]["connection.execute"]["detected"] = False
    assert "sqlite_negative_control:connection.execute" in validate_structured_evidence(evidence)
