#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.strategy_regime_policy import (
    ADVISORY_ONLY,
    BLOCKED,
    ELIGIBLE,
    ELIGIBLE_WITH_PENALTY,
    REGIME_POLICY_VERSION,
    canonical_session_bucket,
    canonical_strategy_family,
    evaluate_strategy_regime_policy,
)


def _evaluate(strategy: str, **overrides):
    payload = {
        "strategy": strategy,
        "session_bucket": "MID_SESSION",
        "entropy_value": 0.5,
        "normalized_entropy": 0.5,
        "entropy_state": "NORMAL",
    }
    payload.update(overrides)
    return evaluate_strategy_regime_policy(**payload)


def _append(checks: list[dict], name: str, passed: bool, evidence: dict) -> None:
    checks.append(
        {
            "name": str(name),
            "passed": bool(passed),
            "evidence": dict(evidence),
        }
    )


def certify() -> dict:
    checks: list[dict] = []

    aliases = {
        "opening_drive_v1": "OPENING_BREAKOUT",
        "opening_range_retest_v1": "OPENING_BREAKOUT",
        "mean_reversion_extension_v1": "MEAN_REVERSION",
        "failed_breakout_trap_v1": "MEAN_REVERSION",
        "trend_pullback_v1": "TREND_CONTINUATION",
        "vwap_reclaim_rejection_v1": "TREND_CONTINUATION",
        "event_volatility_expansion_v1": "EVENT_VOLATILITY",
        "no_trade_chop_v1": "NO_TRADE",
    }
    resolved_aliases = {
        strategy: canonical_strategy_family(strategy)
        for strategy in aliases
    }
    _append(
        checks,
        "real_strategy_ids_canonicalized",
        resolved_aliases == aliases,
        {"expected": aliases, "resolved": resolved_aliases},
    )

    sessions = {
        "MIDDAY_CHOP": "MID_SESSION",
        "LATE_DAY": "CLOSING_VOL",
        "MORNING_TREND": "OPEN_DISCOVERY",
        "EVENT": "EVENT_MODE",
    }
    resolved_sessions = {
        session: canonical_session_bucket(session)
        for session in sessions
    }
    _append(
        checks,
        "legacy_sessions_canonicalized",
        resolved_sessions == sessions,
        {"expected": sessions, "resolved": resolved_sessions},
    )

    opening = _evaluate(
        "opening_drive_v1",
        session_bucket="OPEN_DISCOVERY",
        normalized_entropy=0.90,
        entropy_state="HIGH",
        volatility_expansion=True,
    )
    _append(
        checks,
        "opening_high_entropy_requires_expansion",
        opening.get("policy_result") == ELIGIBLE_WITH_PENALTY
        and opening.get("strategy_family") == "OPENING_BREAKOUT",
        opening,
    )

    opening_wrong_session = _evaluate(
        "opening_drive_v1",
        session_bucket="MID_SESSION",
        normalized_entropy=0.20,
        entropy_state="LOW",
    )
    _append(
        checks,
        "opening_wrong_session_blocked",
        opening_wrong_session.get("policy_result") == BLOCKED,
        opening_wrong_session,
    )

    mean_reversion = _evaluate(
        "mean_reversion_extension_v1",
        session_bucket="MIDDAY_CHOP",
        normalized_entropy=0.25,
        entropy_state="LOW",
        trend_state="RANGE",
    )
    _append(
        checks,
        "mean_reversion_range_evidence_eligible",
        mean_reversion.get("policy_result") == ELIGIBLE,
        mean_reversion,
    )

    mean_reversion_strong_trend = _evaluate(
        "mean_reversion_extension_v1",
        normalized_entropy=0.50,
        entropy_state="NORMAL",
        trend_state="TREND_EXPANSION",
    )
    _append(
        checks,
        "mean_reversion_strong_trend_advisory",
        mean_reversion_strong_trend.get("policy_result") == ADVISORY_ONLY,
        mean_reversion_strong_trend,
    )

    trend_without_confirmation = _evaluate(
        "trend_pullback_v1",
        normalized_entropy=0.90,
        entropy_state="HIGH",
    )
    trend_with_confirmation = _evaluate(
        "trend_pullback_v1",
        normalized_entropy=0.90,
        entropy_state="HIGH",
        trend_state="STRONG",
    )
    _append(
        checks,
        "trend_high_entropy_confirmation_contract",
        trend_without_confirmation.get("policy_result") == BLOCKED
        and trend_with_confirmation.get("policy_result")
        == ELIGIBLE_WITH_PENALTY,
        {
            "without_confirmation": trend_without_confirmation,
            "with_confirmation": trend_with_confirmation,
        },
    )

    event = _evaluate(
        "event_volatility_expansion_v1",
        session_bucket="EVENT_MODE",
        normalized_entropy=0.98,
        entropy_state="EXTREME",
    )
    _append(
        checks,
        "event_uncertainty_penalized_not_hidden",
        event.get("policy_result") == ELIGIBLE_WITH_PENALTY,
        event,
    )

    explicit_no_trade = _evaluate(
        "no_trade_chop_v1",
        normalized_entropy=0.10,
        entropy_state="LOW",
    )
    _append(
        checks,
        "explicit_no_trade_always_blocked",
        explicit_no_trade.get("policy_result") == BLOCKED,
        explicit_no_trade,
    )

    unknown_low = _evaluate(
        "unknown_alpha_v1",
        normalized_entropy=0.20,
        entropy_state="LOW",
    )
    unknown_high = _evaluate(
        "unknown_alpha_v1",
        normalized_entropy=0.90,
        entropy_state="HIGH",
    )
    _append(
        checks,
        "unknown_strategy_never_executable_policy",
        unknown_low.get("policy_result") == ADVISORY_ONLY
        and unknown_high.get("policy_result") == BLOCKED,
        {"low_entropy": unknown_low, "high_entropy": unknown_high},
    )

    invalid_truth = _evaluate(
        "trend_pullback_v1",
        normalized_entropy=0.50,
        entropy_state="NORMAL",
        regime_status="INVALID_INPUT",
    )
    _append(
        checks,
        "invalid_regime_truth_advisory",
        invalid_truth.get("policy_result") == ADVISORY_ONLY,
        invalid_truth,
    )

    passed = all(bool(check.get("passed")) for check in checks)
    return {
        "schema_version": 1,
        "regime_policy_version": REGIME_POLICY_VERSION,
        "verdict": (
            "POLICY_DETERMINISTIC_CERTIFIED"
            if passed
            else "POLICY_CERTIFICATION_FAILED"
        ),
        "passed": passed,
        "check_count": len(checks),
        "passed_count": sum(1 for check in checks if check.get("passed")),
        "checks": checks,
        "safety": {
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "unknown_strategy_executable": False,
            "live_market_certification": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=(
            "runtime/diagnostics/regime_robustness_v1/"
            "strategy_regime_policy_certification.json"
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
