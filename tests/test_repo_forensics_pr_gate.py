from __future__ import annotations

from tools.repo_forensics.pr_gate import compare_counts, gate_verdict, parse_baseline_counts, run_pr_gate
from tools.repo_forensics.unified_runner import ForensicsCheckToggles, ForensicsCounts


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


def test_parse_baseline_counts_reads_compact_summary():
    counts = parse_baseline_counts(
        """
## 3-Agent Evidence Summary

- Hard failures: `113`
- Unknowns: `59`
- Warnings: `135`
- Safety critical: `2`
- Evidence high: `3`
- Drift high: `4`
"""
    )

    assert counts.hard_failures == 113
    assert counts.unknowns == 59
    assert counts.warnings == 135
    assert counts.safety_critical == 2
    assert counts.evidence_high == 3
    assert counts.drift_high == 4


def test_gate_verdict_fails_only_on_new_hard_failures_first():
    baseline = ForensicsCounts(missing_required_entrypoints=1)
    current = ForensicsCounts(missing_required_entrypoints=2)

    deltas = compare_counts(baseline, current)

    assert gate_verdict(deltas) == "FAIL"


def test_gate_verdict_unknown_when_only_unknowns_increase():
    baseline = ForensicsCounts(runtime_flow_unknowns=1)
    current = ForensicsCounts(runtime_flow_unknowns=2)

    deltas = compare_counts(baseline, current)

    assert gate_verdict(deltas) == "UNKNOWN"


def test_run_pr_gate_writes_delta_report_without_runtime_execution(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    cfg = _write_profile(tmp_path)
    baseline = tmp_path / "baseline_pr_summary.md"
    baseline.write_text(
        """
## 3-Agent Evidence Summary

- Hard failures: `0`
- Unknowns: `0`
- Warnings: `0`
""",
        encoding="utf-8",
    )

    result = run_pr_gate(
        tmp_path,
        cfg,
        baseline_summary_path=baseline,
        current_report_path="reports/current.md",
        gate_report_path="reports/pr_gate.md",
        toggles=ForensicsCheckToggles(
            runtime_wiring=False,
            critical_callers=False,
            test_reality=False,
            safety_boundary=False,
            evidence_audit=False,
            architecture_drift=False,
        ),
    )

    assert result.verdict == "PASS"
    assert result.report_path.exists()
    report = result.report_path.read_text(encoding="utf-8")
    assert "# Repo Forensics — PR Gate" in report
    assert "Existing baseline debt is not treated as a new regression" in report
    assert "| hard_failures | 0 | 0 | 0 |" in report
