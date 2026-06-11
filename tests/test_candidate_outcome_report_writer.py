from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.candidate_outcome_report_writer import (
    build_candidate_outcome_report,
    report_to_payload,
    write_candidate_outcome_json_report,
    write_candidate_outcome_markdown_report,
    write_candidate_outcome_reports,
)
from core.candidate_outcome_truth import (
    AMBIGUOUS_SAME_BAR,
    NO_OBSERVATIONS,
    NOT_EXECUTABLE,
    STOP_HIT,
    TARGET_HIT,
    TIMEOUT,
)


FIXTURE_DIR = Path("tests/fixtures/candidate_outcomes")


def test_build_report_from_committed_fixtures() -> None:
    report = build_candidate_outcome_report(FIXTURE_DIR)

    assert report.fixture_count == 7
    assert report.status_counts[TARGET_HIT] == 1
    assert report.status_counts[STOP_HIT] == 1
    assert report.status_counts[TIMEOUT] == 2
    assert report.status_counts[NOT_EXECUTABLE] == 1
    assert report.status_counts[NO_OBSERVATIONS] == 1
    assert report.status_counts[AMBIGUOUS_SAME_BAR] == 1
    assert report.safety["read_only"] is True
    assert report.safety["append"] is False
    assert report.safety["is_order_action"] is False
    assert report.safety["broker_api_called"] is False
    assert report.safety["live_order_allowed"] is False
    assert report.safety["proves_trading_edge"] is False


def test_report_results_are_deterministic() -> None:
    report_one = build_candidate_outcome_report(FIXTURE_DIR)
    report_two = build_candidate_outcome_report(FIXTURE_DIR)

    assert report_to_payload(report_one) == report_to_payload(report_two)


def test_report_rows_match_expected_status() -> None:
    report = build_candidate_outcome_report(FIXTURE_DIR)
    assert all(row["expected_matches_actual"] is True for row in report.results)


def test_report_contains_post_timeout_guard_fixture() -> None:
    report = build_candidate_outcome_report(FIXTURE_DIR)
    row = next(row for row in report.results if row["fixture_id"] == "post_timeout_target_ignored")

    assert row["outcome_status"] == TIMEOUT
    assert row["expected_matches_actual"] is True


def test_write_json_report(tmp_path: Path) -> None:
    report = build_candidate_outcome_report(FIXTURE_DIR)
    output_path = write_candidate_outcome_json_report(report, tmp_path / "candidate_outcome_report.json")

    payload = json.loads(output_path.read_text())
    assert payload["schema_version"] == 1
    assert payload["fixture_count"] == 7
    assert payload["safety"]["read_only"] is True
    assert payload["safety"]["append"] is False
    assert payload["results"]


def test_write_markdown_report(tmp_path: Path) -> None:
    report = build_candidate_outcome_report(FIXTURE_DIR)
    output_path = write_candidate_outcome_markdown_report(report, tmp_path / "candidate_outcome_report.md")

    markdown = output_path.read_text()
    assert "Candidate Outcome Report" in markdown
    assert "This report does not prove trading edge." in markdown
    assert "Status Counts" in markdown
    assert "| fixture_id | outcome_status | expected_outcome_status | expected_matches_actual | gross_r | cost_adjusted_r |" in markdown


def test_write_candidate_outcome_reports_writes_both_files(tmp_path: Path) -> None:
    json_path, markdown_path = write_candidate_outcome_reports(FIXTURE_DIR, tmp_path)

    assert json_path.exists()
    assert markdown_path.exists()
    assert json_path.name == "candidate_outcome_report.json"
    assert markdown_path.name == "candidate_outcome_report.md"


def test_missing_fixture_dir_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="fixture directory does not exist"):
        build_candidate_outcome_report(tmp_path / "missing")


def test_report_writer_preserves_non_action_flags_for_every_result() -> None:
    report = build_candidate_outcome_report(FIXTURE_DIR)

    for row in report.results:
        assert row["read_only"] is True
        assert row["append"] is False
        assert row["is_order_action"] is False
        assert row["broker_api_called"] is False
        assert row["live_order_allowed"] is False
        assert row["live_order_action"] is False
        assert row["broker_order_action"] is False


def test_cli_writes_reports_offline(tmp_path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/write_candidate_outcome_report.py",
            "--fixture-dir",
            str(FIXTURE_DIR),
            "--output-dir",
            str(tmp_path),
        ],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent)},
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "candidate_outcome_report.json").exists()
    assert (tmp_path / "candidate_outcome_report.md").exists()
    assert str(tmp_path / "candidate_outcome_report.json") in proc.stdout
    assert str(tmp_path / "candidate_outcome_report.md") in proc.stdout
