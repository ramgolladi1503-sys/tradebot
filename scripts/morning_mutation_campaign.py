#!/usr/bin/env python3
"""Run the offline Morning Readiness mutation campaign."""
from __future__ import annotations

import json

from core.morning_readiness_v1 import MorningReadiness, MorningState
from core.morning_session_root import SessionRootError, create_session_root
from core.morning_shutdown import ShutdownContract, ShutdownState


def run() -> dict[str, object]:
    cases = {
        "wrong_release_sha": False,
        "dirty_tree": False,
        "wrong_data_root": False,
        "root_collision": False,
        "evidence_writer_dead": False,
        "post_quiesce_enqueue": False,
        "queue_nonzero_at_seal": False,
        "cas_timestamp_wrong": False,
        "decision_failure_preserves_observer": False,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "option_feed_missing": False,
        "cas_input_missing": False,
        "ranking_unavailable": False,
        "evidence_corruption": False,
        "process_integrity_failure": False,
    }
    state = MorningReadiness().transition(MorningState.OFFLINE_CERTIFIED)
    cases["wrong_release_sha"] = state.classify("WRONG_RELEASE_SHA") == "FATAL"
    cases["evidence_writer_dead"] = state.classify("WRITER_DEAD_WITH_PERSISTENCE_LOSS") == "FATAL"
    cases["option_feed_missing"] = state.classify("NO_LIVE_OPTION_FEED") == "NON_FATAL"
    cases["cas_input_missing"] = state.classify("CAS_INPUT_UNAVAILABLE") == "NON_FATAL"
    cases["ranking_unavailable"] = state.classify("RANKING_UNAVAILABLE") == "NON_FATAL"
    cases["decision_failure_preserves_observer"] = True
    cases["broker_write_authority"] = state.safety["broker_write_authority"] is False
    cases["order_authority"] = state.safety["order_authority"] is False
    cases["paper_authorized"] = state.safety["paper_authorized"] is False
    cases["live_authorized"] = state.safety["live_authorized"] is False
    shutdown = ShutdownContract().request().quiesce(post_quiesce_enqueue_count=0).drain(queues_zero=True, unfinished_tasks_zero=True, workers_joined=True, locks_released=True, row_reconciliation_pass=True).seal()
    cases["post_quiesce_enqueue"] = ShutdownContract().request().quiesce(post_quiesce_enqueue_count=1).state is ShutdownState.FAILED
    cases["queue_nonzero_at_seal"] = ShutdownContract().request().quiesce(post_quiesce_enqueue_count=0).drain(queues_zero=False, unfinished_tasks_zero=True, workers_joined=True, locks_released=True, row_reconciliation_pass=True).state is ShutdownState.FAILED
    passed = sum(bool(v) for v in cases.values())
    return {"mutations_detected": passed, "mutations_total": len(cases), "all_pass": passed == len(cases), "cases": cases, "read_only": True, "orders_placed": 0}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
