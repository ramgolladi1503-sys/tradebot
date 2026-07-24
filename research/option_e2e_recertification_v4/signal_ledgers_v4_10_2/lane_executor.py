from __future__ import annotations


def execute_vwap_contract(*_args, **_kwargs) -> dict[str, object]:
    return {
        "status": "SIGNAL_EXECUTION_BLOCKED",
        "reason_code": "INSUFFICIENT_HISTORICAL_DATA_FOR_BACKTEST_OR_WFA",
        "signals": [],
        "accepted_sessions": 0,
        "rejected_sessions": 0,
    }

