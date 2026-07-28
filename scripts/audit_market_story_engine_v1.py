#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def audit(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text())
    stored_semantic = payload.pop("semantic_sha256", None)
    baseline = payload.get("baseline", {})
    checks = {
        "semantic_hash_matches": stored_semantic == canonical_hash(payload),
        "verdict_pass": (
            payload.get("verdict") == "PASS_IMPLEMENTATION_ROBUSTNESS_GATE"
        ),
        "all_scenarios_pass": all(
            payload.get("scenario_checks", {}).values()
        ),
        "noise_stability": all(
            result.get("stability", 0) >= 0.90
            for result in payload.get("noise_results", {}).values()
        ),
        "prefix_invariance": payload.get("prefix_invariance") is True,
        "time_shift_control": payload.get("time_shift_control_pass") is True,
        "determinism": payload.get("determinism_pass") is True,
        "mirror_symmetry": payload.get("mirrored_symmetry") is True,
        "safety_flags": (
            payload.get("research_only") is True
            and payload.get("allowed_for_live_execution") is False
            and payload.get("broker_api_called") is False
            and payload.get("is_order_action") is False
        ),
        "claim_boundary_present": (
            "no profitable edge" in str(payload.get("claim_boundary", ""))
        ),
        "bullish_terminal": (
            baseline.get("bull", {}).get("decision") == "BUY_CE"
        ),
        "bearish_terminal": (
            baseline.get("bear", {}).get("decision") == "BUY_PE"
        ),
        "crossed_market_rejected": (
            baseline.get("crossed_option", {}).get("decision") == "REJECT"
        ),
    }
    verdict = (
        "PASS_INDEPENDENT_AUDIT"
        if all(checks.values())
        else "FAIL_INDEPENDENT_AUDIT"
    )
    return {
        "verdict": verdict,
        "checks": checks,
        "failed_checks": [
            name for name, passed in checks.items() if not passed
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("certification")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = audit(Path(args.certification))
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(text)
    print(text, end="")
    return 0 if report["verdict"] == "PASS_INDEPENDENT_AUDIT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
