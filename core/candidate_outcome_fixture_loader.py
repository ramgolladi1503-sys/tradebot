from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from core.candidate_outcome_truth import (
    CandidateOutcomeInput,
    CandidateOutcomeTruth,
    PriceObservation,
    build_candidate_outcome_truth,
)


CANDIDATE_OUTCOME_FIXTURE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CandidateOutcomeFixture:
    fixture_id: str
    description: str | None
    candidate: CandidateOutcomeInput
    observations: tuple[PriceObservation, ...]
    expected_outcome_status: str | None
    expected_gross_r: float | None
    expected_cost_adjusted_r: float | None
    metadata: dict[str, object]


def _as_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("fixture field must be an object")
    return dict(value)


def _coerce_float(value: Any, *, field_name: str) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"fixture field '{field_name}' must be a number or null") from exc


def _coerce_candidate(payload: Mapping[str, Any]) -> CandidateOutcomeInput:
    return CandidateOutcomeInput(
        candidate_id=payload.get("candidate_id"),
        trade_id=payload.get("trade_id"),
        strategy_family=str(payload.get("strategy_family") or ""),
        symbol=str(payload.get("symbol") or ""),
        index=payload.get("index"),
        regime=payload.get("regime"),
        expiry_type=payload.get("expiry_type"),
        signal_epoch=payload.get("signal_epoch"),
        entry_price=payload.get("entry_price"),
        stop_loss_price=payload.get("stop_loss_price"),
        target_price=payload.get("target_price"),
        timeout_epoch=payload.get("timeout_epoch"),
        side=payload.get("side"),
        direction=payload.get("direction"),
        feed_truth_state=payload.get("feed_truth_state"),
        reportable_executable=bool(payload.get("reportable_executable", False)),
        execution_allowed=bool(payload.get("execution_allowed", False)),
        estimated_cost_r=payload.get("estimated_cost_r"),
        estimated_cost_abs=payload.get("estimated_cost_abs"),
    )


def _coerce_observation(payload: Any) -> PriceObservation:
    if not isinstance(payload, Mapping):
        raise ValueError("observation entries must be objects")
    observed_epoch = payload.get("observed_epoch")
    ltp = payload.get("ltp")
    if observed_epoch is None or ltp is None:
        raise ValueError("observation entries must include 'observed_epoch' and 'ltp'")
    return PriceObservation(
        observed_epoch=float(observed_epoch),
        ltp=float(ltp),
        bid=_coerce_float(payload.get("bid"), field_name="bid"),
        ask=_coerce_float(payload.get("ask"), field_name="ask"),
        spread=_coerce_float(payload.get("spread"), field_name="spread"),
        source=str(payload.get("source") or "").strip() or None,
        quote_age_sec=_coerce_float(payload.get("quote_age_sec"), field_name="quote_age_sec"),
    )


def _coerce_metadata(payload: Any) -> dict[str, object]:
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise ValueError("fixture field 'metadata' must be an object when present")
    return dict(payload)


def load_candidate_outcome_fixture(path: str | Path) -> CandidateOutcomeFixture:
    fixture_path = Path(path)
    if not fixture_path.exists():
        raise ValueError(f"fixture file does not exist: {fixture_path}")
    try:
        payload = json.loads(fixture_path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"fixture file is not valid JSON: {fixture_path}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("fixture root must be an object")
    schema_version = payload.get("schema_version")
    if schema_version != CANDIDATE_OUTCOME_FIXTURE_SCHEMA_VERSION:
        raise ValueError("unsupported candidate outcome fixture schema_version")
    fixture_id = payload.get("fixture_id")
    if not isinstance(fixture_id, str) or not fixture_id.strip():
        raise ValueError("fixture_id is required")
    candidate_payload = payload.get("candidate")
    if not isinstance(candidate_payload, Mapping):
        raise ValueError("fixture field 'candidate' must be an object")
    observations_payload = payload.get("observations")
    if not isinstance(observations_payload, list):
        raise ValueError("fixture field 'observations' must be a list")

    expected_payload = payload.get("expected") or {}
    if expected_payload and not isinstance(expected_payload, Mapping):
        raise ValueError("fixture field 'expected' must be an object when present")

    expected_outcome_status = expected_payload.get("outcome_status")
    if expected_outcome_status is not None and not isinstance(expected_outcome_status, str):
        raise ValueError("expected.outcome_status must be a string or null")

    expected_gross_r = _coerce_float(expected_payload.get("gross_r"), field_name="expected.gross_r")
    expected_cost_adjusted_r = _coerce_float(
        expected_payload.get("cost_adjusted_r"),
        field_name="expected.cost_adjusted_r",
    )

    description = payload.get("description")
    if description is not None and not isinstance(description, str):
        raise ValueError("description must be a string or null")

    observations = tuple(_coerce_observation(item) for item in observations_payload)
    return CandidateOutcomeFixture(
        fixture_id=fixture_id,
        description=description,
        candidate=_coerce_candidate(candidate_payload),
        observations=observations,
        expected_outcome_status=expected_outcome_status,
        expected_gross_r=expected_gross_r,
        expected_cost_adjusted_r=expected_cost_adjusted_r,
        metadata=_coerce_metadata(payload.get("metadata")),
    )


def evaluate_candidate_outcome_fixture(path: str | Path) -> CandidateOutcomeTruth:
    fixture = load_candidate_outcome_fixture(path)
    return build_candidate_outcome_truth(fixture.candidate, fixture.observations)


def load_candidate_outcome_fixtures(directory: str | Path) -> tuple[CandidateOutcomeFixture, ...]:
    fixture_dir = Path(directory)
    if not fixture_dir.exists():
        raise ValueError(f"fixture directory does not exist: {fixture_dir}")
    if not fixture_dir.is_dir():
        raise ValueError(f"fixture directory is not a directory: {fixture_dir}")
    fixture_paths = sorted(path for path in fixture_dir.iterdir() if path.is_file() and path.suffix == ".json")
    if not fixture_paths:
        raise ValueError(f"fixture directory contains no .json fixtures: {fixture_dir}")
    return tuple(load_candidate_outcome_fixture(path) for path in fixture_paths)


__all__ = [
    "CANDIDATE_OUTCOME_FIXTURE_SCHEMA_VERSION",
    "CandidateOutcomeFixture",
    "evaluate_candidate_outcome_fixture",
    "load_candidate_outcome_fixture",
    "load_candidate_outcome_fixtures",
]
