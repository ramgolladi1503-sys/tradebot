from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_candidate_truth import build_truth_report, main


def test_build_truth_report_flags_dirty_selected_candidate():
    fixture = Path("tests/fixtures/candidates_truth_sample.json")
    candidates = json.loads(fixture.read_text(encoding="utf-8"))

    report = build_truth_report(candidates, source=str(fixture))

    assert report["summary"]["total_candidates"] == 3
    assert report["summary"]["dirty_selected_or_executable"] == 1
    assert report["dirty_selected_candidates"][0]["ref"] == "FIXTURE-DIRTY-FALLBACK-SPREAD"
    assert "fallback_spread" in report["dirty_selected_candidates"][0]["execution_truth_blockers"]


def test_validator_script_writes_reports_and_returns_zero_without_fail_flag(tmp_path):
    out_json = tmp_path / "truth.json"
    out_md = tmp_path / "truth.md"

    code = main(
        [
            "--input",
            "tests/fixtures/candidates_truth_sample.json",
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
        ]
    )

    assert code == 0
    assert out_json.exists()
    assert out_md.exists()
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["summary"]["dirty_selected_or_executable"] == 1
    assert "Candidate Truth Validation Report" in out_md.read_text(encoding="utf-8")


def test_validator_script_can_fail_on_dirty_selected(tmp_path):
    code = main(
        [
            "--input",
            "tests/fixtures/candidates_truth_sample.json",
            "--out-json",
            str(tmp_path / "truth.json"),
            "--out-md",
            str(tmp_path / "truth.md"),
            "--fail-on-dirty-selected",
        ]
    )

    assert code == 1
