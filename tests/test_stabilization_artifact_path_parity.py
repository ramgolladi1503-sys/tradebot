from __future__ import annotations

import json

import pytest

from core.runtime_candidate_handoff_root_cause import write_candidate_handoff_root_cause_latest
from core.runtime_feed_truth_snapshot import write_feed_truth_snapshot_latest
from core.runtime_notrade_reason_truth import write_notrade_reason_truth_latest
from core.runtime_phase2_rejection_evidence import write_phase2_rejection_evidence_latest
from core.runtime_ranking_quality_evidence import write_ranking_quality_latest
from core.runtime_snapshot_store import write_top_opportunities_snapshots


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture()
def _artifact_dirs(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = tmp_path / "logs"
    runtime_root.mkdir(parents=True, exist_ok=True)
    logs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(runtime_root / "logs"))
    monkeypatch.setenv("REPO_LOG_DIR", str(logs_root))
    return runtime_root, logs_root


def test_phase2_rejection_writer_writes_repo_logs_and_runtime_root(_artifact_dirs):
    runtime_root, logs_root = _artifact_dirs
    write_phase2_rejection_evidence_latest(payload={"read_only": True, "is_order_action": False, "broker_api_called": False})
    assert (logs_root / "phase2_rejection_latest.json").exists()
    assert (runtime_root / "phase2_rejection_latest.json").exists()
    _read_json(logs_root / "phase2_rejection_latest.json")
    _read_json(runtime_root / "phase2_rejection_latest.json")


def test_feed_truth_writer_writes_repo_logs_and_runtime_root(_artifact_dirs):
    runtime_root, logs_root = _artifact_dirs
    write_feed_truth_snapshot_latest(payload={"read_only": True, "is_order_action": False, "broker_api_called": False})
    assert (logs_root / "feed_truth_latest.json").exists()
    assert (runtime_root / "feed_truth_latest.json").exists()
    _read_json(logs_root / "feed_truth_latest.json")
    _read_json(runtime_root / "feed_truth_latest.json")


def test_notrade_reason_truth_writer_writes_repo_logs_and_runtime_root(_artifact_dirs):
    runtime_root, logs_root = _artifact_dirs
    write_notrade_reason_truth_latest(payload={"read_only": True, "is_order_action": False, "broker_api_called": False})
    assert (logs_root / "notrade_reason_truth_latest.json").exists()
    assert (runtime_root / "notrade_reason_truth_latest.json").exists()
    _read_json(logs_root / "notrade_reason_truth_latest.json")
    _read_json(runtime_root / "notrade_reason_truth_latest.json")


def test_ranking_quality_writer_writes_repo_logs_and_runtime_root(_artifact_dirs):
    runtime_root, logs_root = _artifact_dirs
    write_ranking_quality_latest(payload={"read_only": True, "is_order_action": False, "broker_api_called": False})
    assert (logs_root / "ranking_quality_latest.json").exists()
    assert (runtime_root / "ranking_quality_latest.json").exists()
    _read_json(logs_root / "ranking_quality_latest.json")
    _read_json(runtime_root / "ranking_quality_latest.json")


def test_candidate_handoff_writer_writes_repo_logs_and_runtime_root(_artifact_dirs):
    runtime_root, logs_root = _artifact_dirs
    write_candidate_handoff_root_cause_latest(payload={"read_only": True, "is_order_action": False, "broker_api_called": False})
    assert (logs_root / "candidate_handoff_latest.json").exists()
    assert (runtime_root / "candidate_handoff_latest.json").exists()
    _read_json(logs_root / "candidate_handoff_latest.json")
    _read_json(runtime_root / "candidate_handoff_latest.json")


def test_top_opportunities_writer_writes_repo_logs_and_runtime_root(_artifact_dirs):
    runtime_root, logs_root = _artifact_dirs
    write_top_opportunities_snapshots(payload={"read_only": True}, producer="test")
    assert (logs_root / "top_opportunities_latest.json").exists()
    assert (runtime_root / "top_opportunities_latest.json").exists()
    _read_json(logs_root / "top_opportunities_latest.json")
    _read_json(runtime_root / "top_opportunities_latest.json")

