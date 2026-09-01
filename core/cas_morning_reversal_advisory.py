"""Causal short-horizon CAS advisory evaluator."""
from __future__ import annotations
from datetime import datetime
from typing import Any

STRATEGY_ID = "CAS_MORNING_REVERSAL_SHORT_HORIZON_V1"

def evaluate(*, session_id: str, symbol: str, morning_return: float, observation_timestamp: datetime, cutoff_timestamp: datetime, received_timestamp: datetime | None = None) -> dict[str, Any]:
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
    return {"session_id": session_id, "strategy_id": STRATEGY_ID, "candidate_id": f"{session_id}:{symbol}", "spec_sha": STRATEGY_ID, "timestamp": timestamp, "decision_timestamp": timestamp, "symbol": symbol, "direction": direction, "reference_window": "09:15-10:00", "cutoff": cutoff_timestamp.isoformat(), "execution_status": "advisory_only", "read_only": True, "broker_write_authority": False, "order_authority": False, "paper_authorized": False, "live_execution_authorized": False, "orders_placed": 0, "orders_modified": 0, "orders_cancelled": 0}
