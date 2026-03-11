import pandas as pd

from core.trade_permission import (
    Permission,
    build_permission_payload,
    compute_global_conf,
    decide_permission,
    derive_direction,
)
from dashboard.utils import filter_by_permission


def test_direction_derivation():
    assert derive_direction("CE", "BUY") == "BULLISH"
    assert derive_direction("PE", "BUY") == "BEARISH"
    assert derive_direction("CE", "SELL") == "BEARISH"
    assert derive_direction("PE", "SELL") == "BULLISH"


def test_global_conf_damps_unknown_regime():
    val = compute_global_conf(
        signal_score=0.92,
        regime="UNKNOWN",
        regime_conf=0.0,
        orb_bias="NEUTRAL",
        direction="BULLISH",
    )
    assert val <= 0.10


def test_permission_unknown_low_conf_is_advisory_only():
    perm, reason = decide_permission(
        global_conf=0.55,
        regime="UNKNOWN",
        regime_conf=0.2,
        direction="BULLISH",
        orb_bias="NEUTRAL",
    )
    assert perm == Permission.ADVISORY_ONLY.value
    assert reason == "unknown_regime_low_conf"


def test_countertrend_queue_only():
    perm, _ = decide_permission(
        global_conf=0.70,
        regime="TREND_DOWN",
        regime_conf=0.9,
        direction="BULLISH",
        orb_bias="BULLISH",
    )
    assert perm == Permission.QUEUE_ONLY.value


def test_filtering_contract():
    df = pd.DataFrame(
        [
            {"trade_id": "T1", "permission": "EXECUTE"},
            {"trade_id": "T2", "permission": "QUEUE_ONLY"},
            {"trade_id": "T3", "permission": "ADVISORY_ONLY"},
        ]
    )
    out = filter_by_permission(df, "EXECUTE")
    assert list(out["trade_id"]) == ["T1"]


def test_permission_payload_strong_signal_reaches_execute_confidence():
    payload = build_permission_payload(
        signal_score=0.8,
        regime="TREND_UP",
        regime_conf=0.9,
        orb_bias="BULLISH",
        option_type="CE",
        side="BUY",
        execution_mode="LIVE",
    )
    assert payload["global_confidence"] == 0.72
    assert payload["permission"] == Permission.EXECUTE.value
    assert payload["permission_reason"] == "aligned_high_conf"
    assert payload["threshold_display"] == 0.0
    assert payload["threshold_advisory"] == 0.15
    assert payload["threshold_execution"] == 0.30
    assert payload["confidence_vs_threshold_reason"] == "meets_execution_threshold"


def test_permission_payload_missing_regime_conf_is_explicit_advisory():
    payload = build_permission_payload(
        signal_score=0.8,
        regime="TREND_UP",
        regime_conf=None,
        orb_bias="BULLISH",
        option_type="CE",
        side="BUY",
        execution_mode="LIVE",
    )
    assert payload["permission"] == Permission.ADVISORY_ONLY.value
    assert payload["permission_reason"] == "missing_regime_conf"


def test_permission_payload_normalizes_percentage_signal_once():
    payload = build_permission_payload(
        signal_score=80.0,  # percentage-like score from 0-100
        regime="TREND_UP",
        regime_conf=0.9,
        orb_bias="BULLISH",
        option_type="CE",
        side="BUY",
        execution_mode="LIVE",
    )
    assert payload["signal_score"] == 0.8
    assert payload["global_confidence"] == 0.72


def test_permission_payload_mid_confidence_is_queue_only_when_above_advisory_below_execution():
    payload = build_permission_payload(
        signal_score=0.29,
        regime="TREND_UP",
        regime_conf=1.0,
        orb_bias="BULLISH",
        option_type="CE",
        side="BUY",
        execution_mode="LIVE",
    )
    assert payload["global_confidence"] == 0.29
    assert payload["permission"] == Permission.QUEUE_ONLY.value
    assert payload["permission_reason"] == "medium_global_conf"
    assert payload["confidence_vs_threshold_reason"] == "meets_advisory_below_execution_threshold"
