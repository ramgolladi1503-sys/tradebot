from __future__ import annotations


NEGATIVE_CONTROL_IDS = (
    "direction_inversion",
    "matched_random_timestamps",
    "matched_random_dates",
    "session_level_permutation",
    "peer_symbol_substitution",
    "one_bar_timestamp_shift",
    "two_bar_timestamp_shift",
    "false_previous_day_boundaries",
    "removed_leader_condition",
    "removed_primary_structural_condition",
    "best_month_removal",
    "best_five_session_removal",
    "leave_one_year_out",
    "post_outcome_mutation_invariance",
)


def empty_negative_control_report() -> dict[str, object]:
    return {
        "status": "INSUFFICIENT_DATA",
        "controls": {control_id: "NOT_RUN_INSUFFICIENT_DATA" for control_id in NEGATIVE_CONTROL_IDS},
    }

