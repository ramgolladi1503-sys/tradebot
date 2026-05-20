from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tools.repo_forensics.agent_evidence import render_agent_gate_evidence, render_pr_body_agent_summary
from tools.repo_forensics.unified_runner import EXIT_POLICY_REPORT_ONLY, ForensicsCheckToggles, ForensicsRunResult, run_forensics


DEFAULT_BASELINE_REPORT = "docs/repo_forensics/reports/baseline_latest.md"
DEFAULT_BASELINE_AGENT_EVIDENCE = "docs/agent_reviews/GSD_FOR_12_TRADEBOT_BASELINE_AGENT_GATE.md"
DEFAULT_PR_SUMMARY = "docs/repo_forensics/reports/baseline_pr_summary.md"


@dataclass(frozen=True)
class BaselineAuditResult:
    run_result: ForensicsRunResult
    report_path: Path
    agent_evidence_path: Path
    pr_summary_path: Path


def generate_baseline_audit(
    repo_root: str | Path,
    config_path: str | Path = ".gsd-forensics.yaml",
    *,
    report_path: str | Path = DEFAULT_BASELINE_REPORT,
    agent_evidence_path: str | Path = DEFAULT_BASELINE_AGENT_EVIDENCE,
    pr_summary_path: str | Path = DEFAULT_PR_SUMMARY,
    toggles: ForensicsCheckToggles | None = None,
) -> BaselineAuditResult:
    """Generate the first TradeBot repo-forensics baseline evidence files.

    The baseline command intentionally uses report-only exit behavior. A baseline
    should record current findings, not hide them by failing before reports are
    written. The generated evidence still carries FAIL/UNKNOWN/PASS verdicts.
    """

    root = Path(repo_root).resolve()
    report_file = _resolve(root, report_path)
    evidence_file = _resolve(root, agent_evidence_path)
    summary_file = _resolve(root, pr_summary_path)

    run_result = run_forensics(
        root,
        config_path,
        report_file,
        toggles=toggles or ForensicsCheckToggles(),
        exit_policy=EXIT_POLICY_REPORT_ONLY,
    )

    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text(render_agent_gate_evidence(run_result), encoding="utf-8")
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(render_pr_body_agent_summary(run_result) + "\n", encoding="utf-8")

    return BaselineAuditResult(
        run_result=run_result,
        report_path=report_file,
        agent_evidence_path=evidence_file,
        pr_summary_path=summary_file,
    )


def _resolve(repo_root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return repo_root / candidate
