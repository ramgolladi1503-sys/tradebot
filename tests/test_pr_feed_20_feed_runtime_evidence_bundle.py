from __future__ import annotations

import json

from core.feed_policy import FEED_POLICY_CONFIG_BLOCKER, LIVE_FEED_POLICY, PAPER_FEED_POLICY, SIM_FEED_POLICY
from core.feed_runtime_evidence import FEED_RUNTIME_EVIDENCE_SOURCE, build_feed_runtime_evidence_bundle


def _payload(*, option_age: float = 0.5, ltp_age: float = 0.5, depth_age: float = 1.0, ws_connected=True):
    return {
        "feed_ok": True,
        "effective_ws_connected": ws_connected,
        "runtime_state": "RUNNING",
        "state_machine": {"state": "LIVE", "runtime_state": "RUNNING", "secret": "do_not_emit"},
        "last_tick_age_sec": ltp_age,
        "last_depth_age_sec": depth_age,
        "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
        "option_last_tick_age_by_symbol": {"NIFTY": option_age},
        "ignored_secret_token": "should_not_be_copied_as_top_level_evidence",
    }


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


def test_feed_runtime_evidence_bundle_is_read_only_and_non_action():
    bundle = build_feed_runtime_evidence_bundle(_payload(), mode="PAPER", symbols=("nifty",), cycle_id="cycle-1")

    assert bundle.read_only is True
    assert bundle.append is False
    assert bundle.is_order_action is False
    assert bundle.broker_api_called is False
    assert bundle.mode == "PAPER"
    assert bundle.feed_ok is True
    assert bundle.symbols == ("NIFTY",)
    assert bundle.metadata["source"] == FEED_RUNTIME_EVIDENCE_SOURCE
    assert bundle.metadata["cycle_id"] == "cycle-1"
    assert bundle.metadata["policy_name"] == PAPER_FEED_POLICY


def test_feed_runtime_evidence_bundle_embeds_policy_and_config_audit_payloads():
    bundle = build_feed_runtime_evidence_bundle(
        _payload(option_age=3.0, ltp_age=3.0, depth_age=6.0),
        mode="LIVE",
        symbols=("NIFTY",),
    )

    assert bundle.feed_ok is False
    assert bundle.feed_policy_decision["policy_name"] == LIVE_FEED_POLICY
    assert bundle.feed_policy_decision["feed_ok"] is False
    assert bundle.feed_policy_config_audit["config_ok"] is True
    assert "ltp_ticks_stale" in bundle.reasons
    assert "NIFTY:option_ticks_stale" in bundle.reasons


def test_feed_runtime_evidence_bundle_sanitizes_runtime_snapshot():
    bundle = build_feed_runtime_evidence_bundle(_payload(), mode="PAPER", symbols=("NIFTY",))

    snapshot = bundle.runtime_feed_snapshot

    assert snapshot["payload_present"] is True
    assert snapshot["feed_ok"] is True
    assert snapshot["effective_ws_connected"] is True
    assert snapshot["state_machine"] == {"state": "LIVE", "runtime_state": "RUNNING"}
    assert "ignored_secret_token" not in snapshot
    assert "ignored_secret_token" in snapshot["snapshot_keys"]


def test_invalid_runtime_payload_fails_closed_in_bundle():
    bundle = build_feed_runtime_evidence_bundle(None, mode="PAPER", symbols=("NIFTY",))

    assert bundle.feed_ok is False
    assert bundle.reason_code == "feed_policy_blocked"
    assert bundle.runtime_feed_snapshot == {"payload_present": False, "payload_type": "NoneType"}
    assert "invalid_payload" in bundle.reasons


def test_invalid_policy_config_fails_closed_in_bundle():
    config = _valid_config()
    config["LIVE"]["max_ltp_age_sec"] = -1

    bundle = build_feed_runtime_evidence_bundle(
        _payload(),
        mode="LIVE",
        symbols=("NIFTY",),
        policy_config=config,
    )

    assert bundle.feed_ok is False
    assert bundle.reason_code == FEED_POLICY_CONFIG_BLOCKER
    assert FEED_POLICY_CONFIG_BLOCKER in bundle.reasons
    assert bundle.feed_policy_config_audit["config_ok"] is False
    assert bundle.metadata["config_ok"] is False


def test_feed_runtime_evidence_bundle_json_contains_required_non_action_fields():
    bundle = build_feed_runtime_evidence_bundle(_payload(), mode="PAPER", symbols=("NIFTY",))

    payload = json.loads(bundle.to_json())

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["feed_policy_decision"]["is_order_action"] is False
    assert payload["feed_policy_config_audit"]["is_order_action"] is False


def test_sim_runtime_evidence_bundle_uses_sim_policy():
    bundle = build_feed_runtime_evidence_bundle(
        _payload(option_age=30.0, ltp_age=30.0, depth_age=80.0, ws_connected=None),
        mode="BACKTEST",
        symbols=("NIFTY",),
    )

    assert bundle.mode == "SIM"
    assert bundle.feed_ok is True
    assert bundle.feed_policy_decision["policy_name"] == SIM_FEED_POLICY
