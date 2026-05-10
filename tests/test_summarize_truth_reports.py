from __future__ import annotations

import json

from scripts.summarize_truth_reports import build_summary, main


def test_build_summary_blocks_merge_when_reports_have_dirty_or_shadow_drifts(tmp_path):
    candidate = tmp_path / "candidate.json"
    opportunity = tmp_path / "opportunity.json"
    shadow = tmp_path / "shadow.json"
    candidate.write_text(
        json.dumps({"summary": {"total_candidates": 2, "dirty_selected_or_executable": 1}}),
        encoding="utf-8",
    )
    opportunity.write_text(
        json.dumps({"candidate_count_after_merge": 2, "truth_report": {"summary": {"dirty_selected_or_executable": 0}}}),
        encoding="utf-8",
    )
    shadow.write_text(
        json.dumps({"mode": "SHADOW_ONLY", "behavior_changed": False, "total_candidates": 2, "severity_counts": {"CRITICAL": 1, "HIGH": 0}, "drift_counts": {"CURRENT_ALLOWS_SHADOW_BLOCKS": 1}}),
        encoding="utf-8",
    )

    summary = build_summary(
        {
            "candidate_truth": candidate,
            "opportunity_truth": opportunity,
            "shadow_truth": shadow,
        }
    )

    assert summary["merge_blocked"] is True
    assert "candidate_truth_dirty_selected" in summary["merge_blockers"]
    assert "shadow_critical_drift" in summary["merge_blockers"]


def test_summary_cli_can_fail_if_blocked(tmp_path):
    candidate = tmp_path / "candidate.json"
    opportunity = tmp_path / "opportunity.json"
    shadow = tmp_path / "shadow.json"
    candidate.write_text(json.dumps({"summary": {"dirty_selected_or_executable": 0}}), encoding="utf-8")
    opportunity.write_text(json.dumps({"truth_report": {"summary": {"dirty_selected_or_executable": 0}}}), encoding="utf-8")
    shadow.write_text(json.dumps({"mode": "SHADOW_ONLY", "behavior_changed": False, "severity_counts": {"CRITICAL": 0, "HIGH": 1}, "drift_counts": {"EXECUTION_ALLOWED_SHADOW_BLOCKS": 1}}), encoding="utf-8")

    code = main(
        [
            "--candidate-truth",
            str(candidate),
            "--opportunity-truth",
            str(opportunity),
            "--shadow-truth",
            str(shadow),
            "--fail-if-blocked",
        ]
    )

    assert code == 1


def test_summary_cli_passes_when_clean(tmp_path):
    candidate = tmp_path / "candidate.json"
    opportunity = tmp_path / "opportunity.json"
    shadow = tmp_path / "shadow.json"
    candidate.write_text(json.dumps({"summary": {"dirty_selected_or_executable": 0}}), encoding="utf-8")
    opportunity.write_text(json.dumps({"truth_report": {"summary": {"dirty_selected_or_executable": 0}}}), encoding="utf-8")
    shadow.write_text(json.dumps({"mode": "SHADOW_ONLY", "behavior_changed": False, "severity_counts": {"CRITICAL": 0, "HIGH": 0}, "drift_counts": {}}), encoding="utf-8")

    code = main(
        [
            "--candidate-truth",
            str(candidate),
            "--opportunity-truth",
            str(opportunity),
            "--shadow-truth",
            str(shadow),
            "--fail-if-blocked",
        ]
    )

    assert code == 0
