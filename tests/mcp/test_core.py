from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from tools.tradebot_mcp.core import (
    DataAuditService,
    EvidenceService,
    GateService,
    SafePathPolicy,
    SafetyError,
    Settings,
    sha256_file,
)
from tools.tradebot_mcp.safe_git import SafeGitAuditService


def _settings(root: Path) -> Settings:
    return Settings(
        root=root,
        evidence_roots=(root / "research", root / "evidence"),
        data_roots=(root / "runtime",),
        max_text_bytes=100_000,
        max_hash_bytes=10_000_000,
        max_result_rows=20,
        max_files=100,
    )


def test_safe_path_rejects_escape_and_secrets(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "runtime").mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    secret = root / ".env"
    secret.write_text("TOKEN=x", encoding="utf-8")
    policy = SafePathPolicy(_settings(root))

    with pytest.raises(SafetyError):
        policy.resolve(outside)
    with pytest.raises(SafetyError):
        policy.resolve(secret)


def test_safe_path_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    runtime = root / "runtime"
    runtime.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = runtime / "link.json"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable")
    with pytest.raises(SafetyError):
        SafePathPolicy(_settings(root)).resolve(link)


def test_evidence_service_reads_explicit_context_and_hashes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    context = root / "research" / "demo" / "context"
    context.mkdir(parents=True)
    (root / "runtime").mkdir()
    status = {"phase": "WAVE1_REOPENED_INCOMPLETE", "holdout_locked": True}
    (context / "08_cycle_status.json").write_text(json.dumps(status), encoding="utf-8")
    (context / "01_research_contract.md").write_text("contract-v1", encoding="utf-8")
    (context / "02_safety_boundaries.md").write_text("read-only", encoding="utf-8")
    (context / "06_consumed_evidence_registry.json").write_text("{}", encoding="utf-8")
    (context / "07_agent_registry.json").write_text("{}", encoding="utf-8")
    (context / "11_candidate_freeze_registry.json").write_text("{}", encoding="utf-8")

    service = EvidenceService(_settings(root))
    result = service.get_research_status(str(context))

    assert result["status"] == "PRESENT"
    assert result["content"] == status
    assert result["sha256"] == hashlib.sha256(
        (context / "08_cycle_status.json").read_bytes()
    ).hexdigest()


def test_data_audit_parquet_temporal_checks(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    runtime = root / "runtime"
    runtime.mkdir(parents=True)
    (root / "research").mkdir()
    path = runtime / "ticks.parquet"
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-07-20T03:45:00Z",
                    "2026-07-20T03:46:00Z",
                    "2026-07-20T03:46:00Z",
                    "2026-07-20T03:49:00Z",
                ],
                utc=True,
            ),
            "price": [100.0, 101.0, 101.5, 103.0],
        }
    )
    frame.to_parquet(path, index=False)
    service = DataAuditService(_settings(root))

    assert service.count_rows(str(path))["rows"] == 4
    assert service.inspect_schema(str(path))["rows"] == 4
    assert service.audit_duplicates(str(path), "timestamp")["duplicate_timestamps"] == 1
    assert service.audit_timestamp_order(str(path), "timestamp")["monotonic_non_decreasing"]
    gaps = service.audit_missing_intervals(str(path), "timestamp", expected_seconds=60)
    assert gaps["gap_count"] == 1
    sessions = service.count_sessions(str(path), "timestamp")
    assert sessions["session_count"] == 1


def _write_gate_evidence(root: Path, gate_name: str, check_ids: tuple[str, ...]) -> Path:
    artifact = root / "evidence" / "artifact.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text('{"ok":true}', encoding="utf-8")
    digest = sha256_file(artifact)
    checks = {
        check_id: {
            "status": "PASS",
            "command": "pytest -q",
            "exit_code": 0,
            "producer_commit": "0123456789abcdef",
            "artifact": str(artifact),
            "sha256": digest,
        }
        for check_id in check_ids
    }
    evidence = root / "evidence" / "gate_evidence.json"
    evidence.write_text(
        json.dumps({"schema_version": 1, "gates": {gate_name: {"checks": checks}}}),
        encoding="utf-8",
    )
    return evidence


def test_gate_service_fails_closed_on_hash_mutation(tmp_path: Path) -> None:
    from tools.tradebot_mcp.core import GATE_REQUIREMENTS

    root = tmp_path / "repo"
    (root / "runtime").mkdir(parents=True)
    (root / "research").mkdir()
    evidence = _write_gate_evidence(root, "determinism", GATE_REQUIREMENTS["determinism"])
    service = GateService(_settings(root))

    assert service.evaluate("determinism", str(evidence))["verdict"] == "PASS"
    (root / "evidence" / "artifact.json").write_text('{"ok":false}', encoding="utf-8")
    result = service.evaluate("determinism", str(evidence))
    assert result["verdict"] == "FAIL"
    assert any("hash mismatch" in failure for failure in result["failures"])


def test_gate_service_rejects_missing_check(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "runtime").mkdir(parents=True)
    (root / "research").mkdir()
    evidence = _write_gate_evidence(root, "determinism", ("run_a_hash",))
    result = GateService(_settings(root)).evaluate("determinism", str(evidence))
    assert result["verdict"] == "FAIL"
    assert any("missing check" in failure for failure in result["failures"])


def test_git_audit_checks_scope_and_rejects_option_injection(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "runtime").mkdir()
    (root / "research").mkdir()
    (root / "allowed").mkdir()
    (root / "allowed" / "base.txt").write_text("base", encoding="utf-8")
    subprocess.run(["git", "add", "allowed/base.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=root, check=True, capture_output=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    (root / "allowed" / "next.txt").write_text("next", encoding="utf-8")
    subprocess.run(["git", "add", "allowed/next.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "next"], cwd=root, check=True, capture_output=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()

    service = SafeGitAuditService(_settings(root))
    scope = service.verify_commit_scope(base, head, ["allowed/"])

    assert scope["passes"]
    assert service.check_worktree_clean()["clean"]
    assert service.get_branch_head("HEAD")["sha"] == head
    with pytest.raises(SafetyError):
        service.get_branch_head("--help")
