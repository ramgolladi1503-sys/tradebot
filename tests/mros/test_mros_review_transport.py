from pathlib import Path

from scripts.mros.mros_review_transport import canonicalize_artifact


def _manifest():
    return {
        "candidate_head": "a" * 40,
        "sprint": "S003",
        "round": "R004",
        "members": [
            {
                "execution_role_id": "R01",
                "packet_path": "research/evidence/sprints/S003/agent_queue/packets/S003_R004_R01.md",
                "output_path": "research/evidence/sprints/S003/agent_queue/results/S003_R004_R01.json",
                "receipt_path": "research/evidence/sprints/S003/agent_queue/receipts/S003_R004_R01.json",
            }
        ],
    }


def test_absolute_reviewer_paths_are_replaced_by_frozen_relative_paths(tmp_path: Path):
    manifest = _manifest()
    member = manifest["members"][0]
    raw = {
        "candidate_head": "b" * 40,
        "sprint": "S999",
        "round": "R999",
        "execution_role_id": "R77",
        "packet_path": str(tmp_path / member["packet_path"]),
        "output_path": str(tmp_path / member["output_path"]),
        "verdict": "REPAIR_REQUIRED",
        "findings": [{"severity": "MAJOR", "evidence": "substantive evidence"}],
    }
    receipt = {"job": {"job_id": "1" * 32, "state": "SUCCEEDED", "exit_code": 0}}

    normalized = canonicalize_artifact(
        raw, member=member, manifest=manifest, receipt=receipt, queue_repo=tmp_path
    )

    assert normalized["packet_path"] == member["packet_path"]
    assert normalized["output_path"] == member["output_path"]
    assert normalized["candidate_head"] == manifest["candidate_head"]
    assert normalized["sprint"] == "S003"
    assert normalized["round"] == "R004"
    assert normalized["execution_role_id"] == "R01"
    assert normalized["verdict"] == raw["verdict"]
    assert normalized["findings"] == raw["findings"]


def test_malformed_execution_job_id_is_replaced_by_receipt_truth(tmp_path: Path):
    manifest = _manifest()
    member = manifest["members"][0]
    raw = {
        "execution_job_id": "29823326ebe144248e3b9ced52430a2",
        "verdict": "FAIL",
        "findings": [{"severity": "CRITICAL", "evidence": "independent finding"}],
    }
    receipt_job_id = "9" * 32
    receipt = {"job": {"job_id": receipt_job_id, "state": "SUCCEEDED", "exit_code": 0}}

    normalized = canonicalize_artifact(
        raw, member=member, manifest=manifest, receipt=receipt, queue_repo=tmp_path
    )

    assert normalized["execution_job_id"] == receipt_job_id
    assert normalized["verdict"] == "FAIL"
    assert normalized["findings"] == raw["findings"]
