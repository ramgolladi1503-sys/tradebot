#!/usr/bin/env python3
"""Evaluate only the three HUNT V2 development nominations on validation.

No neighboring configuration is evaluated. No holdout economics are computed.
A validation pass is only permission to proceed to pre-holdout robustness work;
it is not an edge/certification claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

EXPECTED_DATASET_SHA = "66ddbfead966388262b9a1e49937fb227b711ce32f70eaf715a93a5e32572b32"
EXPECTED_GENERATION_SHA = "adc66a83fd04f6186cb25bbe924e230c7fb55548c2a2beb0c3ad49db9cee26dd"
EXPECTED_POLICY_ID = "HUNT_V2_VALIDATION_POLICY"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close_enough(a, b, tol=1e-12):
    if a is None or b is None:
        return a is b
    try:
        return math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol)
    except Exception:
        return False


def metrics_match(observed: dict, expected: dict) -> bool:
    if int(observed.get("trades", -1)) != int(expected.get("trades", -2)):
        return False
    for k in ("mean_net_bps", "win_rate", "total_net_bps"):
        if not close_enough(observed.get(k), expected.get(k)):
            return False
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--dataset", default="research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv")
    ap.add_argument("--generation", default="research/strategy_certification/passports/HUNT_V2_GENERATION_FREEZE.json")
    ap.add_argument("--policy", default="research/strategy_certification/passports/HUNT_V2_VALIDATION_POLICY.json")
    ap.add_argument("--development-evidence", default="research/evidence/strategy_certification/HUNT_V2_DEVELOPMENT_SCREEN.json")
    ap.add_argument("--output", default="research/evidence/strategy_certification/HUNT_V2_VALIDATION_RESULT.json")
    a = ap.parse_args(argv)

    root = Path(a.repo_root).resolve()
    dataset = root / a.dataset
    generation = root / a.generation
    policy_path = root / a.policy
    dev_path = root / a.development_evidence
    output = root / a.output

    result = {
        "status": "FAIL_CLOSED",
        "runtime_authority": "NONE",
        "broker_actions_permitted": False,
        "edge_claimed": False,
        "holdout_outcomes_accessed": False,
    }

    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        dev_evidence = json.loads(dev_path.read_text(encoding="utf-8"))

        if policy.get("policy_id") != EXPECTED_POLICY_ID or policy.get("status") != "FROZEN_PRE_VALIDATION":
            raise ValueError("validation_policy_identity_mismatch")
        if policy.get("generation_sha256") != EXPECTED_GENERATION_SHA or sha256(generation) != EXPECTED_GENERATION_SHA:
            raise ValueError("generation_hash_mismatch")
        if policy.get("dataset_sha256") != EXPECTED_DATASET_SHA or sha256(dataset) != EXPECTED_DATASET_SHA:
            raise ValueError("dataset_hash_mismatch")

        contract = policy["development_evidence_contract"]
        if dev_evidence.get("status") != contract["required_status"]:
            raise ValueError("development_status_mismatch")
        if int(dev_evidence.get("nominated_count", -1)) != int(contract["required_nominated_count"]):
            raise ValueError("development_nomination_count_mismatch")
        if bool(dev_evidence.get("validation_accessed")) is not contract["validation_accessed_must_be"]:
            raise ValueError("development_validation_access_violation")
        if bool(dev_evidence.get("holdout_accessed")) is not contract["holdout_accessed_must_be"]:
            raise ValueError("development_holdout_access_violation")
        if dev_evidence.get("generation_sha256") != EXPECTED_GENERATION_SHA:
            raise ValueError("development_generation_binding_mismatch")
        if dev_evidence.get("dataset_sha256") != EXPECTED_DATASET_SHA:
            raise ValueError("development_dataset_binding_mismatch")

        dev_by_id = {x["passport_id"]: x for x in dev_evidence.get("candidates", [])}
        for nomination in policy["nominations"]:
            pid = nomination["passport_id"]
            observed = dev_by_id.get(pid)
            if not observed or observed.get("development_status") != "NOMINATED_FOR_VALIDATION":
                raise ValueError("missing_frozen_nomination:" + pid)
            obs_nom = observed.get("nomination") or {}
            if obs_nom.get("config") != nomination["config"]:
                raise ValueError("nomination_config_mismatch:" + pid)
            if not metrics_match(obs_nom.get("metrics", {}), nomination["development_metrics"]):
                raise ValueError("nomination_metrics_mismatch:" + pid)

        script_dir = root / "scripts/research/hypothesis_factory"
        sys.path.insert(0, str(script_dir))
        import run_hunt_v2_development_screen as dev

        rows = dev.load_rows(dataset)
        sessions = sorted({r["session"] for r in rows})
        n_dev = int(len(sessions) * 0.6)
        n_val = int(len(sessions) * 0.2)
        validation_sessions = set(sessions[n_dev:n_dev + n_val])
        validation_idx = {i for i, r in enumerate(rows) if r["session"] in validation_sessions}

        if len(validation_sessions) != int(policy["validation_block"]["expected_sessions"]):
            raise ValueError("validation_session_count_mismatch")

        gate = policy["validation_gate"]
        candidate_results = []
        for nomination in policy["nominations"]:
            pid = nomination["passport_id"]
            config = nomination["config"]
            metrics = dev.evaluate(rows, validation_idx, pid, config, gate["cost_bps"])
            passed = (
                metrics["trades"] >= int(gate["minimum_trades"])
                and metrics["mean_net_bps"] is not None
                and metrics["total_net_bps"] is not None
                and metrics["mean_net_bps"] > 0
                and metrics["total_net_bps"] > 0
            )
            reasons = []
            if metrics["trades"] < int(gate["minimum_trades"]):
                reasons.append("INSUFFICIENT_VALIDATION_TRADES")
            if metrics["mean_net_bps"] is None or metrics["mean_net_bps"] <= 0:
                reasons.append("NONPOSITIVE_VALIDATION_MEAN")
            if metrics["total_net_bps"] is None or metrics["total_net_bps"] <= 0:
                reasons.append("NONPOSITIVE_VALIDATION_TOTAL")
            candidate_results.append({
                "passport_id": pid,
                "configuration": config,
                "verdict": "VALIDATION_PASS" if passed else "VALIDATION_FAIL",
                "reasons": reasons,
                "metrics": metrics,
            })

        advanced = [x for x in candidate_results if x["verdict"] == "VALIDATION_PASS"]
        result.update({
            "status": "VALIDATION_FAMILY_COMPLETE",
            "policy_sha256": sha256(policy_path),
            "development_evidence_sha256": sha256(dev_path),
            "generation_sha256": EXPECTED_GENERATION_SHA,
            "dataset_sha256": EXPECTED_DATASET_SHA,
            "sessions_total": len(sessions),
            "validation_sessions": len(validation_sessions),
            "candidates_evaluated": len(candidate_results),
            "candidates": candidate_results,
            "advanced_count": len(advanced),
            "advanced_passport_ids": [x["passport_id"] for x in advanced],
            "holdout_outcomes_accessed": False,
            "parameters_tuned": False,
            "next_action": (
                "FREEZE_PRE_HOLDOUT_ROBUSTNESS_POLICY_FOR_VALIDATION_SURVIVORS"
                if advanced else
                "CLOSE_HUNT_V2_NO_CANDIDATE_ADVANCED"
            ),
        })
    except Exception as e:
        result["error"] = f"{type(e).__name__}:{e}"

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "VALIDATION_FAMILY_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
