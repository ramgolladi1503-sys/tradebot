from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "mros"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import advance_program


HEAD = "a" * 40
JOB_ID = "1" * 32
SOURCE_REF = "research/evidence/sprints/S003/agent_queue/results/native.txt"
RECEIPT_REF = "research/evidence/sprints/S003/agent_queue/receipts/native.json"


def _native(source_text: str = "PASS\n") -> dict:
    return {
        "schema_version": "mros-native-evidence-v2",
        "evidence_kind": "native_validation",
        "repository": "ramgolladi1503-sys/tradebot",
        "branch": "research/mros-program-v1",
        "head": HEAD,
        "validator": "scripts/mros/calibrate_review_audit_board_v2.py",
        "python_version": "3.12.2",
        "command": f"python3 scripts/mros/calibrate_review_audit_board_v2.py --candidate-head {HEAD}",
        "checks": 1,
        "passed": 1,
        "failed": 0,
        "exit_code": 0,
        "timestamp": "2026-08-09T00:00:00+00:00",
        "transport": "mac_git_mailbox",
        "execution_job_id": JOB_ID,
        "execution_receipt_ref": RECEIPT_REF,
        "source_output_ref": SOURCE_REF,
        "source_output_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "runtime_authority": "NONE",
        "broker_actions": "NONE",
    }


def _write_valid_sources(queue: Path, source_text: str = "PASS\n") -> None:
    source = queue / SOURCE_REF
    receipt = queue / RECEIPT_REF
    source.parent.mkdir(parents=True, exist_ok=True)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(source_text, encoding="utf-8")
    receipt.write_text(json.dumps({
        "runtime_authority": "NONE",
        "broker_actions_allowed": False,
        "job": {
            "job_id": JOB_ID,
            "candidate_sha": HEAD,
            "state": "SUCCEEDED",
            "exit_code": 0,
        },
        "request": {"candidate_sha": HEAD},
    }), encoding="utf-8")


def test_native_authority_rejects_self_attested_missing_sources(tmp_path: Path) -> None:
    errors = advance_program._verify_native_authority(_native(), candidate_head=HEAD, queue_repo=tmp_path)
    assert "NATIVE_SOURCE_OUTPUT_MISSING" in errors
    assert "NATIVE_EXECUTION_RECEIPT_MISSING" in errors


def test_native_authority_verifies_source_hash_and_receipt(tmp_path: Path) -> None:
    _write_valid_sources(tmp_path)
    assert advance_program._verify_native_authority(_native(), candidate_head=HEAD, queue_repo=tmp_path) == []

    (tmp_path / SOURCE_REF).write_text("tampered\n", encoding="utf-8")
    errors = advance_program._verify_native_authority(_native(), candidate_head=HEAD, queue_repo=tmp_path)
    assert "NATIVE_SOURCE_OUTPUT_HASH_MISMATCH" in errors


def test_authorize_fails_closed_when_native_refs_do_not_resolve(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(advance_program, "_acceptance_ids", lambda sprint: (["AC-1"], []))
    monkeypatch.setattr(advance_program, "validate_trusted_population", lambda **kwargs: [])
    monkeypatch.setattr(advance_program, "load_exact_receipts", lambda **kwargs: ({}, []))
    monkeypatch.setattr(advance_program, "_validate_aggregate", lambda *args, **kwargs: [])

    review = {"review_round": "R012", "reviews": []}
    audit = {"audit_round": "A012"}
    out = advance_program.authorize(
        sprint="S004",
        next_sprint="S005",
        candidate_head=HEAD,
        review=review,
        audit=audit,
        native=_native(),
        context_errors=[],
        review_manifest={},
        audit_manifest={},
        queue_repo=tmp_path,
        review_manifest_path="review.json",
        audit_manifest_path="audit.json",
        review_round="R012",
        audit_round="A012",
        expected_native_ref="native.json",
    )
    assert out["advance"] is False
    assert "NATIVE_VALIDATION_NOT_PASS_FOR_HEAD" in out["errors"]
    assert "NATIVE_SOURCE_OUTPUT_MISSING" in out["errors"]
    assert "NATIVE_EXECUTION_RECEIPT_MISSING" in out["errors"]
