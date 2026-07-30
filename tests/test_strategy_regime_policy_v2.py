from core.strategy_regime_policy import (
    ADVISORY_ONLY,
    BLOCKED,
    ELIGIBLE,
    ELIGIBLE_WITH_PENALTY,
    WATCHLIST_ONLY,
    canonical_entropy_state,
    canonical_session_bucket,
    canonical_strategy_family,
    evaluate_strategy_regime_policy,
)


def evaluate(strategy, **overrides):
    payload = {
        "strategy": strategy,
        "session_bucket": "MID_SESSION",
        "entropy_value": 0.5,
        "normalized_entropy": 0.5,
        "entropy_state": "NORMAL",
    }
    payload.update(overrides)
    return evaluate_strategy_regime_policy(**payload)


def test_real_opening_strategy_ids_resolve_to_opening_family():
    assert canonical_strategy_family("opening_drive_v1") == "OPENING_BREAKOUT"
    assert canonical_strategy_family("opening_range_retest_v1") == "OPENING_BREAKOUT"


def test_real_reversal_strategy_ids_resolve_to_mean_reversion():
    assert canonical_strategy_family("mean_reversion_extension_v1") == "MEAN_REVERSION"
    assert canonical_strategy_family("failed_breakout_trap_v1") == "MEAN_REVERSION"
    assert canonical_strategy_family("market_event_graph_reversal_v1") == "MEAN_REVERSION"


def test_real_directional_strategy_ids_resolve_to_trend_family():
    assert canonical_strategy_family("trend_pullback_v1") == "TREND_CONTINUATION"
    assert canonical_strategy_family("vwap_reclaim_rejection_v1") == "TREND_CONTINUATION"
    assert canonical_strategy_family("compression_breakout_v1") == "TREND_CONTINUATION"


def test_event_and_no_trade_ids_resolve():
    assert canonical_strategy_family("event_volatility_expansion_v1") == "EVENT_VOLATILITY"
    assert canonical_strategy_family("no_trade_chop_v1") == "NO_TRADE"


def test_legacy_session_aliases_are_canonicalized():
    assert canonical_session_bucket("MIDDAY_CHOP") == "MID_SESSION"
    assert canonical_session_bucket("LATE_DAY") == "CLOSING_VOL"
    assert canonical_session_bucket("MORNING_TREND") == "OPEN_DISCOVERY"


def test_entropy_state_can_be_derived_from_normalized_value():
    assert canonical_entropy_state("", 0.20) == "LOW"
    assert canonical_entropy_state("", 0.70) == "NORMAL"
    assert canonical_entropy_state("", 0.90) == "HIGH"
    assert canonical_entropy_state("", 0.98) == "EXTREME"


def test_opening_high_entropy_with_expansion_is_penalized_not_blocked():
    result = evaluate(
        "opening_drive_v1",
        session_bucket="OPEN_DISCOVERY",
        normalized_entropy=0.90,
        entropy_state="HIGH",
        volatility_expansion=True,
    )
    assert result["policy_result"] == ELIGIBLE_WITH_PENALTY
    assert result["strategy_family"] == "OPENING_BREAKOUT"
    assert result["candidate_generation_allowed"] is True


def test_opening_high_entropy_without_expansion_is_blocked():
    result = evaluate(
        "opening_range_retest_v1",
        session_bucket="OPEN_DISCOVERY",
        normalized_entropy=0.90,
        entropy_state="HIGH",
    )
    assert result["policy_result"] == BLOCKED
    assert result["candidate_generation_allowed"] is False


def test_opening_strategy_outside_opening_session_is_blocked():
    result = evaluate(
        "opening_drive_v1",
        session_bucket="MID_SESSION",
        entropy_state="LOW",
        normalized_entropy=0.20,
    )
    assert result["policy_result"] == BLOCKED
    assert result["reason"] == "session_bucket_mid_session_blocked"


def test_mean_reversion_normal_entropy_mid_session_is_eligible():
    result = evaluate(
        "mean_reversion_extension_v1",
        session_bucket="MIDDAY_CHOP",
        entropy_state="LOW",
        normalized_entropy=0.25,
        trend_state="RANGE",
    )
    assert result["policy_result"] == ELIGIBLE


def test_mean_reversion_high_entropy_is_advisory():
    result = evaluate(
        "failed_breakout_trap_v1",
        entropy_state="HIGH",
        normalized_entropy=0.90,
    )
    assert result["policy_result"] == ADVISORY_ONLY


def test_mean_reversion_does_not_fade_explicit_strong_trend():
    result = evaluate(
        "mean_reversion_extension_v1",
        entropy_state="NORMAL",
        trend_state="TREND_EXPANSION",
    )
    assert result["policy_result"] == ADVISORY_ONLY
    assert result["reason"] == "mean_reversion_strong_trend_advisory"


def test_stable_regime_requirement_is_enforced_when_explicit():
    result = evaluate(
        "mean_reversion_extension_v1",
        entropy_state="NORMAL",
        regime_status="UNCERTAIN",
        stable_regime=False,
    )
    assert result["policy_result"] == ADVISORY_ONLY
    assert result["reason"] == "stable_regime_required_advisory"


def test_trend_high_entropy_requires_confirmation():
    blocked = evaluate(
        "trend_pullback_v1",
        entropy_state="HIGH",
        normalized_entropy=0.90,
    )
    allowed = evaluate(
        "trend_pullback_v1",
        entropy_state="HIGH",
        normalized_entropy=0.90,
        trend_state="STRONG",
    )
    assert blocked["policy_result"] == BLOCKED
    assert allowed["policy_result"] == ELIGIBLE_WITH_PENALTY


def test_event_strategy_accepts_expected_high_uncertainty_with_penalty():
    result = evaluate(
        "event_volatility_expansion_v1",
        session_bucket="EVENT_MODE",
        entropy_state="EXTREME",
        normalized_entropy=0.98,
    )
    assert result["policy_result"] == ELIGIBLE_WITH_PENALTY
    assert result["strategy_family"] == "EVENT_VOLATILITY"


def test_short_premium_poor_liquidity_is_blocked():
    result = evaluate(
        "SHORT_STRADDLE",
        entropy_state="LOW",
        normalized_entropy=0.20,
        liquidity_quality="POOR",
    )
    assert result["policy_result"] == BLOCKED
    assert result["reason"] == "poor_liquidity_blocked"


def test_explicit_no_trade_strategy_is_always_blocked():
    result = evaluate(
        "no_trade_chop_v1",
        entropy_state="LOW",
        normalized_entropy=0.10,
    )
    assert result["policy_result"] == BLOCKED
    assert result["reason"] == "explicit_no_trade_strategy"


def test_invalid_regime_truth_is_advisory_for_known_strategy():
    result = evaluate(
        "trend_pullback_v1",
        entropy_state="NORMAL",
        regime_status="INVALID_INPUT",
    )
    assert result["policy_result"] == ADVISORY_ONLY


def test_unknown_strategy_remains_conservative():
    low = evaluate(
        "unknown_alpha",
        entropy_state="LOW",
        normalized_entropy=0.20,
    )
    high = evaluate(
        "unknown_alpha",
        entropy_state="HIGH",
        normalized_entropy=0.90,
    )
    assert low["policy_result"] == WATCHLIST_ONLY
    assert high["policy_result"] == BLOCKED
