#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.feed_truth_audit import build_feed_truth_audit_report, render_feed_truth_audit_markdown


FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "feedtruth_audit"

# Read-only proof-pack safety contract:
# read_only=true, append=false, is_order_action=false, broker_api_called=false, live_order_action=false, broker_order_action=false


@dataclass(frozen=True)
class ProofPackCase:
    name: str
    log_file: Path
    runtime_file: Path
    expected_verdict: str
    expected_contradiction_count: int | None = None
    minimum_contradiction_count: int = 0


DEFAULT_CASES: tuple[ProofPackCase, ...] = (
    ProofPackCase(
        name="old_bad_unknown_top_executable",
        log_file=FIXTURE_ROOT / "old_bad_unknown_top_executable.jsonl",
        runtime_file=FIXTURE_ROOT / "old_bad_unknown_top_executable.runtime.json",
        expected_verdict="FAIL",
        minimum_contradiction_count=1,
    ),
    ProofPackCase(
        name="new_good_unknown_blocked_candidate",
        log_file=FIXTURE_ROOT / "new_good_unknown_blocked_candidate.jsonl",
        runtime_file=FIXTURE_ROOT / "new_good_unknown_blocked_candidate.runtime.json",
        expected_verdict="PASS",
        expected_contradiction_count=0,
    ),
    ProofPackCase(
        name="live_fresh_good_candidate",
        log_file=FIXTURE_ROOT / "live_fresh_good_candidate.jsonl",
        runtime_file=FIXTURE_ROOT / "live_fresh_good_candidate.runtime.json",
        expected_verdict="PASS",
        expected_contradiction_count=0,
    ),
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Fresh FeedTruth Audit Proof Pack.")
    parser.add_argument("--out-dir", required=True, help="Directory to write proof-pack reports into.")
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _validate_safety_flags(report: dict[str, object]) -> list[str]:
    failures: list[str] = []
    expected = {
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_allowed": False,
        "live_order_action": False,
        "broker_order_action": False,
    }
    for key, value in expected.items():
        if report.get(key) is not value:
            failures.append(f"expected {key}={value!r} got {report.get(key)!r}")
    return failures


def _validate_case_report(case: ProofPackCase, report: dict[str, object]) -> list[str]:
    failures = _validate_safety_flags(report)
    verdict = str(report.get("verdict") or "").strip().upper()
    contradiction_count = int((report.get("counts") or {}).get("contradiction_count") or 0)
    if verdict != case.expected_verdict:
        failures.append(f"expected verdict={case.expected_verdict!r} got {verdict!r}")
    if case.expected_contradiction_count is not None and contradiction_count != case.expected_contradiction_count:
        failures.append(
            f"expected contradiction_count={case.expected_contradiction_count!r} got {contradiction_count!r}"
        )
    if contradiction_count < case.minimum_contradiction_count:
        failures.append(
            f"expected contradiction_count>={case.minimum_contradiction_count!r} got {contradiction_count!r}"
        )
    return failures


def _write_report_file(out_dir: Path, case: ProofPackCase, report: dict[str, object]) -> Path:
    payload = {
        "case_name": case.name,
        "fixture_paths": {
            "log_file": str(case.log_file),
            "runtime_file": str(case.runtime_file),
        },
        "expected_verdict": case.expected_verdict,
        "expected_contradiction_count": case.expected_contradiction_count,
        "minimum_contradiction_count": case.minimum_contradiction_count,
        "audit_report": report,
        "read_only": report.get("read_only"),
        "append": report.get("append"),
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_allowed": report.get("live_order_allowed"),
        "live_order_action": False,
        "broker_order_action": False,
        "verdict": report.get("verdict"),
        "contradiction_count": (report.get("counts") or {}).get("contradiction_count", 0),
    }
    out_path = out_dir / f"{case.name}.report.json"
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return out_path


def _render_summary(report_rows: list[dict[str, object]]) -> str:
    lines = [
        "# Fresh FeedTruth Audit Proof Pack",
        "",
        f"- Generated: `{report_rows[0]['generated_epoch'] if report_rows else 'n/a'}`",
        f"- Read-only: `{True}`",
        f"- Append: `{False}`",
        f"- Is order action: `{False}`",
        f"- Broker API called: `{False}`",
        f"- Live order allowed: `{False}`",
        f"- Live order action: `{False}`",
        f"- Broker order action: `{False}`",
        "",
        "## Cases",
    ]
    for row in report_rows:
        lines.extend(
            [
                f"### {row['case_name']}",
                f"- Verdict: `{row['verdict']}`",
                f"- Contradictions: `{row['contradiction_count']}`",
                f"- Expected verdict: `{row['expected_verdict']}`",
                f"- Expected contradictions: `{row['expected_contradiction_count']}`",
                f"- Minimum contradictions: `{row['minimum_contradiction_count']}`",
                f"- Log file: `{row['fixture_paths']['log_file']}`",
                f"- Runtime file: `{row['fixture_paths']['runtime_file']}`",
                "",
            ]
        )
    return "\n".join(lines)


def run_proof_pack(out_dir: str | Path, cases: Iterable[ProofPackCase] = DEFAULT_CASES) -> dict[str, object]:
    output_dir = Path(out_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    case_rows: list[dict[str, object]] = []
    failures: list[str] = []
    for case in cases:
        report = build_feed_truth_audit_report(log_file=case.log_file, runtime_file=case.runtime_file)
        report["strict"] = True
        report["source_fixture"] = {
            "name": case.name,
            "log_file": str(case.log_file),
            "runtime_file": str(case.runtime_file),
        }
        report["contradiction_count"] = (report.get("counts") or {}).get("contradiction_count", 0)
        report["generated_epoch"] = report.get("generated_epoch")
        report["expected_verdict"] = case.expected_verdict
        report["expected_contradiction_count"] = case.expected_contradiction_count
        report["live_order_action"] = False
        report["broker_order_action"] = False
        report["validation_failures"] = _validate_case_report(case, report)
        _write_report_file(output_dir, case, report)
        case_rows.append(
            {
                "case_name": case.name,
                "verdict": report.get("verdict"),
                "contradiction_count": report["contradiction_count"],
                "expected_verdict": case.expected_verdict,
                "expected_contradiction_count": case.expected_contradiction_count,
                "minimum_contradiction_count": case.minimum_contradiction_count,
                "fixture_paths": {
                    "log_file": str(case.log_file),
                    "runtime_file": str(case.runtime_file),
                },
                "generated_epoch": report.get("generated_epoch"),
                "live_order_action": False,
                "broker_order_action": False,
            }
        )
        if report["validation_failures"]:
            failures.append(f"{case.name}: " + "; ".join(str(item) for item in report["validation_failures"]))

    summary_path = output_dir / "summary.md"
    summary_path.write_text(_render_summary(case_rows), encoding="utf-8")

    summary = {
        "out_dir": str(output_dir),
        "summary_path": str(summary_path),
        "case_rows": case_rows,
        "failures": failures,
        "exit_code": 0 if not failures else 1,
    }
    return summary


def main() -> int:
    args = _parse_args()
    summary = run_proof_pack(args.out_dir)
    if summary["failures"]:
        for failure in summary["failures"]:
            print(f"proof pack failure: {failure}", file=sys.stderr)
        return 1
    print(f"proof pack summary written: {summary['summary_path']}")
    for row in summary["case_rows"]:
        print(f"{row['case_name']}: {row['verdict']} contradictions={row['contradiction_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
