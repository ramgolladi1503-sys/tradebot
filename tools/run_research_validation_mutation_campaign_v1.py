"""Run bounded adversarial mutations against research-certification gates.

This is an offline governance campaign. It does not import execution, broker, risk,
strategy, feed, credential, or live-runtime modules.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from core.research_validation.policy import CertificationInput, certify_research


def _baseline() -> dict[str, object]:
    return {
        "hypothesis_id": "H-MUT-001",
        "registered_experiments": 20,
        "declared_experiments": 20,
        "parameter_stability_pass": True,
        "wfa_pass": True,
        "pbo": 0.10,
        "psr": 0.99,
        "dsr": 0.99,
        "actual_track_record": 500,
        "minimum_track_record": 200,
        "power": 0.90,
        "cost_robust_pass": True,
        "holdout_status": "PASS",
        "prospective_status": "PASS",
        "inference_model_valid": True,
        "search_history_complete": True,
    }


def _mutation(name: str, expected_reason: str, **changes: object) -> dict[str, object]:
    payload = _baseline()
    payload.update(changes)
    verdict = certify_research(CertificationInput(**payload), require_prospective=True)
    detected = verdict.status != "CERTIFIED_RESEARCH" and expected_reason in verdict.reasons
    return {
        "mutation": name,
        "expected_reason": expected_reason,
        "detected": detected,
        "status": verdict.status,
        "reasons": "|".join(verdict.reasons),
    }


def run_campaign() -> list[dict[str, object]]:
    rows = [
        _mutation("missing_hypothesis", "MISSING_HYPOTHESIS_ID", hypothesis_id=""),
        _mutation("hidden_experiment", "SEARCH_HISTORY_INCOMPLETE", declared_experiments=21),
        _mutation("search_history_flag_tamper", "SEARCH_HISTORY_INCOMPLETE", search_history_complete=False),
        _mutation("invalid_inference_model", "INFERENCE_MODEL_INVALID", inference_model_valid=False),
        _mutation("parameter_peak", "PARAMETER_FRAGILE", parameter_stability_pass=False),
        _mutation("wfa_failure", "WFA_FAIL", wfa_pass=False),
        _mutation("pbo_too_high", "PBO_HIGH", pbo=0.95),
        _mutation("psr_too_low", "PSR_FAIL", psr=0.10),
        _mutation("dsr_too_low", "DSR_FAIL", dsr=0.10),
        _mutation("track_record_too_short", "UNDERPOWERED", actual_track_record=20),
        _mutation("low_power", "UNDERPOWERED", power=0.10),
        _mutation("cost_failure", "COST_ROBUSTNESS_FAIL", cost_robust_pass=False),
        _mutation("holdout_failure", "HOLDOUT_NOT_PASS", holdout_status="FAIL"),
        _mutation("prospective_failure", "PROSPECTIVE_NOT_CONFIRMED", prospective_status="FAIL"),
    ]

    # Missing/invalid numeric evidence has explicit fail-closed reasons.
    for field, reason in (
        ("pbo", "PBO_MISSING_OR_INVALID"),
        ("psr", "PSR_MISSING_OR_INVALID"),
        ("dsr", "DSR_MISSING_OR_INVALID"),
        ("power", "POWER_MISSING_OR_INVALID"),
    ):
        rows.append(_mutation(f"{field}_missing", reason, **{field: None}))

    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = run_campaign()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["mutation", "expected_reason", "detected", "status", "reasons"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return 0 if rows and all(row["detected"] is True for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
