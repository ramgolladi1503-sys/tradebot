from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.agentic_qa.adapter import build_agentic_qa_bundle, build_agentic_qa_evidence
from core.agentic_qa.agents import DeterministicCritic, validate_advisory_review
from core.agentic_qa.catalog import CONTROL_CATALOG
from core.agentic_qa.contracts import AuditVerdict, ControlStatus
from core.agentic_qa.engine import AgenticQAAuditor
from core.agentic_qa.evaluation import evaluate_agent_guardrails


def complete_evidence() -> dict:
    return {
        "execution_context": {"isolated": True},
        "authority": {
            "read_only": True,
            "no_broker_tools": True,
            "no_live_runtime_mutation": True,
            "verdict_owner": "deterministic",
            "agent_advisory_only": True,
        },
        "security": {"tool_allowlist_enforced": True},
        "governance": {
            "human_approval_required": True,
            "append_only_ledger": True,
            "restart_safe_checkpointing": True,
            "manual_promotion_approval": True,
            "role_separation": True,
            "failure_taxonomy_present": True,
            "report_schema_complete": True,
            "ci_gate_present": True,
            "reproducible_cli": True,
            "truthful_non_claims": True,
        },
        "provenance": {
            "config_sha256": "c" * 64,
            "dataset_sha256": "d" * 64,
            "execution_context_complete": True,
        },
        "temporal": {
            "timezone_explicit": True,
            "signal_after_entry_count": 0,
            "same_event_entry_count": 0,
            "future_feature_access_count": 0,
        },
        "validation": {
            "split_boundaries_valid": True,
            "preprocessing_train_only": True,
            "out_of_sample_present": True,
            "walk_forward_present": True,
            "repeated_holdout_use_count": 0,
        },
        "data": {
            "point_in_time_universe": True,
            "corporate_actions_handled": True,
            "stale_quote_policy_enforced": True,
            "sequence_quality_passed": True,
        },
        "execution": {
            "fees_included": True,
            "spread_modeled": True,
            "slippage_modeled": True,
            "latency_modeled": True,
            "partial_fills_modeled": True,
            "liquidity_constraints_enforced": True,
            "rejections_modeled": True,
        },
        "risk": {
            "position_sizing_deterministic": True,
            "exposure_limits_enforced": True,
            "kill_switch_tested": True,
        },
        "robustness": {
            "parameter_perturbation_passed": True,
            "cost_stress_passed": True,
            "delayed_entry_passed": True,
            "regime_segmentation_present": True,
            "instrument_generalization_passed": True,
            "best_trade_removal_passed": True,
            "negative_controls_passed": True,
        },
        "agent": {
            "structured_output_enforced": True,
            "citations_resolve": True,
            "fabricated_metric_count": 0,
            "verdict_agreement": True,
            "uncertainty_disclosed": True,
            "prompt_injection_tests_passed": True,
            "tool_policy_passed": True,
            "provenance_complete": True,
            "prompt_regression_passed": True,
            "scorecard_passed": True,
        },
    }


def build_bundle(root: Path, *, mutate=None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    evidence = complete_evidence()
    if mutate:
        mutate(evidence)
    evidence_path = root / "agentic_qa_evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    manifest = {
        "schema_version": "tradebot-evidence/v1",
        "run_id": "run-001",
        "trace_id": "trace-001",
        "policy_version": "agentic-qa-policy/v1",
        "repository_commit": "5d93b51fa74d58ad80751211ca8cf1c6d814c60d",
        "artifacts": {
            "agentic_qa_evidence": {
                "path": "agentic_qa_evidence.json",
                "sha256": digest,
            }
        },
    }
    (root / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return root


def test_catalog_has_exactly_70_contiguous_controls():
    assert [item.control_id for item in CONTROL_CATALOG] == [f"AQ-{index:02d}" for index in range(1, 71)]


def test_every_control_has_explicit_policy_metadata():
    for item in CONTROL_CATALOG:
        assert item.domain and item.title and item.description and item.key
        assert item.rule in {"is_true", "equals", "nonempty", "zero", "min"}


def test_complete_bundle_passes_all_70_controls(tmp_path: Path):
    report = AgenticQAAuditor().audit_bundle(build_bundle(tmp_path / "bundle"))
    assert report.verdict is AuditVerdict.CONTROL_PLANE_CERTIFIED
    assert report.passed == 70
    assert report.deterministic_score == 10.0


def test_lookahead_is_hard_rejected(tmp_path: Path):
    def mutate(evidence):
        evidence["temporal"]["future_feature_access_count"] = 1

    report = AgenticQAAuditor().audit_bundle(build_bundle(tmp_path / "bundle", mutate=mutate))
    assert report.verdict is AuditVerdict.REJECTED
    assert next(item for item in report.controls if item.control_id == "AQ-24").status is ControlStatus.FAIL


def test_missing_mandatory_evidence_withholds_certification(tmp_path: Path):
    def mutate(evidence):
        del evidence["validation"]["walk_forward_present"]

    report = AgenticQAAuditor().audit_bundle(build_bundle(tmp_path / "bundle", mutate=mutate))
    assert report.verdict is AuditVerdict.INSUFFICIENT_EVIDENCE
    assert next(item for item in report.controls if item.control_id == "AQ-42").status is ControlStatus.INSUFFICIENT


def test_hash_tampering_is_rejected(tmp_path: Path):
    root = build_bundle(tmp_path / "bundle")
    evidence_path = root / "agentic_qa_evidence.json"
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["risk"]["kill_switch_tested"] = False
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    report = AgenticQAAuditor().audit_bundle(root)
    assert next(item for item in report.controls if item.control_id == "AQ-15").status is ControlStatus.FAIL
    assert report.verdict is AuditVerdict.REJECTED


def test_unsafe_artifact_path_is_rejected(tmp_path: Path):
    root = build_bundle(tmp_path / "bundle")
    manifest_path = root / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["escape"] = {"path": "../secret.json", "sha256": "x" * 64}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    report = AgenticQAAuditor().audit_bundle(root)
    assert next(item for item in report.controls if item.control_id == "AQ-13").status is ControlStatus.FAIL
    assert report.verdict is AuditVerdict.REJECTED


def test_deterministic_critic_review_is_accepted(tmp_path: Path):
    report = AgenticQAAuditor().audit_bundle(build_bundle(tmp_path / "bundle"))
    outcome = validate_advisory_review(report, DeterministicCritic().review(report.to_dict()))
    assert outcome.accepted is True


def test_agent_cannot_override_deterministic_verdict(tmp_path: Path):
    report = AgenticQAAuditor().audit_bundle(build_bundle(tmp_path / "bundle"))
    review = DeterministicCritic().review(report.to_dict())
    review["deterministic_verdict"] = "REJECTED"
    outcome = validate_advisory_review(report, review)
    assert outcome.accepted is False
    assert outcome.reason_code == "AGENT_VERDICT_OVERRIDE_ATTEMPT"


def test_agent_citations_must_resolve(tmp_path: Path):
    report = AgenticQAAuditor().audit_bundle(build_bundle(tmp_path / "bundle"))
    review = DeterministicCritic().review(report.to_dict())
    review["evidence_citations"] = ["made-up-profit.csv"]
    outcome = validate_advisory_review(report, review)
    assert outcome.accepted is False
    assert outcome.reason_code == "AGENT_CITATIONS_UNRESOLVED"


def test_all_adversarial_agent_cases_are_rejected_for_expected_reason(tmp_path: Path):
    report = AgenticQAAuditor().audit_bundle(build_bundle(tmp_path / "bundle"))
    baseline = DeterministicCritic().review(report.to_dict())
    result = evaluate_agent_guardrails(report, baseline)
    assert result["cases"] == 5
    assert result["passed"] == 5
    assert result["accuracy"] == 1.0
    assert result["unsafe_acceptances"] == 0


def test_adapter_maps_real_exporter_artifacts_without_inventing_missing_controls(tmp_path: Path):
    artifacts = {
        "engine_identity.json": {"read_only": True, "broker_api_called": False},
        "run_configuration.json": {
            "frozen_config_hash": "c" * 64,
            "timezone": "Asia/Kolkata",
            "cost_model_version": "cost-v1",
        },
        "dataset_manifest.json": {
            "dataset_sha256": "d" * 64,
            "time_start": "2025-01-01T09:15:00+05:30",
            "time_end": "2025-06-30T15:30:00+05:30",
            "duplicate_timestamp_count": 0,
            "missing_timestamp_count": 0,
            "malformed_timestamp_count": 0,
            "stale_quote_count": 0,
            "post_expiry_row_count": 0,
            "invalid_ohlc_count": 0,
            "quote_columns_complete": True,
        },
        "timing_evidence.json": {
            "same_event_entry_count": 0,
            "chronology_violation_count": 0,
            "future_data_dependency_count": 0,
        },
        "fill_evidence.json": {
            "entries_use_executable_side": True,
            "exits_use_executable_side": True,
            "strict_liquidity_mode": True,
            "fallback_liquidity_fill_count": 0,
            "proxy_exit_mark_count": 0,
            "missing_bid_ask_accepted_count": 0,
            "synthetic_liquidity_fill_count": 0,
        },
        "cost_reconciliation.json": {"gross_pnl": 10.0, "total_costs": 2.0, "net_pnl": 8.0},
        "wfa_partition_plan.json": {
            "chronological": True,
            "non_overlapping": True,
            "purge_embargo_applied": True,
            "validation_before_holdout": True,
            "holdout_isolated_from_selection": True,
        },
        "wfa_results.json": {"repeated_holdout_run_count": 0, "holdout_status": "completed"},
        "negative_controls.json": {
            "controls": {"future_mutation": True, "timing_shift": True, "cost_sensitivity": True}
        },
        "test_results.json": {
            "collected": 12,
            "failed": 0,
            "errors": 0,
            "commit_matches_bundle": True,
        },
    }
    manifest_artifacts = {}
    for name, payload in artifacts.items():
        path = tmp_path / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        manifest_artifacts[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "run_id": "bundle-1",
        "repository_commit": "abc1234",
        "policy_version": "backtest-certification-v1",
        "artifacts": manifest_artifacts,
    }
    (tmp_path / "bundle_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    evidence = build_agentic_qa_evidence(tmp_path)

    assert evidence["temporal"]["same_event_entry_count"] == 0
    assert evidence["execution"]["fees_included"] is True
    assert evidence["execution"]["liquidity_constraints_enforced"] is True
    assert evidence["validation"]["walk_forward_present"] is True
    assert evidence["robustness"]["negative_controls_passed"] is True
    assert "slippage_modeled" not in evidence.get("execution", {})
    assert "corporate_actions_handled" not in evidence.get("data", {})


def test_adapter_builds_hashed_sidecar_without_mutating_source(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    report_path = source / "certification_report.json"
    report_path.write_text(json.dumps({"evidence_certification": "CERTIFIED", "gates": {}}), encoding="utf-8")
    source_manifest = {
        "run_id": "source-run",
        "repository_commit": "abc1234",
        "policy_version": "backtest-certification-v1",
        "artifacts": {report_path.name: hashlib.sha256(report_path.read_bytes()).hexdigest()},
    }
    manifest_path = source / "bundle_manifest.json"
    manifest_path.write_text(json.dumps(source_manifest), encoding="utf-8")
    before = manifest_path.read_bytes()

    sidecar = build_agentic_qa_bundle(source, tmp_path / "sidecar")

    assert manifest_path.read_bytes() == before
    sidecar_manifest = json.loads((sidecar / "run_manifest.json").read_text(encoding="utf-8"))
    assert sidecar_manifest["source_bundle_digest"]
    assert sidecar_manifest["artifacts"]["agentic_qa_evidence.json"] == hashlib.sha256(
        (sidecar / "agentic_qa_evidence.json").read_bytes()
    ).hexdigest()
