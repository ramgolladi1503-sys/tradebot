from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from tools.qa_certification.whole_tradebot_manifest import WHOLE_TRADEBOT_AREAS


def _pct(covered: int, total: int) -> float:
    if total <= 0:
        return 100.0
    return (float(covered) / float(total)) * 100.0


def _normalize(path: str) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def evaluate_coverage(
    coverage_payload: dict[str, Any],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    files = {
        _normalize(path): payload
        for path, payload in dict(coverage_payload.get("files") or {}).items()
    }
    area_reports: list[dict[str, Any]] = []
    hard_failures: list[dict[str, Any]] = []

    for area in WHOLE_TRADEBOT_AREAS:
        module_reports: list[dict[str, Any]] = []
        for module in area.modules:
            normalized = _normalize(module)
            exists = (repo_root / normalized).exists()
            file_payload = files.get(normalized)
            summary = dict((file_payload or {}).get("summary") or {})
            covered_lines = int(summary.get("covered_lines") or 0)
            num_statements = int(summary.get("num_statements") or 0)
            covered_branches = int(summary.get("covered_branches") or 0)
            num_branches = int(summary.get("num_branches") or 0)
            line_pct = _pct(covered_lines, num_statements) if file_payload is not None else 0.0
            branch_pct = _pct(covered_branches, num_branches) if file_payload is not None else 0.0
            reasons: list[str] = []
            if not exists:
                reasons.append("configured_module_missing")
            if file_payload is None:
                reasons.append("module_unmeasured")
            if file_payload is not None and line_pct + 1e-9 < area.line_min:
                reasons.append("line_coverage_below_threshold")
            if file_payload is not None and branch_pct + 1e-9 < area.branch_min:
                reasons.append("branch_coverage_below_threshold")
            passed = not reasons
            module_report = {
                "path": normalized,
                "exists": exists,
                "measured": file_payload is not None,
                "line_pct": round(line_pct, 4),
                "branch_pct": round(branch_pct, 4),
                "line_min": area.line_min,
                "branch_min": area.branch_min,
                "passed": passed,
                "reasons": reasons,
            }
            module_reports.append(module_report)
            if not passed:
                hard_failures.append(
                    {
                        "area": area.name,
                        "tier": area.tier,
                        **module_report,
                    }
                )

        area_reports.append(
            {
                "name": area.name,
                "tier": area.tier,
                "line_min": area.line_min,
                "branch_min": area.branch_min,
                "required_test_families": list(area.required_test_families),
                "passed": all(item["passed"] for item in module_reports),
                "modules": module_reports,
            }
        )

    return {
        "schema_version": 1,
        "verdict": "PASS" if not hard_failures else "FAIL",
        "area_count": len(area_reports),
        "module_count": sum(len(area["modules"]) for area in area_reports),
        "hard_failure_count": len(hard_failures),
        "areas": area_reports,
        "hard_failures": hard_failures,
        "manifest": [asdict(area) for area in WHOLE_TRADEBOT_AREAS],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Whole-TradeBot Coverage Certification",
        "",
        f"Verdict: **{report['verdict']}**",
        f"Critical areas: {report['area_count']}",
        f"Critical modules: {report['module_count']}",
        f"Hard failures: {report['hard_failure_count']}",
        "",
        "| Area | Tier | Status | Failed modules |",
        "|---|---:|---|---:|",
    ]
    for area in report["areas"]:
        failed = sum(1 for module in area["modules"] if not module["passed"])
        lines.append(
            f"| {area['name']} | {area['tier']} | {'PASS' if area['passed'] else 'FAIL'} | {failed} |"
        )
    lines.extend(["", "## Module evidence", ""])
    for area in report["areas"]:
        lines.append(f"### {area['name']} — Tier {area['tier']}")
        lines.append("")
        lines.append("| Module | Line | Branch | Required | Status | Reasons |")
        lines.append("|---|---:|---:|---:|---|---|")
        for module in area["modules"]:
            required = f"{module['line_min']:.0f}/{module['branch_min']:.0f}"
            reasons = ", ".join(module["reasons"]) or "—"
            lines.append(
                f"| `{module['path']}` | {module['line_pct']:.2f}% | "
                f"{module['branch_pct']:.2f}% | {required} | "
                f"{'PASS' if module['passed'] else 'FAIL'} | {reasons} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate whole-TradeBot coverage evidence.")
    parser.add_argument("--coverage-json", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args()

    coverage_path = Path(args.coverage_json)
    payload = json.loads(coverage_path.read_text(encoding="utf-8"))
    report = evaluate_coverage(payload, repo_root=Path(args.repo_root).resolve())

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")

    print(
        "whole_tradebot_coverage "
        f"verdict={report['verdict']} "
        f"areas={report['area_count']} "
        f"modules={report['module_count']} "
        f"hard_failures={report['hard_failure_count']}"
    )
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
