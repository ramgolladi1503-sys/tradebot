from __future__ import annotations

from core.feed_freshness_gate import assess_feed_freshness_gate


def _freshness(**overrides):
    payload = {
        "ok": True,
        "state": "OK",
        "market_open": True,
        "allow_stale_quotes": False,
        "reasons": [],
        "ltp": {
            "ok": True,
            "age_sec": 0.4,
            "max_age_sec": 2.5,
            "required": True,
            "source": "feed_runtime_latest",
        },
        "depth": {
            "ok": True,
            "age_sec": 1.0,
            "max_age_sec": 6.0,
            "required": True,
            "source": "feed_runtime_latest",
        },
    }
    payload.update(overrides)
    return payload


def test_clean_market_open_fresh_feed_allows_execution():
    decision = assess_feed_freshness_gate(_freshness())

    assert decision.gate_state == "FRESH"
    assert decision.allowed_for_execution is True
    assert decision.allowed_for_paper_execution is True
    assert decision.allowed_for_live_execution is True
    assert decision.advisory_only is False
    assert decision.blockers == ()
    assert decision.is_order_action is False
    assert decision.append is False


def test_missing_status_blocks_fail_closed():
    decision = assess_feed_freshness_gate(None)

    assert decision.gate_state == "BLOCKED"
    assert decision.allowed_for_execution is False
    assert decision.allowed_for_paper_execution is False
    assert decision.allowed_for_live_execution is False
    assert "FEED_STATUS_MISSING" in decision.blockers


def test_market_closed_is_advisory_only_not_execution_grade():
    decision = assess_feed_freshness_gate(
        _freshness(ok=True, state="MARKET_CLOSED", market_open=False)
    )

    assert decision.gate_state == "ADVISORY_ONLY"
    assert decision.allowed_for_execution is False
    assert decision.allowed_for_paper_execution is False
    assert decision.allowed_for_live_execution is False
    assert decision.advisory_only is True
    assert "MARKET_CLOSED" in decision.blockers


def test_allow_stale_quotes_is_advisory_only_not_execution_grade():
    decision = assess_feed_freshness_gate(
        _freshness(ok=True, state="PLANNING", allow_stale_quotes=True)
    )

    assert decision.gate_state == "ADVISORY_ONLY"
    assert decision.allowed_for_execution is False
    assert decision.advisory_only is True
    assert "ALLOW_STALE_QUOTES_ACTIVE" in decision.blockers


def test_stale_ltp_blocks_execution():
    payload = _freshness(
        ok=False,
        state="STALE",
        reasons=["ltp_stale:NIFTY age=9.00 max=2.50"],
        ltp={"ok": False, "age_sec": 9.0, "max_age_sec": 2.5, "required": True},
    )

    decision = assess_feed_freshness_gate(payload)

    assert decision.gate_state == "BLOCKED"
    assert decision.allowed_for_execution is False
    assert "STALE_OPTION_LTP" in decision.blockers
    assert "FEED_NOT_OK" in decision.blockers


def test_missing_required_depth_blocks_execution():
    payload = _freshness(
        ok=False,
        state="DEGRADED",
        reasons=["depth_missing"],
        depth={"ok": False, "age_sec": None, "max_age_sec": 6.0, "required": True},
    )

    decision = assess_feed_freshness_gate(payload)

    assert decision.gate_state == "BLOCKED"
    assert decision.allowed_for_execution is False
    assert "MISSING_DEPTH" in decision.blockers
    assert "FEED_STATE_DEGRADED" in decision.blockers


def test_stale_required_depth_blocks_execution():
    payload = _freshness(
        ok=False,
        state="DEGRADED",
        reasons=["depth_stale age=12.00 max=6.00"],
        depth={"ok": False, "age_sec": 12.0, "max_age_sec": 6.0, "required": True},
    )

    decision = assess_feed_freshness_gate(payload)

    assert decision.gate_state == "BLOCKED"
    assert "STALE_OPTION_DEPTH" in decision.blockers


def test_runtime_stale_option_symbols_block_execution():
    decision = assess_feed_freshness_gate(
        _freshness(runtime_option_stale_symbols=["NIFTY"])
    )

    assert decision.gate_state == "BLOCKED"
    assert decision.allowed_for_execution is False
    assert "STALE_OPTION_LTP" in decision.blockers
    assert "RUNTIME_OPTION_STALE_SYMBOLS_PRESENT" in decision.warnings


def test_disconnected_feed_blocks_execution():
    decision = assess_feed_freshness_gate(
        _freshness(ok=False, state="DISCONNECTED", ws_connected=False, reasons=["ws_connected=false"])
    )

    assert decision.gate_state == "BLOCKED"
    assert decision.allowed_for_execution is False
    assert "FEED_DISCONNECTED" in decision.blockers


def test_to_dict_is_json_friendly_and_stable():
    decision = assess_feed_freshness_gate(_freshness())
    payload = decision.to_dict()

    assert payload["schema_version"] == 1
    assert payload["gate_state"] == "FRESH"
    assert payload["blockers"] == []
    assert payload["warnings"] == []
    assert payload["freshness_state"] == "OK"
    assert payload["ltp_age_sec"] == 0.4
    assert payload["depth_age_sec"] == 1.0
    assert payload["is_order_action"] is False
    assert payload["append"] is False
