"""Causal short-horizon CAS advisory evaluator."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

STRATEGY_ID = "CAS_MORNING_REVERSAL_SHORT_HORIZON_V1"

def evaluate(*, session_id: str, symbol: str, morning_return: float, observation_timestamp: datetime, cutoff_timestamp: datetime, received_timestamp: datetime | None = None, source_sha: str = "", signal_input_09_15: float | None = None, signal_input_10_00: float | None = None, prospective_session_count_before: int = 0, prospective_target_session_count: int = 20) -> dict[str, Any]:
    if observation_timestamp.tzinfo is None or cutoff_timestamp.tzinfo is None:
        raise ValueError("timezone_required")
    if observation_timestamp < cutoff_timestamp:
        raise ValueError("pre_cutoff_observation")
    if received_timestamp is not None:
        if received_timestamp.tzinfo is None:
            raise ValueError("timezone_required")
        if (received_timestamp - cutoff_timestamp).total_seconds() > 2:
            raise ValueError("observation_late")
    direction = "DOWN" if morning_return > 0 else "UP" if morning_return < 0 else "NO_SIGNAL"
    timestamp = observation_timestamp.isoformat()
    side = "CE" if direction == "UP" else "PE" if direction == "DOWN" else None
    return {"session_id": session_id, "strategy_id": STRATEGY_ID, "candidate_id": f"{session_id}:{symbol}", "spec_sha": STRATEGY_ID, "source_sha": source_sha, "research_state": "HYPOTHESIS", "timestamp": timestamp, "decision_timestamp": timestamp, "entry_reference_timestamp": timestamp, "advisory_emission_timestamp": datetime.now(timezone.utc).isoformat(), "symbol": symbol, "direction": direction, "option_side": side, "signal_input_09_15": signal_input_09_15, "signal_input_10_00": signal_input_10_00, "morning_return": morning_return, "entry_lag_ms": max(0, int((observation_timestamp - cutoff_timestamp).total_seconds() * 1000)), "entry_freshness_tolerance_ms": 2000, "primary_exit_timestamp": "15:20:00 Asia/Kolkata", "secondary_exit_timestamp": "15:25:00 Asia/Kolkata", "execution_status": "advisory_only", "read_only": True, "broker_write_authority": False, "order_authority": False, "paper_authorized": False, "live_execution_authorized": False, "broker_order_calls": 0, "orders_placed": 0, "orders_modified": 0, "orders_cancelled": 0, "prospective_session_count_before": prospective_session_count_before, "prospective_target_session_count": prospective_target_session_count, "display_label": "CAS Morning Reversal | ADVISORY ONLY | NOT A LIVE ORDER | PROSPECTIVE EDGE NOT YET SUPPORTED"}
