from __future__ import annotations

import argparse
import json

from .agents import DeterministicCritic, validate_advisory_review
from .engine import AgenticQAAuditor, write_report
from .evaluation import evaluate_agent_guardrails


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit a frozen TradeBot evidence bundle against 70 Agentic QA controls.")
    parser.add_argument("bundle", help="Path to a frozen evidence bundle")
    parser.add_argument("--output", default="agentic_qa_audit_report.json")
    parser.add_argument("--evaluation-output", default="agentic_qa_agent_evaluation.json")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = AgenticQAAuditor().audit_bundle(args.bundle)
    critic = DeterministicCritic()
    review = critic.review(report.to_dict())
    outcome = validate_advisory_review(report, review)
    evaluation = evaluate_agent_guardrails(report, review)
    report_payload = report.to_dict()
    report_payload["agent_review_validation"] = {
        "accepted": outcome.accepted,
        "reason_code": outcome.reason_code,
        "review": outcome.review,
    }
    output_path = write_report(report, args.output)
    output_path.with_suffix(".advisory.json").write_text(
        json.dumps(report_payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    with open(args.evaluation_output, "w", encoding="utf-8") as handle:
        json.dump(evaluation, handle, indent=2, sort_keys=True)
    print(json.dumps({"verdict": report.verdict.value, "score": report.deterministic_score, "report": str(output_path)}))
    return 0 if report.verdict.value in {"CONTROL_PLANE_CERTIFIED", "CONDITIONALLY_CERTIFIED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
