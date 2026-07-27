from __future__ import annotations


def execute_vwap_contract(*_args, **_kwargs) -> dict[str, object]:
    """Execution remains disabled until a reviewed semantic contract is supplied."""

    return {
        "status": "VWAP_EXECUTION_DISABLED_NO_REVIEWED_CONTRACT",
        "reason_codes": ["SEMANTIC_EXECUTION_CONTRACT_REQUIRED"],
        "signals": [],
        "attempted_sessions": 0,
        "accepted_sessions": 0,
        "rejected_sessions": 0,
        "execution_allowed": False,
        "broker_api_called": False,
        "is_order_action": False,
        "allowed_for_live_execution": False,
        "read_only": True,
    }
