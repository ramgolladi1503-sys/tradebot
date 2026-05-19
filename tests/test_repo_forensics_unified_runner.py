from __future__ import annotations

from pathlib import Path

from tools.repo_forensics.unified_runner import (
    EXIT_POLICY_REPORT_ONLY,
    EXIT_POLICY_STRICT,
    ForensicsCheckToggles,
    ForensicsCounts,
    render_pr_summary,
    run_forensics,
)


def _write_profile(repo_root):
    cfg = repo_root / "forensics.yaml"
    cfg.write_text(
        """
project:
  name: tradebot
baseline_rules:
  unknown_is_not_pass: true
entrypoints:
  required:
    - app.py
critical_modules:
  runtime:
    - app.py
exclude:
  directories:
    - cache_dir
""",
        encoding="utf-8",
    )
    return cfg


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_unified_runner_generates_report_and_summary(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    cfg = _write_profile(tmp_path)
    out = tmp_path / "reports" / "latest.md"

    result = run_forensics(
        tmp_path,
        cfg,
        out,
        toggles=ForensicsCheckToggles(
            runtime_wiring=False,
            critical_callers=False,
            test_reality=False,
            safety_boundary=False,
            evidence_audit=False,
            architecture_drift=False,
        ),
    )

    assert result.report_path == out
    assert result.report_path.exists()
    assert result.exit_code == 0
    summary = render_pr_summary(result)
    assert "[repo-forensics] verdict=PASS" in summary
    assert "[repo-forensics] skipped_checks=runtime_wiring,critical_callers,test_reality,safety_boundary,evidence_audit,architecture_drift" in summary


def test_unified_runner_report_only_policy_keeps_exit_zero_on_hard_failure(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    cfg = tmp_path / "forensics.yaml"
    cfg.write_text(
        """
project:
  name: tradebot
baseline_rules:
  unknown_is_not_pass: true
entrypoints:
  required:
    - missing.py
critical_modules:
  runtime:
    - app.py
""",
        encoding="utf-8",
    )

    strict_result = run_forensics(
        tmp_path,
        cfg,
        tmp_path / "strict.md",
        toggles=ForensicsCheckToggles(
            runtime_wiring=False,
            critical_callers=False,
            test_reality=False,
            safety_boundary=False,
            evidence_audit=False,
            architecture_drift=False,
        ),
        exit_policy=EXIT_POLICY_STRICT,
    )
    report_only_result = run_forensics(
        tmp_path,
        cfg,
        tmp_path / "report_only.md",
        toggles=ForensicsCheckToggles(
            runtime_wiring=False,
            critical_callers=False,
            test_reality=False,
            safety_boundary=False,
            evidence_audit=False,
            architecture_drift=False,
        ),
        exit_policy=EXIT_POLICY_REPORT_ONLY,
    )

    assert strict_result.verdict == "FAIL"
    assert strict_result.exit_code == 1
    assert report_only_result.verdict == "FAIL"
    assert report_only_result.exit_code == 0


def test_forensics_counts_group_hard_failures_unknowns_and_warnings():
    counts = ForensicsCounts(
        missing_required_entrypoints=1,
        runtime_flow_unknowns=2,
        fake_confidence_tests=3,
    )

    assert counts.hard_failures == 1
    assert counts.unknowns == 2
    assert counts.warnings == 3
