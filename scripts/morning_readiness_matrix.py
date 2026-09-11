#!/usr/bin/env python3
"""Deterministic Morning Readiness V1 fault matrix.

The matrix is offline and does not access Kite or start a runtime.
"""
from __future__ import annotations

import json

from core.morning_readiness_v1 import MorningReadiness, MorningState


SCENARIOS = {
    "normal_startup": None,
    "auth_failure": "AUTH_FAILURE",
    "dirty_sha": "DIRTY_WORKTREE",
    "storage_failure": "WRONG_STORAGE_AUTHORITY",
    "evidence_collision": "EVIDENCE_ROOT_COLLISION",
    "option_universe_empty": "NO_LIVE_OPTION_FEED",
    "option_mirror_unavailable": "OPTION_MIRROR_STALE",
    "persistence_writer_dead": "WRITER_DEAD_WITH_PERSISTENCE_LOSS",
    "cas_input_missing": "CAS_INPUT_UNAVAILABLE",
    "ranking_unavailable": "RANKING_UNAVAILABLE",
}


def armed() -> MorningReadiness:
    current = MorningReadiness()
    for state in (
        MorningState.OFFLINE_CERTIFIED, MorningState.MORNING_PRECHECK,
        MorningState.AUTH_READY, MorningState.STORAGE_READY,
        MorningState.UNIVERSE_READY, MorningState.SUBSCRIPTION_PLAN_READY,
        MorningState.PERSISTENCE_READY, MorningState.EVIDENCE_WRITER_READY,
        MorningState.OPTION_MIRROR_OFFLINE_READY, MorningState.PREOPEN_ARMED,
        MorningState.WAITING_FOR_MARKET, MorningState.LIVE_FEED_PENDING,
        MorningState.LIVE_RUNNING,
    ):
        current = current.transition(state)
    return current


def run() -> dict[str, object]:
    live = armed()
    results: dict[str, object] = {}
    for name, invariant in SCENARIOS.items():
        if invariant is None:
            results[name] = {"state": live.state.value, "pass": live.state is MorningState.LIVE_RUNNING}
            continue
        if invariant in {"NO_LIVE_OPTION_FEED", "OPTION_MIRROR_STALE", "CAS_INPUT_UNAVAILABLE", "RANKING_UNAVAILABLE"}:
            result = live.degraded_for(invariant)
            results[name] = {"state": result.state.value, "pass": result.state is MorningState.LIVE_DEGRADED}
        else:
            result = live.degraded_for(invariant)
            results[name] = {"state": result.state.value, "pass": result.state is MorningState.FAIL_CLOSED}
    return {"matrix": results, "all_pass": all(item["pass"] for item in results.values()), "read_only": True, "orders_placed": 0}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
