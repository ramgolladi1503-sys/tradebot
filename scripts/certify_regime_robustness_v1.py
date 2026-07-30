#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path

from core.regime_contract_v2 import (
    INSUFFICIENT_DATA,
    INVALID_INPUT,
    RegimeStabilizer,
    UNCERTAIN,
    VALID,
    normalized_heuristic_scores,
    probability_diagnostics,
    stable_softmax,
)
from core.regime_entropy_gate import evaluate_regime_entropy_gate
from core.regime_prob_model import REGIMES, RegimeProbModel


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


def _append(checks, name, passed, evidence):
    checks.append(
        {
            "name": str(name),
            "passed": bool(passed),
            "evidence": evidence,
        }
    )


def _heuristic_model() -> RegimeProbModel:
    return RegimeProbModel(
        "runtime/diagnostics/nonexistent_regime_model.json"
    )


def certify() -> dict:
    checks: list[dict] = []

    scores, quality = normalized_heuristic_scores(
        _features(oi_delta=10**12, oi_gross=None)
    )
    probabilities = stable_softmax(scores)
    _append(
        checks,
        "raw_oi_bounded",
        quality.get("status") == VALID
        and -1.0 <= quality["normalization"]["oi_normalized"] <= 1.0
        and max(probabilities.values()) < 0.90
        and math.isclose(sum(probabilities.values()), 1.0, abs_tol=1e-12),
        {
            "oi_normalized": quality["normalization"]["oi_normalized"],
            "max_probability": max(probabilities.values()),
            "probability_sum": sum(probabilities.values()),
        },
    )

    rounded = {
        "TREND": 0.333333,
        "RANGE": 0.222222,
        "RANGE_VOLATILE": 0.166667,
        "EVENT": 0.166667,
        "PANIC": 0.111112,
    }
    rounded_diag = probability_diagnostics(rounded)
    _append(
        checks,
        "rounded_probability_compatibility",
        math.isclose(
            sum(rounded_diag["probabilities"].values()),
            1.0,
            abs_tol=1e-12,
        )
        and math.isclose(
            rounded_diag["input_probability_sum"],
            1.000001,
            abs_tol=1e-12,
        ),
        rounded_diag,
    )

    model = _heuristic_model()
    missing = model.predict(_features(adx=None))
    _append(
        checks,
        "missing_feature_fail_closed",
        missing.get("regime_status") == INSUFFICIENT_DATA
        and missing.get("primary_regime") == "UNKNOWN"
        and missing.get("unstable_regime_flag") is True,
        missing,
    )

    invalid = model.predict(_features(atr_pct=0.0))
    _append(
        checks,
        "non_positive_atr_fail_closed",
        invalid.get("regime_status") == INVALID_INPUT
        and invalid.get("primary_regime") == "UNKNOWN"
        and invalid.get("unstable_regime_flag") is True,
        invalid,
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
    _append(
        checks,
        "low_entropy_not_blocked",
        low_entropy.get("normalized_entropy") == 0.0
        and low_entropy.get("uncertain") is False
        and low_entropy.get("low_entropy_suspect") is False,
        low_entropy,
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
    _append(
        checks,
        "invalid_probability_vector_fail_closed",
        invalid_vector.get("probability_valid") is False
        and invalid_vector.get("uncertain") is True,
        invalid_vector,
    )

    unknown_label = evaluate_regime_entropy_gate(
        probabilities={
            "TREND": 1.0,
            "RANGE": 0.0,
            "RANGE_VOLATILE": 0.0,
            "EVENT": 0.0,
            "PANIC": 0.0,
            "NEUTRAL": 0.1,
        }
    )
    _append(
        checks,
        "unknown_probability_label_fail_closed",
        unknown_label.get("probability_valid") is False
        and unknown_label.get("uncertain") is True,
        unknown_label,
    )

    clear_trend = model.predict(
        _features(
            adx=35.0,
            vol_z=0.5,
            atr_pct=0.008,
            iv_mean=0.18,
            oi_delta=3_000_000.0,
            oi_gross=10_000_000.0,
            depth_imbalance=0.4,
            x_regime_align=0.5,
        )
    )
    _append(
        checks,
        "clear_trend_discriminative",
        clear_trend.get("primary_regime") == "TREND"
        and clear_trend.get("regime_status") == VALID
        and clear_trend.get("regime_prob_max", 0.0) >= 0.80,
        clear_trend,
    )

    clear_range = model.predict(
        _features(
            adx=10.0,
            vol_z=-0.5,
            atr_pct=0.003,
            iv_mean=0.15,
            oi_delta=0.0,
            depth_imbalance=0.0,
        )
    )
    _append(
        checks,
        "clear_range_discriminative",
        clear_range.get("primary_regime") == "RANGE"
        and clear_range.get("regime_status") == VALID
        and clear_range.get("regime_prob_max", 0.0) >= 0.90,
        clear_range,
    )

    clear_range_volatile = model.predict(
        _features(
            adx=14.0,
            vol_z=1.8,
            atr_pct=0.011,
            iv_mean=0.25,
            oi_delta=0.0,
            depth_imbalance=0.0,
        )
    )
    _append(
        checks,
        "clear_range_volatile_discriminative",
        clear_range_volatile.get("primary_regime") == "RANGE_VOLATILE"
        and clear_range_volatile.get("regime_status") == VALID
        and clear_range_volatile.get("regime_prob_max", 0.0) >= 0.75,
        clear_range_volatile,
    )

    mixed = model.predict(
        _features(
            adx=28.0,
            vol_z=1.4,
            atr_pct=0.003,
            iv_mean=0.20,
            shock_score=0.1,
            uncertainty_index=0.2,
            oi_delta=0.0,
            depth_imbalance=0.0,
        )
    )
    _append(
        checks,
        "mixed_structure_remains_uncertain",
        mixed.get("regime_status") == UNCERTAIN
        and mixed.get("regime_entropy_normalized", 0.0)
        > mixed.get("regime_entropy_threshold", 1.0)
        and mixed.get("regime_prob_max", 1.0) < 0.40,
        mixed,
    )

    panic = model.predict(
        _features(
            adx=30.0,
            vol_z=2.5,
            atr_pct=0.015,
            iv_mean=0.60,
            shock_score=0.9,
            uncertainty_index=0.8,
            regime_transition_rate=8.0,
            ltp_acceleration_atr=1.0,
            x_lead_lag=1.0,
            macro_direction_bias=-1.0,
        )
    )
    _append(
        checks,
        "panic_requires_composite_evidence",
        panic.get("primary_regime") == "PANIC"
        and panic.get("regime_status") == VALID
        and panic.get("regime_prob_max", 0.0) >= 0.65,
        panic,
    )

    provenance = model.predict(_features())
    _append(
        checks,
        "heuristic_provenance_is_uncalibrated",
        provenance.get("model_source")
        == "HEURISTIC_STRUCTURAL_V2_UNCALIBRATED"
        and provenance.get("probability_calibrated") is False
        and provenance.get("probability_semantics")
        == "deterministic_structural_pseudo_probability",
        provenance,
    )

    with tempfile.TemporaryDirectory() as tmp:
        model_path = Path(tmp) / "regime_model.json"
        payload = {
            "feature_names": ["adx", "atr_pct"],
            "calibrated": False,
            "priors": {regime: 0.2 for regime in REGIMES},
            "means": {
                regime: {"adx": 20.0, "atr_pct": 0.005}
                for regime in REGIMES
            },
            "vars": {
                regime: {"adx": 10.0, "atr_pct": 0.0001}
                for regime in REGIMES
            },
        }
        model_path.write_text(json.dumps(payload), encoding="utf-8")
        schema_result = RegimeProbModel(str(model_path)).predict({"adx": 25.0})
    _append(
        checks,
        "trained_model_schema_missing_feature_fail_closed",
        schema_result.get("regime_status") == INSUFFICIENT_DATA
        and schema_result.get("primary_regime") == "UNKNOWN"
        and schema_result.get("feature_quality", {}).get("missing_required")
        == ["atr_pct"],
        schema_result,
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
    _append(
        checks,
        "completed_bar_hysteresis",
        first.get("stable_regime") == "UNKNOWN"
        and duplicate.get("transition_confirmation_count") == 1
        and confirmed.get("stable_regime") == "TREND",
        {
            "first": first,
            "duplicate": duplicate,
            "confirmed": confirmed,
        },
    )

    passed = all(bool(check.get("passed")) for check in checks)
    return {
        "schema_version": 2,
        "verdict": (
            "DETERMINISTIC_CERTIFIED" if passed else "CERTIFICATION_FAILED"
        ),
        "passed": passed,
        "check_count": len(checks),
        "passed_count": sum(1 for check in checks if check.get("passed")),
        "checks": checks,
        "safety": {
            "read_only": True,
            "broker_api_called": False,
            "is_order_action": False,
            "feed_files_modified": False,
            "probability_calibrated": False,
            "live_market_certification": False,
            "predictive_edge_certification": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=(
            "runtime/diagnostics/regime_robustness_v1/certification.json"
        ),
    )
    args = parser.parse_args()
    report = certify()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
