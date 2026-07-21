from __future__ import annotations

from typing import Any

import pandas as pd

from research.prospective_structural_edge_v2.cycle4_underlying_runner import ac18_generate


PARAMETERS = {
    "morning_range_end_index": 75,
    "late_session_start_index": 286,
    "acceptance_fraction": 0.28,
    "required_confirming_indices": 2,
    "required_confirmation_bars": 1,
}


def validate_parameters(params: dict[str, Any] | None = None) -> None:
    params = PARAMETERS if params is None else params
    if set(params) != set(PARAMETERS):
        raise ValueError("AC18 parameter contract mismatch")
    if params["late_session_start_index"] <= params["morning_range_end_index"]:
        raise ValueError("late session must start after morning range completion")
    if params["required_confirming_indices"] < 2:
        raise ValueError("multi-index confirmation requires at least two indices")
    if params["required_confirmation_bars"] != 1:
        raise ValueError("required_confirmation_bars is frozen separately from confirming-index count")
    if not 0 < params["acceptance_fraction"] < 1:
        raise ValueError("acceptance_fraction must be a positive fraction")


def evaluate_state(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None = None) -> dict[str, Any]:
    validate_parameters()
    candidates, rejections = ac18_generate(session, data, prior)
    return {"candidate_count": len(candidates), "rejections": rejections, "single_emission": len(candidates) <= 1}


def generate_candidates(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None = None):
    validate_parameters()
    return ac18_generate(session, data, prior)[0]


def generate_rejections(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None = None) -> list[str]:
    validate_parameters()
    return ac18_generate(session, data, prior)[1]


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
