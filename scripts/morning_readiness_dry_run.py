#!/usr/bin/env python3
"""Run deterministic, offline Morning Readiness V1 scenarios."""
from __future__ import annotations

import json

from core.morning_readiness_v1 import MorningReadiness, MorningState


def normal_path() -> MorningReadiness:
    current = MorningReadiness()
    for state in list(MorningState)[1:11]:
        current = current.transition(state)
    return current


def run() -> dict[str, object]:
    armed = normal_path()
    live = armed.transition(MorningState.WAITING_FOR_MARKET).transition(MorningState.LIVE_FEED_PENDING).transition(MorningState.LIVE_RUNNING)
    degraded = live.degraded_for("NO_LIVE_OPTION_FEED")
    fatal = live.degraded_for("WRONG_STORAGE_AUTHORITY")
    return {"normal_preopen_state": armed.state.value, "degraded_state": degraded.state.value, "fatal_state": fatal.state.value, "read_only": True, "orders_placed": 0}


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
