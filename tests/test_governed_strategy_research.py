from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core.governed_strategy_research_supervised import (
    AgentRole,
    GovernedResearchStore,
    MANDATORY_GATES,
    ResearchError,
    ResearchState,
    build_validation_payload,
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_supervisor_implementation(
    store: GovernedResearchStore,
    changed_paths: list[str],
) -> tuple[str, str]:
    path = store.root / "supervisor" / "implementation_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "task_id": "opening-state-v1",
        "state": "VERIFIED",
        "base_commit": "a" * 40,
        "head_commit": "b" * 40,
        "branch": "research/opening-state-v1",
        "changed_paths": sorted(set(changed_paths)),
        "safety": {
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        },
    }
    payload["manifest_sha256"] = manifest_hash(payload)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path.relative_to(store.root).as_posix(), file_sha256(path)


def write_supervisor_review(
    store: GovernedResearchStore,
    decision: str = "APPROVE",
) -> tuple[str, str]:
    path = store.root / "supervisor" / "review_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    implementation_manifest = json.loads(
        (store.root / "supervisor" / "implementation_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    payload = {
        "schema_version": 1,
        "reviewer": "antigravity",
        "implementer": "codex",
        "decision": decision,
        "implementation_manifest_sha256": implementation_manifest[
            "manifest_sha256"
        ],
        "blockers": [],
    }
    payload["manifest_sha256"] = manifest_hash(payload)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path.relative_to(store.root).as_posix(), file_sha256(path)


def hypothesis() -> dict:
    return {
        "thesis": "Opening-state continuation persists after causal confirmation.",
        "market": "NIFTY",
        "timeframe": "5m",
        "data_universe": "completed underlying candles plus executable option quotes",
        "development_window": "2023-01-01/2025-12-31",
        "holdout_window": "2026-01-01/2026-06-30",
        "signal_definition": "gap acceptance then first pullback hold",
        "entry_rule": "next completed bar open after confirmation",
        "exit_rule": "fixed causal stop/target or 30 minute timeout",
        "cost_model": "brokerage, taxes, spread and slippage",
        "negative_controls": ["timestamp permutation", "direction inversion"],
        "primary_metric": "net expectancy with drawdown guardrail",
        "rejection_criteria": "reject if WFA or untouched holdout fails",
    }


def init_store(tmp_path: Path) -> GovernedResearchStore:
    return GovernedResearchStore.initialize(
        tmp_path / "run",
        strategy_id="opening_state_v1",
        title="Opening state research",
        objective="Test one frozen causal structure",
    )


def implementation_payload(store: GovernedResearchStore) -> dict:
    status = store.status()
    changed_paths = [
        "research/opening_state_v1/strategy.py",
        "tests/test_opening_state_v1.py",
    ]
    supervisor_manifest, supervisor_file_hash = write_supervisor_implementation(
        store,
        changed_paths,
    )
    return {
        "agent": "codex",
        "hypothesis_sha256": status.hypothesis_sha256,
        "base_commit": "a" * 40,
        "head_commit": "b" * 40,
        "branch": "research/opening-state-v1",
        "changed_paths": changed_paths,
        "test_results": [
            {
                "name": "focused",
                "exit_code": 0,
                "command": ["python", "-m", "pytest"],
            }
        ],
        "artifacts": ["research/opening_state_v1/manifest.json"],
        "supervisor_manifest": supervisor_manifest,
        "supervisor_manifest_file_sha256": supervisor_file_hash,
    }


def review_payload(
    store: GovernedResearchStore,
    decision: str = "APPROVE",
) -> dict:
    status = store.status()
    supervisor_review, supervisor_file_hash = write_supervisor_review(store, decision)
    return {
        "agent": "antigravity",
        "decision": decision,
        "summary": "Independent reproduction passed and no leakage was found.",
        "implementation_sha256": status.implementation_sha256,
        "reproduction_results": [{"name": "focused", "exit_code": 0}],
        "findings": [],
        "supervisor_review_manifest": supervisor_review,
        "supervisor_review_manifest_file_sha256": supervisor_file_hash,
    }


def advance_to_audited(store: GovernedResearchStore) -> None:
    store.freeze_hypothesis(hypothesis())
    store.record_implementation(implementation_payload(store))
    store.record_review(review_payload(store))


def make_gate_artifacts(store: GovernedResearchStore) -> dict:
    artifacts = {}
    for gate in MANDATORY_GATES:
        path = store.root / "gate_artifacts" / f"{gate}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"gate": gate, "passed": True}),
            encoding="utf-8",
        )
        artifacts[gate] = path
    return build_validation_payload(store, artifacts)


def test_initialization_is_paper_and_live_ineligible(tmp_path: Path):
    status = init_store(tmp_path).status()
    assert status.state == ResearchState.INTAKE.value
    assert status.allowed_for_paper is False
    assert status.allowed_for_live_execution is False
    assert status.integrity_ok is True


def test_freeze_requires_complete_pre_outcome_contract(tmp_path: Path):
    store = init_store(tmp_path)
    bad = hypothesis()
    bad.pop("rejection_criteria")
    with pytest.raises(
        ResearchError,
        match="missing_hypothesis_field:rejection_criteria",
    ):
        store.freeze_hypothesis(bad)


def test_freeze_requires_at_least_two_negative_controls(tmp_path: Path):
    store = init_store(tmp_path)
    bad = hypothesis()
    bad["negative_controls"] = ["one control"]
    with pytest.raises(
        ResearchError,
        match="at_least_two_negative_controls_required",
    ):
        store.freeze_hypothesis(bad)


def test_implementation_cannot_precede_freeze(tmp_path: Path):
    store = init_store(tmp_path)
    with pytest.raises(
        ResearchError,
        match="implementation_requires_frozen_hypothesis",
    ):
        store.record_implementation({})


def test_codex_packet_requires_frozen_hypothesis(tmp_path: Path):
    store = init_store(tmp_path)
    with pytest.raises(
        ResearchError,
        match="implementer_packet_requires_frozen_hypothesis",
    ):
        store.build_agent_packet(agent="codex", role=AgentRole.IMPLEMENTER)
    store.freeze_hypothesis(hypothesis())
    packet_path = store.build_agent_packet(
        agent="codex",
        role=AgentRole.IMPLEMENTER,
    )
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["agent"] == "codex"
    assert packet["safety"]["allowed_for_live_execution"] is False
    assert any("Do not call brokers" in line for line in packet["instructions"])


def test_forbidden_runtime_paths_block_implementation(tmp_path: Path):
    store = init_store(tmp_path)
    store.freeze_hypothesis(hypothesis())
    payload = implementation_payload(store)
    payload["changed_paths"].append("core/execution_engine.py")
    with pytest.raises(ResearchError, match="forbidden_implementation_paths"):
        store.record_implementation(payload)


def test_tampered_supervisor_manifest_blocks_implementation(tmp_path: Path):
    store = init_store(tmp_path)
    store.freeze_hypothesis(hypothesis())
    payload = implementation_payload(store)
    path = store.root / payload["supervisor_manifest"]
    path.write_text("tampered", encoding="utf-8")
    with pytest.raises(
        ResearchError,
        match="supervisor_manifest_file_hash_mismatch",
    ):
        store.record_implementation(payload)


def test_implementer_cannot_self_review(tmp_path: Path):
    store = init_store(tmp_path)
    store.freeze_hypothesis(hypothesis())
    store.record_implementation(implementation_payload(store))
    payload = review_payload(store)
    payload["agent"] = "codex"
    with pytest.raises(ResearchError, match="reviewer_identity_mismatch"):
        store.record_review(payload)


def test_antigravity_rewrite_returns_to_refreeze_boundary(tmp_path: Path):
    store = init_store(tmp_path)
    store.freeze_hypothesis(hypothesis())
    store.record_implementation(implementation_payload(store))
    payload = review_payload(store, "REWRITE")
    payload["summary"] = "Timestamp semantics are insufficient."
    store.record_review(payload)
    status = store.status()
    assert status.state == ResearchState.REVIEW_REWRITE.value
    assert status.implementation_sha256 is None
    assert status.allowed_for_paper is False


def test_missing_validation_gate_fails_closed(tmp_path: Path):
    store = init_store(tmp_path)
    advance_to_audited(store)
    payload = make_gate_artifacts(store)
    payload["gates"].pop("untouched_holdout")
    result = store.record_validation(payload)
    assert "gate_missing:untouched_holdout" in result["blockers"]
    assert store.status().state == ResearchState.VALIDATION_FAILED.value
    with pytest.raises(
        ResearchError,
        match="paper_approval_requires_validated_research",
    ):
        store.approve_paper(approved_by="Ram")


def test_tampered_gate_artifact_fails_hash_verification(tmp_path: Path):
    store = init_store(tmp_path)
    advance_to_audited(store)
    payload = make_gate_artifacts(store)
    artifact = store.root / payload["gates"]["causal_timestamps"]["artifact"]
    artifact.write_text("tampered", encoding="utf-8")
    result = store.record_validation(payload)
    assert "gate_artifact_hash_mismatch:causal_timestamps" in result["blockers"]


def test_full_governed_path_allows_paper_only(tmp_path: Path):
    store = init_store(tmp_path)
    advance_to_audited(store)
    result = store.record_validation(make_gate_artifacts(store))
    assert result["blockers"] == []
    assert store.status().state == ResearchState.VALIDATED.value
    status = store.approve_paper(approved_by="Ram")
    assert status.state == ResearchState.PAPER_ELIGIBLE.value
    assert status.allowed_for_paper is True
    assert status.allowed_for_live_execution is False
    assert status.integrity_ok is True


def test_frozen_hypothesis_tampering_is_detected(tmp_path: Path):
    store = init_store(tmp_path)
    store.freeze_hypothesis(hypothesis())
    payload = json.loads(store.hypothesis_path.read_text(encoding="utf-8"))
    payload["entry_rule"] = "same bar close after seeing outcome"
    store.hypothesis_path.write_text(json.dumps(payload), encoding="utf-8")
    status = store.status()
    assert status.integrity_ok is False
    assert "frozen_hypothesis_hash_invalid" in status.blockers


def test_rehashed_forged_supervisor_manifest_is_rejected(tmp_path: Path):
    store = init_store(tmp_path)
    store.freeze_hypothesis(hypothesis())
    payload = implementation_payload(store)
    path = store.root / payload["supervisor_manifest"]
    forged = json.loads(path.read_text(encoding="utf-8"))
    forged["state"] = "VERIFIED"
    forged["manifest_sha256"] = "0" * 64
    path.write_text(json.dumps(forged, sort_keys=True), encoding="utf-8")
    payload["supervisor_manifest_file_sha256"] = file_sha256(path)
    with pytest.raises(
        ResearchError,
        match="supervisor_manifest_internal_hash_invalid",
    ):
        store.record_implementation(payload)
