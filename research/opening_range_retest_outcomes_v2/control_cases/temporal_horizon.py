from __future__ import annotations

import copy

import pandas as pd

from research.opening_range_retest_outcomes_v2 import engine, oracle
from research.opening_range_retest_outcomes_v2.control_protocol import (
    ControlExpectation,
    MutationSpec,
    RawExecution,
)
from research.opening_range_retest_outcomes_v2.contract import canonical_json_bytes, sha256_bytes


CATEGORY = "temporal_horizon"
_SESSION_DATE = "2026-07-06"


def temporal_horizon_specs() -> tuple[MutationSpec, ...]:
    return (
        _spec("S4_READYNESS_MALFORMED_TIMESTAMP", "readiness_timestamp", {"proposal_ready_at_iso": "not-a-timestamp"}, "engine.measure_candidate"),
        _spec("S4_READYNESS_OUTSIDE_SESSION", "readiness_timestamp", {"proposal_ready_at_iso": "2026-07-07T09:20:00+05:30"}, "engine.measure_candidate"),
        _spec("S4_COMPLETED_BAR_OFF_GRID_SECONDS", "readiness_timestamp", {"proposal_ready_at_iso": "2026-07-06T09:20:30+05:30"}, "engine.measure_candidate"),
        _spec("S4_COMPLETED_BAR_REQUIRED", "remove_completed_bar", {"timestamp": "2026-07-06T09:19:00"}, "engine.measure_candidate"),
        _spec("S4_SAME_TIME_EXCLUDED_FROM_ENTRY", "candidate_ready_same_time", {"proposal_ready_at_iso": "2026-07-06T09:21:00+05:30"}, "engine.measure_candidate"),
        _spec("S4_LATER_ENTRY_REQUIRED", "truncate_at_ready", {"proposal_ready_at_iso": "2026-07-06T15:29:00+05:30"}, "engine.measure_candidate"),
        _spec("S4_TIMESTAMP_DUPLICATE", "frame_timestamp", {"operation": "duplicate"}, "engine.validate_frame"),
        _spec("S4_TIMESTAMP_NON_MONOTONIC", "frame_timestamp", {"operation": "non_monotonic"}, "engine.validate_frame"),
        _spec("S4_TIMESTAMP_CADENCE_GAP", "frame_timestamp", {"operation": "cadence_gap"}, "engine.validate_frame"),
        _spec("S4_TIMESTAMP_WRONG_SESSION_DATE", "frame_timestamp", {"operation": "wrong_session_date"}, "engine.validate_frame"),
        _spec("S4_EXACT_HORIZON_MISSING_MINUTE", "remove_horizon_bar", {"timestamp": "2026-07-06T09:25:00"}, "engine.measure_candidate"),
        _spec("S4_NO_FALL_FORWARD", "shift_horizon_bar", {"from": "2026-07-06T09:25:00", "to": "2026-07-06T09:25:30"}, "engine.measure_candidate"),
        _spec("S4_HORIZON_CONSERVATION", "remove_ledger_horizon", {"horizon": "30"}, "oracle.ledger_conservation_failures"),
        _spec("S4_SESSION_ENDED_BEFORE_HORIZON", "late_ready_partial_horizon", {"proposal_ready_at_iso": "2026-07-06T15:27:00+05:30"}, "engine.measure_candidate"),
        _spec("S4_FUTURE_MUTATION_BLOCKED", "future_timestamp_mutation", {"timestamp": "2026-07-07T09:20:00"}, "engine.validate_frame"),
    )


def temporal_horizon_expectations() -> tuple[ControlExpectation, ...]:
    return (
        _expect("S4_READYNESS_MALFORMED_TIMESTAMP", "CANDIDATE_TIMESTAMP_MALFORMED"),
        _expect("S4_READYNESS_OUTSIDE_SESSION", "CANDIDATE_TIMESTAMP_OUTSIDE_SESSION"),
        _expect("S4_COMPLETED_BAR_OFF_GRID_SECONDS", "CANDIDATE_READY_OFF_GRID"),
        _expect("S4_COMPLETED_BAR_REQUIRED", "CANDIDATE_READY_BAR_MISSING"),
        _expect("S4_SAME_TIME_EXCLUDED_FROM_ENTRY", "SAME_TIMESTAMP_BAR_SKIPPED_FOR_PRIMARY"),
        _expect("S4_LATER_ENTRY_REQUIRED", "NO_LEGAL_ENTRY_BAR"),
        _expect("S4_TIMESTAMP_DUPLICATE", "SOURCE_TIMESTAMP_GAP"),
        _expect("S4_TIMESTAMP_NON_MONOTONIC", "SOURCE_TIMESTAMP_GAP"),
        _expect("S4_TIMESTAMP_CADENCE_GAP", "SOURCE_TIMESTAMP_GAP"),
        _expect("S4_TIMESTAMP_WRONG_SESSION_DATE", "SOURCE_SESSION_MISMATCH"),
        _expect("S4_EXACT_HORIZON_MISSING_MINUTE", "MISSING_EXPECTED_MINUTE"),
        _expect("S4_NO_FALL_FORWARD", "MISSING_EXPECTED_MINUTE"),
        _expect("S4_HORIZON_CONSERVATION", "CANDIDATE_OR_HORIZON_CONSERVATION_FAIL"),
        _expect("S4_SESSION_ENDED_BEFORE_HORIZON", "SESSION_ENDED_BEFORE_HORIZON"),
        _expect("S4_FUTURE_MUTATION_BLOCKED", "SOURCE_SESSION_MISMATCH"),
    )


def execute_temporal_horizon_control(spec: MutationSpec) -> RawExecution:
    candidate = _candidate()
    source = _source()
    frame = _frame()
    before = _fixture_hash(candidate, source, frame)

    observed: tuple[str, ...]
    target_invoked = False
    if spec.target_function == "engine.validate_frame":
        _mutate_frame(spec, frame)
        target_invoked = True
        failure = engine.validate_frame(frame, source)
        observed = tuple([failure] if failure else [])
    elif spec.target_function == "engine.measure_candidate":
        _mutate_measure_fixture(spec, candidate, frame)
        target_invoked = True
        outcome = engine.measure_candidate(candidate, source, frame, _contract())
        observed = _measure_failures(spec, outcome)
    elif spec.target_function == "oracle.ledger_conservation_failures":
        baseline_record = engine.measure_candidate(candidate, source, frame, _contract())
        actual = copy.deepcopy(baseline_record)
        actual["horizons"].pop(str(spec.mutation_payload["horizon"]))
        before = _payload_hash([baseline_record])
        target_invoked = True
        observed = tuple(oracle.ledger_conservation_failures([actual], expected_candidate_count=1))
        after = _payload_hash([actual])
        return RawExecution(
            observed_failures=observed,
            target_invoked=target_invoked,
            mutation_applied=before != after,
            fixture_hash_before=before,
            fixture_hash_after=after,
            target_output_hash=_payload_hash(observed),
        )
    else:
        raise ValueError(f"unsupported target function: {spec.target_function}")

    after = _fixture_hash(candidate, source, frame)
    return RawExecution(
        observed_failures=observed,
        target_invoked=target_invoked,
        mutation_applied=before != after,
        fixture_hash_before=before,
        fixture_hash_after=after,
        target_output_hash=_payload_hash(observed),
    )


def control_fingerprint(spec: MutationSpec, raw: RawExecution) -> str:
    return _payload_hash(
        {
            "control_id": spec.control_id,
            "category": spec.category,
            "mutation_kind": spec.mutation_kind,
            "mutation_payload": dict(spec.mutation_payload),
            "target_function": spec.target_function,
            "observed_failures": raw.observed_failures,
            "target_output_hash": raw.target_output_hash,
        }
    )


def _spec(control_id: str, mutation_kind: str, mutation_payload: dict[str, object], target_function: str) -> MutationSpec:
    return MutationSpec(
        control_id=control_id,
        category=CATEGORY,
        mutation_kind=mutation_kind,
        mutation_payload=mutation_payload,
        target_function=target_function,
    )


def _expect(control_id: str, failure: str) -> ControlExpectation:
    return ControlExpectation(control_id=control_id, expected_failures=(failure,))


def _frame() -> pd.DataFrame:
    timestamps = pd.date_range(f"{_SESSION_DATE} 09:15:00", periods=375, freq="min")
    rows = []
    for index, timestamp in enumerate(timestamps):
        price = 100.0 + index * 0.1
        rows.append(
            {
                "timestamp": timestamp,
                "symbol": "NIFTY",
                "open": price,
                "high": price + 0.05,
                "low": price - 0.05,
                "close": price + 0.02,
                "volume": 1000 + index,
                "oi": 0,
                "source": "fixture",
                "interval": "1minute",
                "fetch_timestamp": f"{_SESSION_DATE}T15:35:00+05:30",
                "fetch_start_date": _SESSION_DATE,
                "fetch_end_date": _SESSION_DATE,
                "data_origin": "fixture",
                "synthetic": False,
                "mock": False,
                "fallback": False,
                "provider": "fixture",
                "source_endpoint": "fixture",
            }
        )
    return pd.DataFrame(rows, columns=engine.SOURCE_COLUMNS)


def _source() -> dict[str, object]:
    return {
        "source_record_id": "S4_SOURCE",
        "logical_path": "runtime/upstox_candidate_replay/s4_fixture.parquet",
        "actual_sha256": "fixture",
        "symbol": "NIFTY",
        "session_date": _SESSION_DATE,
        "byte_size": 1,
    }


def _candidate() -> dict[str, object]:
    return {
        "candidate_id": "S4_CANDIDATE",
        "candidate_core": {
            "symbol": "NIFTY",
            "session_date": _SESSION_DATE,
            "direction": "BUY_CALL",
            "proposal_ready_at_iso": "2026-07-06T09:20:00+05:30",
        },
        "source_provenance": {
            "source_record_id": "S4_SOURCE",
            "source_logical_path": "runtime/upstox_candidate_replay/s4_fixture.parquet",
            "source_actual_sha256": "fixture",
            "source_symbol": "NIFTY",
            "source_session_date": _SESSION_DATE,
            "source_manifest_semantic_hash": engine.INPUT_SOURCE_HASH,
            "source_manifest_version": "v2",
        },
    }


def _contract() -> dict[str, str]:
    return {
        "contract_hash": "s4_contract_hash",
        "frozen_code_sha": "661721315d7f606cac99e4517075622c33c1472e",
        "implementation_tree_hash": "s4_tree_hash",
    }


def _mutate_measure_fixture(spec: MutationSpec, candidate: dict[str, object], frame: pd.DataFrame) -> None:
    core = candidate["candidate_core"]
    assert isinstance(core, dict)
    if spec.mutation_kind == "readiness_timestamp":
        core["proposal_ready_at_iso"] = spec.mutation_payload["proposal_ready_at_iso"]
    elif spec.mutation_kind == "remove_completed_bar":
        _drop_timestamp_in_place(frame, str(spec.mutation_payload["timestamp"]))
    elif spec.mutation_kind == "candidate_ready_same_time":
        core["proposal_ready_at_iso"] = spec.mutation_payload["proposal_ready_at_iso"]
    elif spec.mutation_kind == "truncate_at_ready":
        core["proposal_ready_at_iso"] = spec.mutation_payload["proposal_ready_at_iso"]
    elif spec.mutation_kind == "remove_horizon_bar":
        _drop_timestamp_in_place(frame, str(spec.mutation_payload["timestamp"]))
    elif spec.mutation_kind == "shift_horizon_bar":
        row = frame.index[frame["timestamp"] == pd.Timestamp(spec.mutation_payload["from"])][0]
        frame.loc[row, "timestamp"] = pd.Timestamp(spec.mutation_payload["to"])
    elif spec.mutation_kind == "late_ready_partial_horizon":
        core["proposal_ready_at_iso"] = spec.mutation_payload["proposal_ready_at_iso"]
    else:
        raise ValueError(f"unsupported measure mutation: {spec.mutation_kind}")


def _mutate_frame(spec: MutationSpec, frame: pd.DataFrame) -> None:
    operation = spec.mutation_payload.get("operation")
    if operation == "duplicate":
        frame.loc[10, "timestamp"] = frame.loc[9, "timestamp"]
    elif operation == "non_monotonic":
        frame.loc[10, "timestamp"], frame.loc[11, "timestamp"] = frame.loc[11, "timestamp"], frame.loc[10, "timestamp"]
    elif operation == "cadence_gap":
        frame.loc[10, "timestamp"] = frame.loc[10, "timestamp"] + pd.Timedelta(minutes=1)
    elif operation == "wrong_session_date":
        frame["timestamp"] = frame["timestamp"] + pd.Timedelta(days=1)
    elif spec.mutation_kind == "future_timestamp_mutation":
        frame["timestamp"] = frame["timestamp"] + pd.Timedelta(days=1)
    else:
        raise ValueError(f"unsupported frame mutation: {spec.mutation_kind}")


def _measure_failures(spec: MutationSpec, outcome: dict[str, object]) -> tuple[str, ...]:
    if spec.mutation_kind == "candidate_ready_same_time":
        legal_entry = outcome["legal_entry"]
        if isinstance(legal_entry, dict) and legal_entry.get("start") == "2026-07-06T09:22:00+05:30":
            return ("SAME_TIMESTAMP_BAR_SKIPPED_FOR_PRIMARY",)
        return ("SAME_TIMESTAMP_BAR_NOT_SKIPPED",)
    if spec.mutation_kind in {"remove_horizon_bar", "shift_horizon_bar"}:
        status = outcome["horizons"]["5"]["status"]  # type: ignore[index]
        return (str(status),)
    if spec.mutation_kind == "late_ready_partial_horizon":
        statuses = {payload["status"] for payload in outcome["horizons"].values()}  # type: ignore[union-attr]
        return tuple(sorted(statuses - {"MEASURED"}))
    terminal_reason = outcome.get("terminal_reason")
    return tuple([str(terminal_reason)] if terminal_reason else [])


def _drop_timestamp_in_place(frame: pd.DataFrame, timestamp: str) -> None:
    drop_index = frame.index[frame["timestamp"] == pd.Timestamp(timestamp)]
    frame.drop(index=drop_index, inplace=True)
    frame.reset_index(drop=True, inplace=True)


def _fixture_hash(candidate: dict[str, object], source: dict[str, object], frame: pd.DataFrame) -> str:
    return _payload_hash(
        {
            "candidate": candidate,
            "source": source,
            "frame": frame.astype({"timestamp": "string"}).to_dict(orient="records"),
        }
    )


def _payload_hash(payload: object) -> str:
    return sha256_bytes(canonical_json_bytes(payload))
