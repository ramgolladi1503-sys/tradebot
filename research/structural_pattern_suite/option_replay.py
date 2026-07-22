from __future__ import annotations


WRAPPER_SET = ("ATM", "ONE_STEP_ITM")


def unavailable_option_replay_report(reason: str) -> dict[str, object]:
    return {
        "UNDERLYING_EDGE": "NOT_EVALUATED",
        "OPTION_EXECUTABILITY": "INSUFFICIENT_DATA",
        "OPTION_NET_EDGE": "INSUFFICIENT_DATA",
        "wrapper_set": list(WRAPPER_SET),
        "real_historical_option_data_required": True,
        "mock_option_data_allowed": False,
        "reason": reason,
    }

