from __future__ import annotations

from typing import Any

import pandas as pd

from research.prospective_structural_edge_v2.cycle4_underlying_runner import ac16_generate, make_candidate


PARAMETERS = {
    "acceptance_fraction": 0.26,
    "morning_window_end_index": 60,
    "late_start_index": 61,
    "minimum_vwap_migration": 0.12,
    "confirmation_count": 2,
}


def validate_parameters(params: dict[str, Any] | None = None) -> None:
    params = PARAMETERS if params is None else params
    required = set(PARAMETERS)
    if set(params) != required:
        raise ValueError("AC16 parameter contract mismatch")
    if not 0 < params["acceptance_fraction"] < 1:
        raise ValueError("acceptance_fraction must be a positive fraction")
    if params["late_start_index"] <= params["morning_window_end_index"]:
        raise ValueError("late_start_index must follow the morning window")
    if params["confirmation_count"] < 1:
        raise ValueError("confirmation_count must be positive")


def evaluate_state(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None) -> dict[str, Any]:
    validate_parameters()
    candidates, rejections = ac16_generate(session, data, prior)
    return {"candidate_count": len(candidates), "rejections": rejections, "single_emission": len(candidates) <= 3}


def generate_candidates(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None):
    validate_parameters()
    return ac16_generate(session, data, prior)[0]


def generate_rejections(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None) -> list[str]:
    validate_parameters()
    return ac16_generate(session, data, prior)[1]


def project_candidate_identity(candidate) -> dict[str, Any]:
    return {
        "hypothesis_id": candidate.hypothesis_id,
        "target_symbol": candidate.symbol,
        "session_date": candidate.session,
        "direction": candidate.direction,
        "entry_index": candidate.entry_index,
        "entry_ts": candidate.entry_ts,
        "history_hash": candidate.evidence.get("history_hash"),
    }


__all__ = [
    "PARAMETERS",
    "validate_parameters",
    "evaluate_state",
    "generate_candidates",
    "generate_rejections",
    "project_candidate_identity",
]
