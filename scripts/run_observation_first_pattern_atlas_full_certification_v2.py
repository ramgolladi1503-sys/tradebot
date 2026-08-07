#!/usr/bin/env python3
"""Run Pattern Atlas Stages 5-14 with strictly causal first-signal execution.

This wrapper supersedes full_certification_v1 trigger evaluation. It requires
Stage-4 V3 causal-prefix authority and changes the downstream signal path so:

1. trigger features use prefix rows only;
2. prefix scaler/prototype/threshold are frozen on observation prefixes before
   trading outcomes are opened;
3. each session is scanned on a predeclared chronological schedule;
4. the first qualifying prefix is used -- never the closest/best later prefix;
5. only a known session-close clock is used to decide whether the fixed future
   horizon can fit;
6. unopened sessions remain sealed unless a strategy survives all earlier gates.

No broker, paper, live, risk-engine, ranking, or order behavior is mutated.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from datetime import date
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

TARGET_REGIME = "PRE_CAS"
SCHEMA_VERSION = 2
STAGE = "pre_cas_full_edge_certification_live_causal_v2"


def load_sibling(name: str, filename: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load sibling module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


V1 = load_sibling(
    "pattern_atlas_full_certification_v1_for_v2",
    "run_observation_first_pattern_atlas_full_certification_v1.py",
)
A3 = load_sibling(
    "pattern_atlas_analogues_v3_for_full_certification_v2",
    "run_observation_first_pattern_atlas_analogues_v3.py",
)
MOTIF = V1.MOTIF
BASE = V1.BASE

ORIGINAL_FREEZE_HYPOTHESES = V1.freeze_hypotheses


def validate_inputs_v2(
    motif_catalog: dict[str, Any],
    analogue_catalog: dict[str, Any],
    instrument: str,
) -> dict[str, Any]:
    lane = A3.V2.validate_recertified_catalog(
        motif_catalog, instrument, TARGET_REGIME
    )
    if (
        motif_catalog.get("principal_verdict")
        != "OUTCOME_BLIND_TRAJECTORY_ACCEPTED_MOTIFS_RECERTIFIED"
    ):
        raise ValueError("Recertified motif catalog lacks required authority")
    if analogue_catalog.get("schema_version") != 3:
        raise ValueError("Full certification V2 requires Stage-4 schema_version=3")
    if (
        analogue_catalog.get("stage")
        != "pre_cas_causal_prefix_matched_geometric_analogues_v3"
    ):
        raise ValueError("Full certification V2 requires Stage-4 causal-prefix V3")
    if (
        analogue_catalog.get("principal_verdict")
        != "PRE_CAS_CAUSAL_PREFIX_MATCHED_GEOMETRIC_ANALOGUES_FROZEN"
    ):
        raise ValueError("Causal-prefix analogue catalog is not frozen")
    if analogue_catalog.get("source_motif_catalog_sha256") != motif_catalog.get(
        "semantic_sha256"
    ):
        raise ValueError("Stage-4 V3 does not reference the recertified motif catalog")
    policy = dict(analogue_catalog.get("policy") or {})
    required_true = (
        "pre_cas_only",
        "trajectory_quality_accepted_sessions_only",
        "causal_prefix_representation",
        "prefix_scaler_fit_on_observation_prefixes_only",
    )
    for key in required_true:
        if policy.get(key) is not True:
            raise ValueError(f"Stage-4 V3 missing required causal policy: {key}")
    if policy.get("suffix_values_used_in_prefix_trigger") is not False:
        raise ValueError("Stage-4 V3 does not prove suffix-free prefix triggers")
    if policy.get("unopened_sessions_scored") is not False:
        raise ValueError("Stage-4 V3 opened sealed sessions before certification")
    return lane


def analogue_by_motif_v3(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for window in catalog.get("windows", []):
        for motif in window.get("motifs", []):
            result[str(motif["motif_id"])] = motif
    return result


def freeze_hypotheses_v2(
    states: dict[int, Any],
    lane: dict[str, Any],
    analogue_catalog: dict[str, Any],
    transition_catalog: dict[str, Any],
    cache: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    catalog = ORIGINAL_FREEZE_HYPOTHESES(
        states, lane, analogue_catalog, transition_catalog, cache
    )
    analogue_lookup = analogue_by_motif_v3(analogue_catalog)
    for hypothesis in catalog.get("hypotheses", []):
        analogue = analogue_lookup.get(str(hypothesis["motif_id"]))
        if analogue is None:
            raise ValueError(
                f"Frozen hypothesis has no Stage-4 V3 analogue: {hypothesis['motif_id']}"
            )
        calibration = dict(analogue.get("causal_prefix_calibration") or {})
        if calibration.get("suffix_values_used") is not False:
            raise ValueError("Hypothesis received a non-causal prefix calibration")
        if calibration.get("scaler_fit_scope") != "observation_prefixes_only":
            raise ValueError("Prefix calibration was not fit on observation prefixes only")
        hypothesis["causal_prefix_calibration"] = calibration
        hypothesis["trigger_selection_policy"] = {
            "scan_order": "chronological_from_session_open",
            "start_stride_points": "max(1, full_window_points // 2)",
            "selection": "first_qualifying_prefix_only",
            "best_later_signal_selection": False,
            "session_close_gate_uses_known_clock_only": True,
        }
        hypothesis["outcomes_seen_when_frozen"] = False
        hypothesis["semantic_sha256"] = BASE.digest(hypothesis)
    policy = dict(catalog.get("policy") or {})
    policy.update(
        {
            "causal_prefix_calibration_frozen_before_outcomes": True,
            "suffix_values_used_in_trigger": False,
            "first_qualifying_signal_policy_frozen_before_outcomes": True,
            "best_later_signal_selection": False,
        }
    )
    catalog["policy"] = policy
    catalog["semantic_sha256"] = BASE.digest(catalog)
    return catalog


def _timestamp_utc(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")


def _session_close_utc(session_date: str, regime: str = TARGET_REGIME) -> pd.Timestamp:
    _, close_time = BASE.window(regime)
    local = pd.Timestamp(
        f"{session_date} {close_time.hour:02d}:{close_time.minute:02d}:00",
        tz=BASE.TZ,
    )
    return local.tz_convert("UTC")


def _contiguous_native(
    frame: pd.DataFrame, cadence_minutes: float
) -> bool:
    if len(frame) <= 1:
        return True
    gaps = (
        pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
        .diff()
        .dt.total_seconds()
        .div(60.0)
        .dropna()
        .to_numpy(float)
    )
    return bool(
        np.allclose(
            gaps,
            cadence_minutes,
            atol=max(0.25, cadence_minutes * 0.10),
        )
    )


def prefix_distance_from_calibration(
    prefix: pd.DataFrame,
    calibration: dict[str, Any],
) -> float:
    prefix_points = int(calibration["prefix_points"])
    raw = A3.causal_prefix_vector(prefix, prefix_points)
    median = np.asarray(calibration["scaler_median"], dtype=float)
    scale = np.asarray(calibration["scaler_scale"], dtype=float)
    prototype = np.asarray(calibration["motif_prefix_prototype"], dtype=float)
    if len(raw) != len(median) or len(raw) != len(scale) or len(raw) != len(prototype):
        raise ValueError("Causal prefix calibration dimensionality mismatch")
    transformed = MOTIF.apply_scaler(
        raw.reshape(1, -1), median, scale
    )[0]
    return float(A3.normalized_distances(transformed, prototype)[0])


def first_qualifying_prefix_index(
    session: pd.DataFrame,
    calibration: dict[str, Any],
    full_window_points: int,
    cadence_minutes: float,
    future_points: int,
    regime: str = TARGET_REGIME,
) -> tuple[int, float] | None:
    """Return the first causal qualifying start index; suffix data never ranks starts."""
    ordered = session.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    prefix_points = int(calibration["prefix_points"])
    threshold = float(calibration["distance_threshold"])
    stride_points = max(1, int(full_window_points) // 2)
    if prefix_points < 2 or future_points < 1:
        return None
    if len(ordered) < prefix_points:
        return None
    session_date = str(ordered["session_date"].iloc[0])
    close_utc = _session_close_utc(session_date, regime)

    for start in range(0, len(ordered) - prefix_points + 1, stride_points):
        prefix = ordered.iloc[start : start + prefix_points]
        if not _contiguous_native(prefix, cadence_minutes):
            continue
        signal_timestamp = _timestamp_utc(prefix["timestamp"].iloc[-1])
        required_exit_timestamp = signal_timestamp + pd.Timedelta(
            minutes=float(future_points) * cadence_minutes
        )
        if required_exit_timestamp > close_utc:
            continue
        distance = prefix_distance_from_calibration(prefix, calibration)
        if distance <= threshold:
            return (start, distance)
    return None


def _split_sessions(lane: dict[str, Any], allowed_splits: Sequence[str]) -> list[tuple[str, str]]:
    field_by_split = {
        "observation": "observation_sessions",
        "replication": "replication_sessions",
        "unopened": "unopened_sessions",
    }
    result: list[tuple[str, str]] = []
    for split in allowed_splits:
        field = field_by_split.get(str(split))
        if field is None:
            raise ValueError(f"Unknown chronological split: {split}")
        result.extend((split, str(value)) for value in lane.get(field, []))
    return sorted(result, key=lambda item: (item[1], item[0]))


def _directional_return(
    prices: np.ndarray, left: int, right: int, expected_sign: int
) -> float:
    if left < 0 or right >= len(prices) or right <= left:
        raise ValueError("Invalid fixed-horizon price indexes")
    if not (prices[left] > 0 and prices[right] > 0):
        raise ValueError("Non-positive price reached fixed-horizon outcome")
    return float(expected_sign * math.log(prices[right] / prices[left]) * 10000.0)


def prefix_events_for_hypothesis_v2(
    hypothesis: dict[str, Any],
    state: Any,
    lane: dict[str, Any],
    cache: dict[str, pd.DataFrame],
    allowed_splits: Sequence[str],
) -> list[dict[str, Any]]:
    calibration = dict(hypothesis.get("causal_prefix_calibration") or {})
    if calibration.get("suffix_values_used") is not False:
        raise ValueError("Missing suffix-free causal prefix calibration")
    future_points = int(hypothesis["future_points"])
    expected_sign = int(hypothesis["expected_completion_sign"])
    cadence = float(state.cadence)
    prefix_points = int(calibration["prefix_points"])
    events: list[dict[str, Any]] = []

    for split, session_date in _split_sessions(lane, allowed_splits):
        session = cache.get(session_date)
        if session is None:
            raise ValueError(f"Missing accepted native session: {session_date}")
        ordered = session.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
        qualifying = first_qualifying_prefix_index(
            ordered,
            calibration,
            int(state.points),
            cadence,
            future_points,
            TARGET_REGIME,
        )
        if qualifying is None:
            continue
        start, distance = qualifying
        signal_index = start + prefix_points - 1
        exit_index = signal_index + future_points
        if exit_index >= len(ordered):
            raise ValueError(
                "First qualifying signal passed known-close gate but fixed outcome rows are missing"
            )
        outcome_path = ordered.iloc[signal_index : exit_index + 1]
        if not _contiguous_native(outcome_path, cadence):
            raise ValueError(
                "First qualifying signal has a gap inside the fixed outcome horizon"
            )

        timestamps = pd.to_datetime(ordered["timestamp"], errors="coerce", utc=True)
        required_exit = timestamps.iloc[signal_index] + pd.Timedelta(
            minutes=float(future_points) * cadence
        )
        if timestamps.iloc[exit_index] != required_exit:
            raise ValueError("Fixed-horizon exit timestamp is not exact native cadence")

        prices = pd.to_numeric(ordered["price"], errors="coerce").to_numpy(float)
        gross = _directional_return(prices, signal_index, exit_index, expected_sign)
        shorter_steps = max(1, future_points // 2)
        shorter_index = signal_index + shorter_steps
        shorter = _directional_return(
            prices, signal_index, shorter_index, expected_sign
        )

        delayed = None
        if signal_index + 1 < exit_index:
            delayed = _directional_return(
                prices, signal_index + 1, exit_index, expected_sign
            )

        longer = None
        extra_steps = max(1, future_points // 2)
        longer_index = exit_index + extra_steps
        if longer_index < len(ordered):
            close_utc = _session_close_utc(session_date, TARGET_REGIME)
            if timestamps.iloc[longer_index] <= close_utc:
                longer_path = ordered.iloc[signal_index : longer_index + 1]
                if _contiguous_native(longer_path, cadence):
                    longer = _directional_return(
                        prices, signal_index, longer_index, expected_sign
                    )

        event = {
            "hypothesis_id": hypothesis["hypothesis_id"],
            "motif_id": hypothesis["motif_id"],
            "session_date": session_date,
            "split": split,
            "start_timestamp": str(timestamps.iloc[start]),
            "signal_timestamp": str(timestamps.iloc[signal_index]),
            "exit_timestamp": str(timestamps.iloc[exit_index]),
            "signal_progress": float(ordered["session_progress"].iloc[signal_index]),
            "prefix_distance": float(distance),
            "future_log_return": float(gross / (expected_sign * 10000.0)),
            "directional_return_bps": gross,
            "shorter_directional_return_bps": shorter,
            "longer_directional_return_bps": longer,
            "delayed_directional_return_bps": delayed,
            "trigger_selection": "first_qualifying_prefix_chronologically",
            "suffix_values_used_in_trigger": False,
        }
        events.append(event)

    # By construction there can be at most one signal per chronological session.
    keys = [(item["split"], item["session_date"]) for item in events]
    if len(keys) != len(set(keys)):
        raise ValueError("More than one signal was emitted for a session")
    return events


def main() -> int:
    # Replace only authority/trigger-sensitive functions; all statistical gates,
    # robustness attacks, unopened-tail rules, option gate and shadow gate remain
    # exactly as frozen in V1.
    V1.validate_inputs = validate_inputs_v2
    V1.freeze_hypotheses = freeze_hypotheses_v2
    V1.prefix_events_for_hypothesis = prefix_events_for_hypothesis_v2
    return V1.main()


if __name__ == "__main__":
    raise SystemExit(main())
