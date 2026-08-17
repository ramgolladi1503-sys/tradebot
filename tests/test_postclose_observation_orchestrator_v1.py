from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "research" / "run_postclose_observation_orchestrator_v1.py"
spec = importlib.util.spec_from_file_location("postclose_orchestrator_v1", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_authority_constants_are_exact_and_frozen():
    assert mod.FROZEN_PRODUCER_SHA == "f0f5b3d3659415ab36662291e91b8f57fd8d1e07"
    assert mod.SUBSCRIPTION_TOOL_SHA == "21f95a8b5908a8f6b9a0d7bbf459877efed41262"
    assert mod.KERNEL_TOOL_SHA == "10d2f68b08026a269e9c25095bebca683ada67e5"
    assert mod.KERNEL_BASE_SHA == "46dd4f7df9b63486eb633a12baf25412cd4f761d"


def test_exact_sha_rejects_symbolic_refs():
    with pytest.raises(mod.OrchestrationError, match="EXACT_SHA_REQUIRED"):
        mod._exact_sha("main", "TEST")


def test_invalid_observation_date_rejected():
    with pytest.raises(mod.OrchestrationError, match="OBSERVATION_DATE_INVALID"):
        mod._parse_date("2026-02-30")


def test_regular_file_rejects_symlink(tmp_path: Path):
    target = tmp_path / "truth.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(mod.OrchestrationError, match="REGULAR_FILE_REQUIRED"):
        mod._regular_file(link, "INPUT")


def test_run_fails_closed_on_nonzero_stage(monkeypatch: pytest.MonkeyPatch):
    class R:
        returncode = 2
        stdout = ""
        stderr = "failed"

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: R())
    with pytest.raises(mod.OrchestrationError, match="TEST_STAGE_FAILED_RC_2"):
        mod._run(["python", "validator.py"], "TEST_STAGE")


def test_unknown_stages_remain_unknown_when_inputs_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    producer = tmp_path / "producer"
    subscription = tmp_path / "subscription"
    kernel = tmp_path / "kernel"
    runtime = tmp_path / "runtime"
    for p in (producer, subscription, kernel, runtime):
        p.mkdir(exist_ok=True)

    for root, rel in (
        (subscription, mod.SUBSCRIPTION_REL),
        (kernel, mod.SEALER_REL),
        (kernel, mod.INGESTOR_REL),
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixture\n", encoding="utf-8")

    def fake_verify(worktree: Path, expected_sha: str, label: str):
        sha = {
            "PRODUCER": mod.FROZEN_PRODUCER_SHA,
            "SUBSCRIPTION_TOOL": mod.SUBSCRIPTION_TOOL_SHA,
            "KERNEL_TOOL": mod.KERNEL_TOOL_SHA,
        }[label]
        assert expected_sha == sha
        return {"worktree": str(worktree.resolve()), "git_sha": sha, "git_clean": True, "branch": "fixture"}

    monkeypatch.setattr(mod, "verify_clean_worktree", fake_verify)

    report_path = runtime / "report.json"
    report = mod.orchestrate(
        producer_worktree=producer,
        runtime_root=runtime,
        observation_date="2026-08-18",
        subscription_worktree=subscription,
        kernel_worktree=kernel,
        subscription_inputs=[],
        artifact_specs=[],
        report_path=report_path,
    )

    assert report["stages"]["subscription_reconciliation"]["status"] == "UNKNOWN_NOT_SUPPLIED"
    assert report["stages"]["bundle_seal"]["status"] == "UNKNOWN_NOT_SUPPLIED"
    assert report["stages"]["kernel_ingestion"]["status"] == "UNKNOWN_NOT_RUN"
    assert report["prospective_supported"] is False
    assert report["structural_edge_certified"] is False
    assert report["broker_write_authority"] is False
    assert report["order_authority"] is False
    assert report_path.exists()
    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted["stages"]["kernel_ingestion"]["status"] == "UNKNOWN_NOT_RUN"


def test_runtime_root_inside_any_repo_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    producer = tmp_path / "producer"
    subscription = tmp_path / "subscription"
    kernel = tmp_path / "kernel"
    for p in (producer, subscription, kernel):
        p.mkdir(exist_ok=True)
    runtime = producer / "runtime"
    runtime.mkdir(exist_ok=True)

    def fake_verify(worktree: Path, expected_sha: str, label: str):
        return {"worktree": str(worktree.resolve()), "git_sha": expected_sha, "git_clean": True, "branch": "fixture"}

    monkeypatch.setattr(mod, "verify_clean_worktree", fake_verify)

    with pytest.raises(mod.OrchestrationError, match="RUNTIME_ROOT_INSIDE_PRODUCER_REPO"):
        mod.orchestrate(
            producer_worktree=producer,
            runtime_root=runtime,
            observation_date="2026-08-18",
            subscription_worktree=subscription,
            kernel_worktree=kernel,
            subscription_inputs=[],
            artifact_specs=[],
            report_path=runtime / "report.json",
        )


def test_report_is_write_once(tmp_path: Path):
    path = tmp_path / "report.json"
    mod._write_once(path, {"x": 1})
    with pytest.raises(mod.OrchestrationError, match="REPORT_ALREADY_EXISTS"):
        mod._write_once(path, {"x": 2})
