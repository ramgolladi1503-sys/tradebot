#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from core.regime_contract_v2 import (
    INSUFFICIENT_DATA,
    INVALID_INPUT,
    RegimeStabilizer,
    VALID,
    normalized_heuristic_scores,
    probability_diagnostics,
    stable_softmax,
)
from core.regime_entropy_gate import evaluate_regime_entropy_gate
from core.regime_prob_model import RegimeProbModel


def _features(**overrides):
    row = {
        "adx": 28.0,
        "vwap_slope": 1.5,
        "vol_z": 1.2,
        "atr_pct": 0.006,
        "iv_mean": 18.0,
        "ltp_acceleration": 2.0,
        "option_chain_skew": 0.01,
        "oi_delta": 250_000.0,
        "oi_gross": 10_000_000.0,
        "depth_imbalance": 0.2,
        "regime_transition_rate": 0.0,
        "shock_score": 0.0,
        "uncertainty_index": 0.0,
        "macro_direction_bias": 0.0,
        "x_regime_align": 0.0,
        "x_vol_spillover": 0.0,
        "x_lead_lag": 0.0,
    }
    row.update(overrides)
    return row


def certify() -> dict:
    checks: list[dict] = []

    scores, quality = normalized_heuristic_scores(
        _features(oi_delta=10**12, oi_gross=None)
    )
    probabilities = stable_softmax(scores)
    checks.append(
        {
            "name": "raw_oi_bounded",
            "passed": bool(
                quality.get("status") == VALID
                and -1.0
                <= quality["normalization"]["oi_normalized"]
                <= 1.0
                and max(probabilities.values()) < 0.90
                and math.isclose(
                    sum(probabilities.values()), 1.0, abs_tol=1e-12
                )
            ),
            "evidence": {
                "oi_normalized": quality["normalization"]["oi_normalized"],
                "max_probability": max(probabilities.values()),
                "probability_sum": sum(probabilities.values()),
            },
        }
    )

    rounded = {
        "TREND": 0.333333,
        "RANGE": 0.222222,
        "RANGE_VOLATILE": 0.166667,
        "EVENT": 0.166667,
        "PANIC": 0.111112,
    }
    rounded_diag = probability_diagnostics(rounded)
    checks.append(
        {
            "name": "rounded_probability_compatibility",
            "passed": bool(
                math.isclose(
                    sum(rounded_diag["probabilities"].values()),
                    1.0,
                    abs_tol=1e-12,
                )
                and math.isclose(
                    rounded_diag["input_probability_sum"],
                    1.000001,
                    abs_tol=1e-12,
                )
            ),
            "evidence": rounded_diag,
        }
    )

    model = RegimeProbModel("runtime/diagnostics/nonexistent_regime_model.json")
    missing = model.predict(_features(adx=None))
    checks.append(
        {
            "name": "missing_feature_fail_closed",
            "passed": bool(
                missing.get("regime_status") == INSUFFICIENT_DATA
                and missing.get("primary_regime") == "UNKNOWN"
                and missing.get("unstable_regime_flag") is True
            ),
            "evidence": {
                "status": missing.get("regime_status"),
                "primary_regime": missing.get("primary_regime"),
                "feature_quality": missing.get("feature_quality"),
            },
        }
    )

    invalid = model.predict(_features(atr_pct=0.0))
    checks.append(
        {
            "name": "non_positive_atr_fail_closed",
            "passed": bool(
                invalid.get("regime_status") == INVALID_INPUT
                and invalid.get("primary_regime") == "UNKNOWN"
                and invalid.get("unstable_regime_flag") is True
            ),
            "evidence": {
                "status": invalid.get("regime_status"),
                "feature_quality": invalid.get("feature_quality"),
            },
        }
    )

    low_entropy = evaluate_regime_entropy_gate(
        probabilities={
            "TREND": 1.0,
            "RANGE": 0.0,
            "RANGE_VOLATILE": 0.0,
            "EVENT": 0.0,
            "PANIC": 0.0,
        },
        market_data={"feature_quality_status": VALID},
        primary_regime="TREND",
    )
    checks.append(
        {
            "name": "low_entropy_not_blocked",
            "passed": bool(
                low_entropy.get("normalized_entropy") == 0.0
                and low_entropy.get("uncertain") is False
                and low_entropy.get("low_entropy_suspect") is False
            ),
            "evidence": low_entropy,
        }
    )

    invalid_vector = evaluate_regime_entropy_gate(
        probabilities={
            "TREND": 0.9,
            "RANGE": 0.9,
            "RANGE_VOLATILE": 0.0,
            "EVENT": 0.0,
            "PANIC": 0.0,
        }
    )
    checks.append(
        {
            "name": "invalid_probability_vector_fail_closed",
            "passed": bool(
                invalid_vector.get("probability_valid") is False
                and invalid_vector.get("uncertain") is True
            ),
            "evidence": invalid_vector,
        }
    )

    stabilizer = RegimeStabilizer(
        confirmation_bars=3,
        minimum_dwell_bars=0,
    )
    first = stabilizer.update(
        symbol="NIFTY",
        completed_bar=1,
        instantaneous_regime="TREND",
        top_probability=0.70,
        status=VALID,
    )
    duplicate = stabilizer.update(
        symbol="NIFTY",
        completed_bar=1,
        instantaneous_regime="TREND",
        top_probability=0.70,
        status=VALID,
    )
    stabilizer.update(
        symbol="NIFTY",
        completed_bar=2,
        instantaneous_regime="TREND",
        top_probability=0.70,
        status=VALID,
    )
    confirmed = stabilizer.update(
        symbol="NIFTY",
        completed_bar=3,
        instantaneous_regime="TREND",
        top_probability=0.70,
        status=VALID,
    )
    checks.append(
        {
            "name": "completed_bar_hysteresis",
            "passed": bool(
                first.get("stable_regime") == "UNKNOWN"
                and duplicate.get("transition_confirmation_count") == 1
                and confirmed.get("stable_regime") == "TREND"
            ),
            "evidence": {
                "first": first,
                "duplicate": duplicate,
                "confirmed": confirmed,
            },
        }
    )

    passed = all(bool(check.get("passed")) for check in checks)
    return {
        "schema_version": 1,
        "verdict": "DETERMINISTIC_CERTIFIED" if passed else "CERTIFICATION_FAILED",
        "passed": passed,
        "check_count": len(checks),
        "passed_count": sum(1 for check in checks if check.get("passed")),
        "checks": checks,
        "safety": {
            "read_only": True,
            "broker_api_called": False,
            "is_order_action": False,
            "feed_files_modified": False,
            "live_market_certification": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="runtime/diagnostics/regime_robustness_v1/certification.json",
    )
    args = parser.parse_args()
    report = certify()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
