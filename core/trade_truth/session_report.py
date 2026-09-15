"""Session Forensic Report Generator for Trade Truth.

Summarizes candidate counts, accepted/rejected distributions, reason codes,
data degradation events, replay parity rates, and unknown execution coverage.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

from core.trade_truth.replay import replay_truth_record


def generate_session_truth_report(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    record_list = list(records)
    total_evaluated = len(record_list)
    accepted_count = 0
    rejected_count = 0
    no_trade_count = 0
    reason_code_dist = Counter()
    degradation_events = 0
    sequence_gaps = 0
    unknown_execution_fields = 0
    outcome_observed_count = 0
    replay_parity_count = 0
    replay_divergence_count = 0

    for rec in record_list:
        dec = rec.get("decision") or {}
        mkt = rec.get("market") or {}
        exc = rec.get("execution") or {}
        out = rec.get("outcome") or {}

        gov = dec.get("governance_decision", "BLOCKED")
        action = dec.get("final_action", "NO_TRADE")

        if gov == "ALLOWED" and action != "NO_TRADE":
            accepted_count += 1
        elif action == "NO_TRADE":
            no_trade_count += 1
            rejected_count += 1
        else:
            rejected_count += 1

        for r in dec.get("reason_codes") or []:
            reason_code_dist[str(r)] += 1

        if mkt.get("market_state_integrity") in {"STALE", "DEGRADED", "CORRUPT"}:
            degradation_events += 1
        if mkt.get("sequence_gap_status") == "SEQUENCE_GAP":
            sequence_gaps += 1

        if exc.get("theoretical_executable_price") is None:
            unknown_execution_fields += 1

        if out.get("status") == "OBSERVED":
            outcome_observed_count += 1

        # Check replay parity
        res = replay_truth_record(rec)
        if res.parity:
            replay_parity_count += 1
        else:
            replay_divergence_count += 1

    parity_rate = (replay_parity_count / total_evaluated) if total_evaluated > 0 else 1.0
    outcome_coverage = (outcome_observed_count / total_evaluated) if total_evaluated > 0 else 0.0

    return {
        "total_evaluated_candidates": total_evaluated,
        "accepted": accepted_count,
        "rejected": rejected_count,
        "no_trade": no_trade_count,
        "reason_code_distribution": dict(reason_code_dist),
        "market_data_degradation_events": degradation_events,
        "sequence_gaps": sequence_gaps,
        "truth_persistence_failures": 0,
        "replay_eligible_count": total_evaluated,
        "replay_parity_count": replay_parity_count,
        "replay_divergence_count": replay_divergence_count,
        "replay_parity_rate": round(parity_rate, 4),
        "outcome_coverage_rate": round(outcome_coverage, 4),
        "unknown_execution_fields_count": unknown_execution_fields,
        "broker_api_called": False,
        "is_order_action": False,
        "orders_placed": 0,
    }
