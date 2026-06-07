from __future__ import annotations

from pathlib import Path

import core.expectancy.expectancy_gate as expectancy_gate


def _row(**overrides: object) -> dict[str, object]:
    row = {
        "candidate_id": "cand-1",
        "trade_id": "trade-1",
        "strategy_family": "breakout",
        "regime": "LIVE",
        "index": "NIFTY",
        "expiry_type": "WEEKLY",
        "option_type": "CE",
        "direction": "BUY",
        "setup_id": "breakout__LIVE__HIGH__HIGH__WIDE__T08_11_UTC__WEEKLY__BUY__NIFTY__CE",
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "readiness": "READY",
        "execution_status": "executable",
        "candidate_status": "executable",
        "reportable_executable": True,
        "execution_allowed": True,
        "eligible_for_execution": True,
        "selected_for_execution": True,
        "tradable": True,
        "is_executable": True,
        "final_emit_block_reason": None,
        "permission_reason": None,
        "source_flags": {},
    }
    row.update(overrides)
    return row


def test_kill_setup_cannot_become_executable() -> None:
    gated = expectancy_gate.apply_expectancy_gate(_row(), expectancy_lookup={"breakout__LIVE__HIGH__HIGH__WIDE__T08_11_UTC__WEEKLY__BUY__NIFTY__CE": "KILL"})
    assert gated["expectancy_status"] == "KILL"
    assert gated["reportable_executable"] is False
    assert gated["execution_allowed"] is False
    assert gated["eligible_for_execution"] is False
    assert gated["permission"] == "BLOCK"
    assert gated["final_action"] == "BLOCK"
    assert gated["execution_status"] == "blocked"
    assert gated["readiness"] == "BLOCKED"
    assert gated["reason"] == gated["expectancy_gate_reason"] == "expectancy_kill"


def test_insufficient_data_setup_cannot_become_executable() -> None:
    gated = expectancy_gate.apply_expectancy_gate(_row(), expectancy_lookup=None)
    assert gated["expectancy_status"] == "INSUFFICIENT_DATA"
    assert gated["reportable_executable"] is False
    assert gated["execution_allowed"] is False
    assert gated["eligible_for_execution"] is False
    assert gated["permission"] == "QUEUE_ONLY"
    assert gated["final_action"] == "QUEUE_ONLY"
    assert gated["execution_status"] == "queue_only"
    assert gated["readiness"] == "QUEUE_ONLY"
    assert gated["candidate_status"] == "advisory_only"
    assert gated["reason"] == gated["expectancy_gate_reason"] == "expectancy_insufficient_data"


def test_watch_setup_becomes_queue_only_advisory() -> None:
    gated = expectancy_gate.apply_expectancy_gate(_row(), expectancy_lookup={"breakout__LIVE__HIGH__HIGH__WIDE__T08_11_UTC__WEEKLY__BUY__NIFTY__CE": "WATCH"})
    assert gated["expectancy_status"] == "WATCH"
    assert gated["permission"] == "QUEUE_ONLY"
    assert gated["final_action"] == "QUEUE_ONLY"
    assert gated["execution_status"] == "queue_only"
    assert gated["candidate_status"] == "advisory_only"
    assert gated["reportable_executable"] is False
    assert gated["execution_allowed"] is False


def test_keep_setup_passes_through_unchanged_if_otherwise_eligible() -> None:
    row = _row()
    gated = expectancy_gate.apply_expectancy_gate(
        row,
        expectancy_lookup={"breakout__LIVE__HIGH__HIGH__WIDE__T08_11_UTC__WEEKLY__BUY__NIFTY__CE": "KEEP"},
    )
    assert gated["expectancy_status"] == "KEEP"
    assert gated["permission"] == row["permission"]
    assert gated["final_action"] == row["final_action"]
    assert gated["readiness"] == row["readiness"]
    assert gated["execution_status"] == row["execution_status"]
    assert gated["reportable_executable"] is True
    assert gated["execution_allowed"] is True


def test_fallback_still_blocked_even_if_keep() -> None:
    row = _row(
        fallback_used=True,
        permission="BLOCK",
        final_action="BLOCK",
        readiness="BLOCKED",
        execution_status="blocked",
        candidate_status="blocked",
        reportable_executable=False,
        execution_allowed=False,
        eligible_for_execution=False,
        selected_for_execution=False,
        tradable=False,
        is_executable=False,
        final_emit_block_reason="fallback_not_executable",
    )
    gated = expectancy_gate.apply_expectancy_gate(
        row,
        expectancy_lookup={"breakout__LIVE__HIGH__HIGH__WIDE__T08_11_UTC__WEEKLY__BUY__NIFTY__CE": "KEEP"},
    )
    assert gated["expectancy_status"] == "KEEP"
    assert gated["permission"] == "BLOCK"
    assert gated["final_action"] == "BLOCK"
    assert gated["readiness"] == "BLOCKED"
    assert gated["execution_status"] == "blocked"
    assert gated["reportable_executable"] is False
    assert gated["final_emit_block_reason"] == "fallback_not_executable"


def test_stale_feed_still_blocked_even_if_keep() -> None:
    row = _row(
        permission="BLOCK",
        final_action="BLOCK",
        readiness="BLOCKED",
        execution_status="blocked",
        candidate_status="blocked",
        reportable_executable=False,
        execution_allowed=False,
        eligible_for_execution=False,
        selected_for_execution=False,
        tradable=False,
        is_executable=False,
        feed_truth_state="STALE",
        final_emit_block_reason="STALE_OPTION_LTP",
    )
    gated = expectancy_gate.apply_expectancy_gate(
        row,
        expectancy_lookup={"breakout__LIVE__HIGH__HIGH__WIDE__T08_11_UTC__WEEKLY__BUY__NIFTY__CE": "KEEP"},
    )
    assert gated["expectancy_status"] == "KEEP"
    assert gated["permission"] == "BLOCK"
    assert gated["final_action"] == "BLOCK"
    assert gated["readiness"] == "BLOCKED"
    assert gated["execution_status"] == "blocked"
    assert gated["reportable_executable"] is False
    assert gated["final_emit_block_reason"] == "STALE_OPTION_LTP"


def test_missing_expectancy_lookup_defaults_to_insufficient_data_or_safe_advisory() -> None:
    gated = expectancy_gate.apply_expectancy_gate(_row())
    assert gated["expectancy_status"] == "INSUFFICIENT_DATA"
    assert gated["permission"] == "QUEUE_ONLY"
    assert gated["final_action"] == "QUEUE_ONLY"
    assert gated["execution_status"] == "queue_only"


def test_manual_override_logs_and_does_not_bypass_hard_safety(caplog) -> None:
    row = _row(
        fallback_used=True,
        permission="BLOCK",
        final_action="BLOCK",
        readiness="BLOCKED",
        execution_status="blocked",
        candidate_status="blocked",
        reportable_executable=False,
        execution_allowed=False,
        eligible_for_execution=False,
        selected_for_execution=False,
        tradable=False,
        is_executable=False,
        expectancy_override="KEEP",
    )
    with caplog.at_level("WARNING"):
        gated = expectancy_gate.apply_expectancy_gate(row)
    assert "expectancy_gate_manual_override" in caplog.text
    assert gated["expectancy_status"] == "KEEP"
    assert gated["permission"] == "BLOCK"
    assert gated["execution_status"] == "blocked"
    assert gated["reportable_executable"] is False


def test_expectancy_gate_module_avoids_broker_and_order_imports() -> None:
    source = Path(expectancy_gate.__file__).read_text(encoding="utf-8")
    forbidden = ("broker", "order_router", "live_trade", "kite", "upstox")
    assert not any(f"from core.{name}" in source or f"import {name}" in source for name in forbidden)
