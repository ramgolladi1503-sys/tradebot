from __future__ import annotations


def execute_lane(*_args, **_kwargs) -> dict[str, object]:
    return {"status": "HOLDOUT_ACCESS_PROHIBITED", "signals": [], "rejected_sessions": [], "accepted_sessions": []}
