from __future__ import annotations

from core.feed_truth_contract import (
    AUTH_BLOCKED,
    DEGRADED,
    DISCONNECTED,
    IMPORT_MISSING,
    LIVE,
    RECOVERY_BLOCKED,
    STALE,
    UNKNOWN,
    build_feed_truth_contract,
)


def test_live_fresh_option_feed_allows_entries():
    contract = build_feed_truth_contract(
        {
            "runtime_state": "RUNNING",
            "ws_connected": True,
            "feed_truth_state": "LIVE",
            "feed_ok": True,
            "feed_truth_strict_live": True,
            "quote_health": {"state": "OK", "stale_reasons": []},
        }
    )

    assert contract.state == LIVE
    assert contract.entries_allowed is True
    assert contract.exits_allowed is True
    assert contract.quotes_trusted is True
    assert contract.depth_trusted is True
    assert contract.reconnect_allowed is True
    assert contract.process_restart_required is False
    assert contract.blockers == ()
    assert contract.advisory_reasons == ()


def test_disconnected_blocks_entries_and_untrusts_quotes():
    contract = build_feed_truth_contract(
        {
            "runtime_state": "RUNNING",
            "ws_connected": False,
            "feed_truth_state": "DEAD",
            "quote_health": {"state": "OK"},
        }
    )

    assert contract.state == DISCONNECTED
    assert contract.entries_allowed is False
    assert contract.quotes_trusted is False
    assert contract.depth_trusted is False
    assert "DISCONNECTED" in contract.blockers


def test_stale_option_ltp_blocks_entries():
    contract = build_feed_truth_contract(
        {
            "runtime_state": "RUNNING",
            "ws_connected": True,
            "feed_truth_state": "LIVE",
            "feed_truth_reason_code": "STALE_OPTION_LTP",
            "quote_health": {"state": "STALE", "stale_reasons": ["LTP_STALE"]},
        }
    )

    assert contract.state == STALE
    assert contract.entries_allowed is False
    assert contract.quotes_trusted is False
    assert contract.depth_trusted is False
    assert "STALE" in contract.blockers
    assert contract.reconnect_allowed is True


def test_recovery_blocked_blocks_entries_even_when_quote_health_ok():
    contract = build_feed_truth_contract(
        {
            "runtime_state": "RECOVERY_BLOCKED",
            "ws_connected": False,
            "reconnect_blocked_reason": "ws1006_process_restart_required",
            "quote_health": {"state": "OK", "stale_reasons": []},
        }
    )

    assert contract.state == RECOVERY_BLOCKED
    assert contract.entries_allowed is False
    assert contract.quotes_trusted is False
    assert contract.depth_trusted is False
    assert contract.process_restart_required is True
    assert contract.reconnect_allowed is False
    assert "RECOVERY_BLOCKED" in contract.blockers
    assert contract.source_snapshot["quote_health_state"] == "OK"


def test_auth_blocked_disallows_reconnect_and_entries():
    contract = build_feed_truth_contract({"runtime_state": "AUTH_BLOCKED", "ws_connected": False})

    assert contract.state == AUTH_BLOCKED
    assert contract.entries_allowed is False
    assert contract.reconnect_allowed is False
    assert contract.process_restart_required is False


def test_import_missing_disallows_reconnect_and_entries():
    contract = build_feed_truth_contract({"runtime_state": "IMPORT_MISSING", "ws_connected": False})

    assert contract.state == IMPORT_MISSING
    assert contract.entries_allowed is False
    assert contract.reconnect_allowed is False
    assert contract.process_restart_required is False


def test_process_restart_required_sets_terminal_flag():
    contract = build_feed_truth_contract(
        {
            "runtime_state": "RUNNING",
            "ws_connected": False,
            "reconnect_blocked_reason": "reactor_not_restartable_process_restart_required",
        }
    )

    assert contract.state == RECOVERY_BLOCKED
    assert contract.process_restart_required is True
    assert contract.reconnect_allowed is False
    assert contract.entries_allowed is False


def test_duplicate_blockers_are_deduped_deterministically():
    contract = build_feed_truth_contract(
        {
            "runtime_state": "RECOVERY_BLOCKED",
            "ws_connected": False,
            "feed_truth_state": "RECOVERY_BLOCKED",
            "feed_truth_reason_code": "WS_DISCONNECTED",
            "reconnect_blocked_reason": "ws1006_process_restart_required",
            "quote_health": {"state": "OK", "stale_reasons": ["RECOVERY_BLOCKED", "RECOVERY_BLOCKED"]},
        }
    )

    assert contract.blockers == ("RECOVERY_BLOCKED", "DISCONNECTED")


def test_ok_markers_are_not_blockers():
    contract = build_feed_truth_contract(
        {
            "runtime_state": "RUNNING",
            "ws_connected": True,
            "feed_truth_state": "LIVE",
            "quote_health": {"state": "OK", "stale_reasons": ["OK", "LIVE", "FRESH", "NONE"]},
            "option_feed_block_reason": "OK",
        }
    )

    assert contract.state == LIVE
    assert contract.blockers == ()


def test_latency_guard_ok_is_not_blocker():
    contract = build_feed_truth_contract(
        {
            "runtime_state": "RUNNING",
            "ws_connected": True,
            "feed_truth_state": "LIVE",
            "latency_guard": {
                "latency_guard_triggered": True,
                "latency_guard_action": "OK",
                "latency_guard_reason": "LATENCY_GUARD_OK",
            },
            "quote_health": {"state": "OK"},
        }
    )

    assert contract.state == LIVE
    assert contract.advisory_reasons == ()
    assert contract.blockers == ()


def test_missing_feed_input_fails_closed():
    contract = build_feed_truth_contract({})

    assert contract.state == UNKNOWN
    assert contract.entries_allowed is False
    assert contract.reconnect_allowed is False
    assert contract.blockers == ("UNKNOWN_INPUT",)


def test_quote_health_ok_does_not_override_runtime_blocked_truth():
    contract = build_feed_truth_contract(
        {
            "runtime_state": "RECOVERY_BLOCKED",
            "ws_connected": False,
            "reconnect_blocked_reason": "ws1006_process_restart_required",
            "quote_health": {"state": "OK"},
            "feed_ok": True,
            "feed_truth_strict_live": True,
        }
    )

    assert contract.state == RECOVERY_BLOCKED
    assert contract.entries_allowed is False
    assert contract.quotes_trusted is False
    assert contract.depth_trusted is False
    assert contract.source_snapshot["quote_health_state"] == "OK"
    assert "RECOVERY_BLOCKED" in contract.blockers
