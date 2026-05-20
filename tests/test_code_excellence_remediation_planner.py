from __future__ import annotations

import json

import pytest

from tools.code_excellence.remediation_planner import (
    RemediationPlannerError,
    parse_finding_clusters,
    plan_remediation,
    render_remediation_report,
)
from tools.repo_forensics.config_loader import ConfigError


def _config_text(*, include_accepted_unknown: bool = True) -> str:
    accepted_unknown = "      - ACCEPTED_UNKNOWN\n" if include_accepted_unknown else ""
    return f"""
gsd_forensics_config_version: 1
project:
  name: tradebot
baseline_rules:
  no_target_runtime_execution: true
entrypoints:
  required:
    - main.py
  optional:
    - scripts/run_paper_replay.py
critical_modules:
  runtime:
    - main.py
    - core/orchestrator.py
  execution_boundary:
    - core/kite_client.py
    - core/execution_engine.py
  evidence:
    - core/decision_logger.py
agent_parameters:
  ariadne:
    mission: root_cause_investigator
    input_sources:
      - repo_forensics_report
    cluster_signals:
      - same_file
    confidence_levels:
      - CONFIRMED
      - LIKELY
      - POSSIBLE
      - UNKNOWN
    output_required:
      - finding_cluster
  daedalus:
    mission: remediation_architect
    decisions:
      - FIX_NOW
      - BACKLOG
      - DEFER
      - FALSE_POSITIVE
{accepted_unknown}    required_contract_fields:
      - root_cause
      - decision
      - files_to_change
      - files_not_to_touch
      - patch_behavior
      - tests_required
      - negative_tests_required
      - evidence_required
      - regression_risks
      - done_means
    block_on:
      - no_root_cause
      - no_non_touch_list
      - broad_fix
      - missing_negative_tests
    output_required:
      - scoped_pr_contract
      - priority
      - proof_required
  vulcan:
    mission: production_hardening_from_scoped_contract
    allowed_only_after:
      - daedalus_contract
    hardening_targets:
      - safe_defaults
    forbidden_actions:
      - broad_repo_rewrite
    output_required:
      - maturity_before
  minerva:
    mission: test_reality_classifier
    classes:
      - SAFETY_REGRESSION
      - EVIDENCE_CONTRACT
      - INTEGRATION_WIRING
    weak_test_patterns:
      - shape_only
    required_negative_tests:
      - fallback_candidate_cannot_be_executable
      - stale_feed_blocks_order_intent
      - paper_path_cannot_call_live_broker
      - missing_evidence_field_fails_contract
    output_required:
      - test_classification_summary
  cerberus:
    mission: sim_paper_live_safety_boundary_guard
    protected_modes:
      - PAPER
    forbidden_import_markers:
      - place_order
    required_non_action_fields:
      - is_order_action=false
      - broker_api_called=false
      - live_order_action=false
      - broker_order_action=false
    block_on:
      - read_only_sets_order_action_true
    output_required:
      - safety_boundary_status
"""


def _write_config(tmp_path, *, include_accepted_unknown: bool = True):
    path = tmp_path / ".gsd-forensics.yaml"
    path.write_text(_config_text(include_accepted_unknown=include_accepted_unknown), encoding="utf-8")
    return path


def test_planner_generates_fix_now_from_normalized_ariadne_findings(tmp_path):
    config = _write_config(tmp_path)
    source = tmp_path / "findings.json"
    source.write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "finding_id": "F-001",
                        "source": {"source_type": "repo_forensics"},
                        "classification": {
                            "finding_type": "safety_boundary",
                            "severity": "high",
                            "confidence": "high",
                            "root_cause_family": "fallback_execution_boundary",
                        },
                        "summary": {
                            "title": "Fallback candidate can reach executable boundary",
                            "observed_behavior": "fallback state can be ranked as executable",
                            "expected_behavior": "fallback state remains advisory only",
                        },
                        "location": {"files": ["core/decision_builder.py"]},
                        "relationships": {},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = plan_remediation(source_path=source, config_path=config)

    assert report.total_plans == 1
    plan = report.plans[0]
    assert plan.decision == "FIX_NOW"
    assert plan.status == "draft"
    assert plan.priority == "P1"
    assert plan.files_to_change == ("core/decision_builder.py",)
    assert "core/kite_client.py" in plan.files_not_to_touch
    assert "fallback_candidate_cannot_be_executable" in plan.negative_tests_required
    assert "is_order_action=false" in plan.evidence_required
    assert "repo-forensics-pr-gate" in plan.proof_required


def test_planner_blocks_cluster_without_root_cause(tmp_path):
    config = _write_config(tmp_path)
    source = tmp_path / "clusters.json"
    source.write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "cluster_id": "C-001",
                        "title": "Unknown execution failure",
                        "severity": "high",
                        "confidence_level": "LIKELY",
                        "affected_files": ["core/execution_engine.py"],
                        "tags": ["execution"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = plan_remediation(source_path=source, config_path=config)

    plan = report.plans[0]
    assert plan.status == "blocked"
    assert plan.decision == "ACCEPTED_UNKNOWN"
    assert "no_root_cause" in plan.block_reasons
    assert "missing_negative_tests" in plan.block_reasons
    assert plan.patch_behavior == "No implementation patch approved by this plan."
    assert plan.done_means == ("decision_recorded_with_reason", "no_product_code_changed")


def test_planner_report_is_deterministically_ordered_by_cluster_id(tmp_path):
    config = _write_config(tmp_path)
    source = tmp_path / "clusters.json"
    source.write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "cluster_id": "B-CLUSTER",
                        "title": "Backlog evidence issue",
                        "severity": "medium",
                        "confidence_level": "CONFIRMED",
                        "root_cause": "missing evidence field",
                        "affected_files": ["core/decision_logger.py"],
                    },
                    {
                        "cluster_id": "A-CLUSTER",
                        "title": "Low priority doc issue",
                        "severity": "low",
                        "confidence_level": "CONFIRMED",
                        "root_cause": "stale doc claim",
                        "affected_files": ["docs/runbook.md"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = plan_remediation(source_path=source, config_path=config)
    rendered = render_remediation_report(report)

    assert [plan.source_cluster_id for plan in report.plans] == ["A-CLUSTER", "B-CLUSTER"]
    assert "## CE-DAEDALUS-0001 — Low priority doc issue" in rendered
    assert "## CE-DAEDALUS-0002 — Backlog evidence issue" in rendered


def test_parse_finding_clusters_rejects_empty_payload():
    with pytest.raises(RemediationPlannerError, match="remediation_source_has_no_clusters_or_findings"):
        parse_finding_clusters({"clusters": []})


def test_planner_fails_closed_when_required_decision_is_not_configured(tmp_path):
    config = _write_config(tmp_path, include_accepted_unknown=False)
    source = tmp_path / "clusters.json"
    source.write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "cluster_id": "C-001",
                        "title": "Unknown root cause",
                        "severity": "high",
                        "confidence_level": "UNKNOWN",
                        "affected_files": ["core/execution_engine.py"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="daedalus_decision_not_configured decision=ACCEPTED_UNKNOWN"):
        plan_remediation(source_path=source, config_path=config)
