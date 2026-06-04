from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.feed_truth_audit import build_feed_truth_audit_report


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "feedtruth_audit"


def _fixture(name: str) -> tuple[Path, Path]:
    return (
        FIXTURE_ROOT / f"{name}.jsonl",
        FIXTURE_ROOT / f"{name}.runtime.json",
    )


def _load_report(log_name: str) -> dict[str, object]:
    log_file, runtime_file = _fixture(log_name)
    return build_feed_truth_audit_report(log_file=log_file, runtime_file=runtime_file)


def test_old_bad_unknown_top_executable_fails_audit() -> None:
    report = _load_report("old_bad_unknown_top_executable")

    assert report["verdict"] == "FAIL"
    assert report["read_only"] is True
    assert report["append"] is False
    assert report["is_order_action"] is False
    assert report["broker_api_called"] is False
    assert report["live_order_allowed"] is False
    assert report["counts"]["contradiction_count"] > 0
    codes = {item["code"] for item in report["contradictions"]}
    assert "unsafe_reportable_executable_under_blocked_feedtruth" in codes
    assert "top_executable_emitted_under_blocked_truth" in codes


def test_new_good_unknown_blocked_candidate_passes_audit() -> None:
    report = _load_report("new_good_unknown_blocked_candidate")

    assert report["verdict"] == "PASS"
    assert report["read_only"] is True
    assert report["append"] is False
    assert report["is_order_action"] is False
    assert report["broker_api_called"] is False
    assert report["live_order_allowed"] is False
    assert report["counts"]["contradiction_count"] == 0
    assert report["counts"]["reportable_executable_count"] == 0
    assert report["counts"]["blocked_candidate_count"] == 1


def test_live_fresh_good_candidate_passes_audit() -> None:
    report = _load_report("live_fresh_good_candidate")

    assert report["verdict"] == "PASS"
    assert report["read_only"] is True
    assert report["append"] is False
    assert report["is_order_action"] is False
    assert report["broker_api_called"] is False
    assert report["live_order_allowed"] is False
    assert report["counts"]["contradiction_count"] == 0
    assert report["counts"]["reportable_executable_count"] == 1
    assert report["feed_truth_state_counts"]["LIVE"] >= 1


def test_proof_pack_cli_writes_reports_and_summary(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_feedtruth_audit_proof_pack.py",
            "--out-dir",
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout

    expected_files = [
        tmp_path / "old_bad_unknown_top_executable.report.json",
        tmp_path / "new_good_unknown_blocked_candidate.report.json",
        tmp_path / "live_fresh_good_candidate.report.json",
        tmp_path / "summary.md",
    ]
    for path in expected_files:
        assert path.exists(), path

    old_bad = json.loads((tmp_path / "old_bad_unknown_top_executable.report.json").read_text(encoding="utf-8"))
    new_good = json.loads((tmp_path / "new_good_unknown_blocked_candidate.report.json").read_text(encoding="utf-8"))
    live_good = json.loads((tmp_path / "live_fresh_good_candidate.report.json").read_text(encoding="utf-8"))

    assert old_bad["audit_report"]["verdict"] == "FAIL"
    assert old_bad["audit_report"]["counts"]["contradiction_count"] > 0
    assert new_good["audit_report"]["verdict"] == "PASS"
    assert new_good["audit_report"]["counts"]["contradiction_count"] == 0
    assert live_good["audit_report"]["verdict"] == "PASS"
    assert live_good["audit_report"]["counts"]["contradiction_count"] == 0
    assert old_bad["audit_report"]["read_only"] is True
    assert new_good["audit_report"]["read_only"] is True
    assert live_good["audit_report"]["read_only"] is True
    assert old_bad["live_order_action"] is False
    assert old_bad["broker_order_action"] is False
    assert new_good["live_order_action"] is False
    assert new_good["broker_order_action"] is False
    assert live_good["live_order_action"] is False
    assert live_good["broker_order_action"] is False


def test_proof_pack_helper_fails_closed_on_mismatch(tmp_path: Path) -> None:
    import scripts.run_feedtruth_audit_proof_pack as proof_pack

    bad_case = proof_pack.ProofPackCase(
        name="mismatch_case",
        log_file=FIXTURE_ROOT / "live_fresh_good_candidate.jsonl",
        runtime_file=FIXTURE_ROOT / "live_fresh_good_candidate.runtime.json",
        expected_verdict="FAIL",
        expected_contradiction_count=1,
    )

    outcome = proof_pack.run_proof_pack(tmp_path, cases=[bad_case])

    assert outcome["exit_code"] != 0
    assert (tmp_path / "mismatch_case.report.json").exists()
