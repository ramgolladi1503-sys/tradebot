from __future__ import annotations

from tools.repo_forensics.baseline import generate_baseline_audit
from tools.repo_forensics.unified_runner import ForensicsCheckToggles


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


def test_generate_baseline_audit_writes_report_agent_evidence_and_summary(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    cfg = _write_profile(tmp_path)

    result = generate_baseline_audit(
        tmp_path,
        cfg,
        report_path="reports/baseline.md",
        agent_evidence_path="agent/baseline_gate.md",
        pr_summary_path="reports/pr_summary.md",
        toggles=ForensicsCheckToggles(
            runtime_wiring=False,
            critical_callers=False,
            test_reality=False,
            safety_boundary=False,
            evidence_audit=False,
            architecture_drift=False,
        ),
    )

    assert result.report_path.exists()
    assert result.agent_evidence_path.exists()
    assert result.pr_summary_path.exists()
    assert "# Repo Forensics" in result.report_path.read_text(encoding="utf-8")
    assert "## 3-Agent Evidence Gate" in result.agent_evidence_path.read_text(encoding="utf-8")
    assert "## 3-Agent Evidence Summary" in result.pr_summary_path.read_text(encoding="utf-8")
    assert result.run_result.exit_code == 0


def test_generate_baseline_audit_records_fail_verdict_but_still_exits_report_only(tmp_path):
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
    - missing.py
""",
        encoding="utf-8",
    )

    result = generate_baseline_audit(
        tmp_path,
        cfg,
        report_path="reports/baseline.md",
        agent_evidence_path="agent/baseline_gate.md",
        pr_summary_path="reports/pr_summary.md",
        toggles=ForensicsCheckToggles(
            runtime_wiring=False,
            critical_callers=False,
            test_reality=False,
            safety_boundary=False,
            evidence_audit=False,
            architecture_drift=False,
        ),
    )

    assert result.run_result.verdict == "FAIL"
    assert result.run_result.exit_code == 0
    assert result.run_result.counts.hard_failures == 2
    assert "Verdict: `FAIL`" in result.agent_evidence_path.read_text(encoding="utf-8")
