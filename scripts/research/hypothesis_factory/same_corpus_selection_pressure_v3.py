#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Any

def calculate_selection_pressure(
    candidates_generated: int,
    candidates_evaluated: int,
    family_groups_count: int,
    survivors_count: int
) -> dict[str, Any]:
    effective_trials = candidates_evaluated * 1.5
    selection_bias_risk = "HIGH" if candidates_evaluated > 200 else "MODERATE" if candidates_evaluated > 50 else "LOW"

    if candidates_evaluated > 1000:
        locked_gate_allowed = False
        restriction_reason = "BLOCKED_INSUFFICIENT_HOLDOUT_AFTER_SEARCH_PRESSURE"
    elif candidates_evaluated > 200:
        locked_gate_allowed = True
        restriction_reason = "REQUIRES_STRICT_PRE_OUTCOME_NARROWING_MAX_5_SURVIVORS"
    else:
        locked_gate_allowed = True
        restriction_reason = "STANDARD_LOCKED_GATE_PERMITTED"

    return {
        "candidate_specs_generated": candidates_generated,
        "candidate_specs_evaluated": candidates_evaluated,
        "family_groups_generated": family_groups_count,
        "development_tests_run": candidates_evaluated,
        "effective_trials_estimate": effective_trials,
        "selection_method": "PRE_OUTCOME_GRAMMAR_DISCOVERY_V3",
        "survivor_count": survivors_count,
        "selection_bias_risk": selection_bias_risk,
        "locked_gate_allowed": locked_gate_allowed,
        "restriction_reason": restriction_reason
    }
