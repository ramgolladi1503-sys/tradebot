from __future__ import annotations

from typing import Any

import pandas as pd

from research.prospective_structural_edge_v2.cycle4_underlying_runner import ac17_generate, corr


PARAMETERS = {
    "return_interval": 1,
    "correlation_lookback": 45,
    "breakdown_correlation_threshold": 0.18,
    "minimum_leader_displacement_bps": 22,
    "realignment_threshold_bps": 8,
    "realignment_confirmation_bars": 2,
}


def validate_parameters(params: dict[str, Any] | None = None) -> None:
    params = PARAMETERS if params is None else params
    if set(params) != set(PARAMETERS):
        raise ValueError("AC17 parameter contract mismatch")
    if params["return_interval"] != 1:
        raise ValueError("return_interval is frozen at one minute")
    if params["correlation_lookback"] < 3:
        raise ValueError("correlation_lookback too small")
    if not -1 <= params["breakdown_correlation_threshold"] <= 1:
        raise ValueError("correlation threshold outside Pearson bounds")
    if params["realignment_confirmation_bars"] < 1:
        raise ValueError("confirmation bars must be positive")


def estimate_correlation(xs: list[float], ys: list[float]) -> float | None:
    validate_parameters()
    return corr(xs, ys)


def evaluate_state(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None = None) -> dict[str, Any]:
    validate_parameters()
    candidates, rejections = ac17_generate(session, data, prior)
    return {"candidate_count": len(candidates), "rejections": rejections, "single_emission": len(candidates) <= 1}


def generate_candidates(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None = None):
    validate_parameters()
    return ac17_generate(session, data, prior)[0]


def generate_rejections(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None = None) -> list[str]:
    validate_parameters()
    return ac17_generate(session, data, prior)[1]


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
    "estimate_correlation",
    "evaluate_state",
    "generate_candidates",
    "generate_rejections",
    "project_candidate_identity",
]
