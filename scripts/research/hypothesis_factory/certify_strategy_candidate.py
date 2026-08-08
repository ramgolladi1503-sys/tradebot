#!/usr/bin/env python3
"""Certify or block a strategy candidate from evidence files.

The certifier never grants live-trading or broker authority. It can only produce
research-stage verdicts from explicit screen, filter, and robustness evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import strategy_certification_artifacts as sca  # noqa: E402


ALLOWED_VERDICTS = {
    "REJECTED",
    "PROMISING_NOT_CERTIFIED",
    "ROBUSTNESS_REQUIRED",
    "VALIDATED_RESEARCH",
    "ADAPTER_READY",
}
FORBIDDEN_VERDICTS = {"PRODUCTION_READY", "LIVE_TRADING_READY", "BROKER_READY"}


def find_candidate(report: dict[str, Any], candidate_id: str, candidate_shape_key: str) -> dict[str, Any] | None:
    for candidate in report.get("candidates", []):
        if candidate_id and candidate.get("hypothesis_id") == candidate_id:
            return candidate
        if candidate_shape_key and candidate.get("candidate_shape_key") == candidate_shape_key:
            return candidate
    return None


def decide_verdict(candidate: dict[str, Any] | None, robustness: dict[str, Any] | None) -> tuple[str, list[str]]:
    if candidate is None:
        return "REJECTED", ["candidate_not_found"]

    rejection_reasons = list(candidate.get("rejection_reasons", []))
    if rejection_reasons:
        return "REJECTED", rejection_reasons

    if robustness is None:
        return "ROBUSTNESS_REQUIRED", ["missing_robustness_evidence"]

    status = robustness.get("status")
    if status == "ROBUSTNESS_BLOCKED":
        return "ROBUSTNESS_REQUIRED", list(robustness.get("blocking_reasons", ["robustness_blocked"]))
    if not robustness.get("robustness_passed"):
        return "REJECTED", list(robustness.get("failed_gates", ["robustness_failed"]))

    return "VALIDATED_RESEARCH", []


def build_passport(
    args: argparse.Namespace,
    candidate: dict[str, Any] | None,
    verdict: str,
    reasons: list[str],
    evidence_paths: list[Path],
    robustness: dict[str, Any] | None,
) -> dict[str, Any]:
    candidate = candidate or {}
    mode = "VALIDATED_RESEARCH" if verdict == "VALIDATED_RESEARCH" else "RESEARCH_ONLY"
    return {
        "schema_version": "tradebot-strategy-passport-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_hypothesis_id": candidate.get("hypothesis_id", args.candidate_hypothesis_id),
        "candidate_shape_key": candidate.get("candidate_shape_key", args.candidate_shape_key),
        "instrument": candidate.get("instrument"),
        "family": candidate.get("family"),
        "direction": candidate.get("direction"),
        "window_minutes": candidate.get("window_minutes"),
        "filters": candidate.get("filters"),
        "verdict": verdict,
        "certification": verdict,
        "blocking_reasons": reasons,
        "runtime_authority": sca.SAFE_RUNTIME_AUTHORITY,
        "broker_actions_allowed": sca.SAFE_BROKER_ACTIONS_ALLOWED,
        "forbidden_verdicts": sorted(FORBIDDEN_VERDICTS),
        "integration": {
            "allowed_tradebot_mode": mode,
            "adapter_required": verdict == "VALIDATED_RESEARCH",
            "shadow_first_required": True,
            "broker_actions_allowed": sca.SAFE_BROKER_ACTIONS_ALLOWED,
            "runtime_authority": sca.SAFE_RUNTIME_AUTHORITY,
        },
        "screen_metrics": {
            "trades": candidate.get("trades"),
            "win_rate": candidate.get("win_rate"),
            "net_expectancy_bps": candidate.get("net_expectancy_bps"),
            "profit_factor": candidate.get("profit_factor"),
            "max_drawdown_bps": candidate.get("max_drawdown_bps"),
        },
        "robustness": robustness or {},
        "evidence_hashes": sca.evidence_hashes(evidence_paths),
    }


def certify(args: argparse.Namespace) -> dict[str, Any]:
    screen_run_dir = Path(args.screen_run_dir)
    filter_path = Path(args.candidate_filter_report) if args.candidate_filter_report else screen_run_dir / "candidate_filter_report.json"
    robustness_dir = Path(args.robustness_run_dir) if args.robustness_run_dir else None
    robustness_result_path = robustness_dir / "robustness_results.json" if robustness_dir else None
    robustness_manifest_path = robustness_dir / "robustness_manifest.json" if robustness_dir else None

    evidence_paths = [
        screen_run_dir / "run_manifest.json",
        screen_run_dir / "leaderboard.csv",
        filter_path,
    ]

    filter_report = sca.read_json(filter_path) if filter_path.exists() else {"candidates": []}
    candidate = find_candidate(filter_report, args.candidate_hypothesis_id, args.candidate_shape_key)

    robustness = None
    if robustness_result_path and robustness_result_path.exists():
        robustness = sca.read_json(robustness_result_path)
        evidence_paths.append(robustness_result_path)
    if robustness_manifest_path and robustness_manifest_path.exists():
        evidence_paths.append(robustness_manifest_path)

    verdict, reasons = decide_verdict(candidate, robustness)
    if verdict not in ALLOWED_VERDICTS or verdict in FORBIDDEN_VERDICTS:
        verdict = "REJECTED"
        reasons.append("invalid_or_forbidden_verdict")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    passport = build_passport(args, candidate, verdict, reasons, evidence_paths, robustness)
    decision = {
        "schema_version": "tradebot-certification-decision-v1",
        "created_at_utc": passport["created_at_utc"],
        "candidate_hypothesis_id": passport["candidate_hypothesis_id"],
        "candidate_shape_key": passport["candidate_shape_key"],
        "verdict": verdict,
        "blocking_reasons": reasons,
        "runtime_authority": sca.SAFE_RUNTIME_AUTHORITY,
        "broker_actions_allowed": sca.SAFE_BROKER_ACTIONS_ALLOWED,
        "passport_path": str(out_dir / "strategy_passport.json"),
        "allowed_verdicts": sorted(ALLOWED_VERDICTS),
        "forbidden_verdicts": sorted(FORBIDDEN_VERDICTS),
    }
    integration = passport["integration"]

    sca.write_json(out_dir / "strategy_passport.json", passport)
    sca.write_json(out_dir / "certification_decision.json", decision)
    sca.write_json(out_dir / "integration_decision.json", integration)
    sca.write_markdown_report(out_dir / "certification_report.md", "Strategy Certification Report", [
        f"- Verdict: `{verdict}`",
        f"- Blocking reasons: `{', '.join(reasons) if reasons else 'NONE'}`",
        f"- Runtime authority: `{sca.SAFE_RUNTIME_AUTHORITY}`",
        f"- Broker actions allowed: `{sca.SAFE_BROKER_ACTIONS_ALLOWED}`",
        f"- Allowed TradeBot mode: `{integration['allowed_tradebot_mode']}`",
        "",
        "This report does not authorize production, live trading, broker operations, or runtime authority.",
    ])

    return {
        "passport": passport,
        "decision": decision,
        "integration": integration,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen-run-dir", required=True)
    parser.add_argument("--candidate-filter-report", default="")
    parser.add_argument("--robustness-run-dir", default="")
    parser.add_argument("--candidate-hypothesis-id", default="")
    parser.add_argument("--candidate-shape-key", default="")
    parser.add_argument("--output-dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = certify(args)
    decision = result["decision"]
    print(json.dumps({
        "verdict": decision["verdict"],
        "blocking_reasons": decision["blocking_reasons"],
        "runtime_authority": decision["runtime_authority"],
        "broker_actions_allowed": decision["broker_actions_allowed"],
        "passport_path": decision["passport_path"],
    }, indent=2, sort_keys=True))
    return 0 if decision["verdict"] == "VALIDATED_RESEARCH" else 2


if __name__ == "__main__":
    raise SystemExit(main())
