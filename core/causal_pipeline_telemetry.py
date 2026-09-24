"""Pure telemetry projection; never mutate strategy qualification to improve counters."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable


def build_causal_telemetry(
    *, symbols_seen: int, symbols_evaluated: int,
    observations: Iterable[Any], candidates: Iterable[Any],
) -> dict[str, Any]:
    obs = list(observations)
    cand = list(candidates)
    status = Counter(
        o.qualification_state for o in obs if o.applicability_state == "APPLICABLE"
    )
    strategy_states: dict[str, Counter] = defaultdict(Counter)
    for o in obs:
        strategy_states[o.strategy_id][
            o.applicability_state + ":" + o.qualification_state
        ] += 1
    counters: dict[str, Any] = {
        "symbols_seen": symbols_seen,
        "symbols_evaluated": symbols_evaluated,
        "strategy_observations": len(obs),
        "qualified_candidates": len(cand),
        "execution_eligible_candidates": sum(bool(c.execution_eligible) for c in cand),
        "advisory_ready_candidates": sum(bool(c.advisory_ready) for c in cand),
        "qualification_unknown": status["UNKNOWN"],
        "no_signal": status["NO_SIGNAL"],
        "blocked_prerequisites": sum(
            o.applicability_state == "APPLICABLE" and
            o.reason_code.startswith("CAS_") and
            ("MISSING" in o.reason_code or "INVALID" in o.reason_code)
            for o in obs
        ),
        "strategy_state_counts": {
            name: dict(stages) for name, stages in sorted(strategy_states.items())
        },
        # No option-market execution gates were called by this CAS-only path.
        # Do not turn unassessed checks into zeros.
        "execution_gates": "NOT_EVALUATED_SHADOW_ONLY",
        "near_signal_calibration": "NOT_AVAILABLE",
    }
    if counters["execution_eligible_candidates"] != 0 and not any(
        c.execution_eligible for c in cand
    ):
        raise AssertionError("executable_candidate_counter_corrupt")
    return counters
