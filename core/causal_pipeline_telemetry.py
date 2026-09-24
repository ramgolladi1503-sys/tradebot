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
    # Verify conservation against actual immutable events; do not self-assert
    # merely because counters were computed by this function.
    identities = [(o.pulse_id, o.symbol, o.strategy_id) for o in obs]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate_strategy_observation_identity")
    seen_qualified = {
        (o.pulse_id, o.symbol, o.strategy_id) for o in obs
        if o.qualification_state == "QUALIFIED" and o.applicability_state == "APPLICABLE"
    }
    candidate_ids = [c.candidate_id for c in cand]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("duplicate_candidate_identity")
    for c in cand:
        if not c.strategy_qualified or (c.pulse_id, c.symbol, c.strategy_id) not in seen_qualified:
            raise ValueError("candidate_without_matching_qualified_observation")
    return counters
