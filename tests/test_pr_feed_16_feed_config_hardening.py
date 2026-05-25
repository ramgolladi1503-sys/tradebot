from __future__ import annotations

import json

from core.feed_policy import (
    FEED_POLICY_CONFIG_BLOCKER,
    INVALID_FEED_POLICY,
    LIVE_FEED_POLICY,
    PAPER_FEED_POLICY,
    SIM_FEED_POLICY,
    FeedPolicyThresholds,
    classify_feed_with_policy,
    thresholds_for_mode,
    validate_feed_policy_config,
)


def _valid_config():
    return {
        "LIVE": {
            "mode": "LIVE",
            "policy_name": LIVE_FEED_POLICY,
            "max_option_tick_age_sec": 2.0,
            "max_ltp_age_sec": 2.0,
            "max_depth_age_sec": 4.0,
            "require_websocket": True,
            "require_symbol_truth": True,
        },
        "PAPER": {
            "mode": "PAPER",
            "policy_name": PAPER_FEED_POLICY,
            "max_option_tick_age_sec": 5.0,
            "max_ltp_age_sec": 5.0,
            "max_depth_age_sec": 10.0,
            "require_websocket": True,
            "require_symbol_truth": True,
        },
        "SIM": {
            "mode": "SIM",
            "policy_name": SIM_FEED_POLICY,
            "max_option_tick_age_sec": 60.0,
            "max_ltp_age_sec": 60.0,
            "max_depth_age_sec": 120.0,
            "require_websocket": False,
            "require_symbol_truth": False,
        },
    }


def _healthy_payload():
    return {
        "feed_ok": True,
        "effective_ws_connected": True,
        "runtime_state": "RUNNING",
        "state_machine": {"state": "LIVE"},
        "last_tick_age_sec": 0.5,
        "last_depth_age_sec": 1.0,
        "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
        "option_last_tick_age_by_symbol": {"NIFTY": 0.5},
    }


def test_default_feed_policy_config_is_valid_and_read_only():
    audit = validate_feed_policy_config()

    assert audit.read_only is True
    assert audit.is_order_action is False
    assert audit.append is False
    assert audit.config_ok is True
    assert audit.reason_code == "ok"
    assert audit.issues == ()
    assert [threshold.mode for threshold in audit.thresholds] == ["LIVE", "PAPER", "SIM"]


def test_valid_custom_policy_config_is_accepted():
    audit = validate_feed_policy_config(_valid_config())

    assert audit.config_ok is True
    assert audit.issues == ()
    assert thresholds_for_mode("LIVE", policy_config=_valid_config()).policy_name == LIVE_FEED_POLICY


def test_missing_required_mode_blocks_config():
    config = _valid_config()
    del config["PAPER"]

    audit = validate_feed_policy_config(config)

    assert audit.config_ok is False
    assert any(issue.field == "PAPER" and issue.reason == "required_mode_missing" for issue in audit.issues)


def test_non_positive_or_non_finite_threshold_blocks_config():
    config = _valid_config()
    config["LIVE"]["max_ltp_age_sec"] = 0
    config["PAPER"]["max_depth_age_sec"] = "nan"

    audit = validate_feed_policy_config(config)

    assert audit.config_ok is False
    assert any(issue.field == "LIVE.max_ltp_age_sec" for issue in audit.issues)
    assert any(issue.field == "PAPER.max_depth_age_sec" for issue in audit.issues)


def test_live_threshold_cannot_be_looser_than_paper():
    config = _valid_config()
    config["LIVE"]["max_option_tick_age_sec"] = 9.0

    audit = validate_feed_policy_config(config)

    assert audit.config_ok is False
    assert any(
        issue.field == "LIVE.max_option_tick_age_sec" and issue.reason == "threshold_must_be_lte_paper"
        for issue in audit.issues
    )


def test_paper_threshold_cannot_be_looser_than_sim():
    config = _valid_config()
    config["PAPER"]["max_depth_age_sec"] = 130.0

    audit = validate_feed_policy_config(config)

    assert audit.config_ok is False
    assert any(
        issue.field == "PAPER.max_depth_age_sec" and issue.reason == "threshold_must_be_lte_sim"
        for issue in audit.issues
    )


def test_live_and_paper_must_require_websocket_and_symbol_truth():
    config = _valid_config()
    config["LIVE"]["require_websocket"] = False
    config["PAPER"]["require_symbol_truth"] = False

    audit = validate_feed_policy_config(config)

    assert audit.config_ok is False
    assert any(issue.field == "LIVE.require_websocket" for issue in audit.issues)
    assert any(issue.field == "PAPER.require_symbol_truth" for issue in audit.issues)


def test_invalid_config_fails_closed_in_feed_policy_decision():
    config = _valid_config()
    config["LIVE"]["max_ltp_age_sec"] = -1

    decision = classify_feed_with_policy(
        _healthy_payload(),
        mode="LIVE",
        symbols=("NIFTY",),
        policy_config=config,
    )

    assert decision.feed_ok is False
    assert decision.policy_name == INVALID_FEED_POLICY
    assert decision.reason_code == FEED_POLICY_CONFIG_BLOCKER
    assert FEED_POLICY_CONFIG_BLOCKER in decision.reasons
    assert FEED_POLICY_CONFIG_BLOCKER in decision.blockers
    assert decision.thresholds.policy_name == INVALID_FEED_POLICY
    assert decision.is_order_action is False


def test_threshold_dataclass_config_is_validated_too():
    config = {
        "LIVE": FeedPolicyThresholds("LIVE", LIVE_FEED_POLICY, 2.0, 2.0, 4.0, True, True),
        "PAPER": FeedPolicyThresholds("PAPER", PAPER_FEED_POLICY, 5.0, 5.0, 10.0, True, True),
        "SIM": FeedPolicyThresholds("SIM", SIM_FEED_POLICY, 60.0, 60.0, 120.0, False, False),
    }

    audit = validate_feed_policy_config(config)

    assert audit.config_ok is True
    assert thresholds_for_mode("paper", policy_config=config).policy_name == PAPER_FEED_POLICY


def test_config_audit_is_json_serializable_and_non_action():
    audit = validate_feed_policy_config(_valid_config())

    payload = json.loads(audit.to_json())

    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["append"] is False
    assert payload["config_ok"] is True
    assert payload["metadata"]["policy_config"] == "feed_policy_config_v1"
