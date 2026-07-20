from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from research.opening_range_retest_outcomes_v2.control_protocol import (
    ControlExpectation,
    MutationSpec,
    RawExecution,
)
from research.opening_range_retest_outcomes_v2.oracle import ledger_conservation_failures


CATEGORY = "math_identity"
HORIZON = "1"


@dataclass(frozen=True)
class MathIdentityControl:
    spec: MutationSpec
    expectation: ControlExpectation


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _horizon_payload(
    *,
    direction: str,
    entry_open: float,
    terminal_close: float,
    high: float,
    low: float,
    mfe_timestamp: str,
    mae_timestamp: str,
) -> dict[str, Any]:
    unsigned = round((terminal_close - entry_open) / entry_open, 12)
    if direction == "BUY_CALL":
        directional = unsigned
        mfe = round((high - entry_open) / entry_open, 12)
        mae = round((low - entry_open) / entry_open, 12)
    elif direction == "BUY_PUT":
        directional = round(-unsigned, 12)
        mfe = round((entry_open - low) / entry_open, 12)
        mae = round((entry_open - high) / entry_open, 12)
    else:
        raise ValueError(f"unsupported direction: {direction}")
    return {
        "horizon_minutes": 1,
        "status": "MEASURED",
        "reason": "MEASURED",
        "terminal_close": terminal_close,
        "unsigned_underlying_return": unsigned,
        "directional_underlying_return": directional,
        "high": high,
        "low": low,
        "mfe": mfe,
        "mae": mae,
        "mfe_timestamp": mfe_timestamp,
        "mae_timestamp": mae_timestamp,
    }


def _valid_record(
    *,
    candidate_id: str,
    direction: str,
    entry_open: float,
    terminal_close: float,
    high: float,
    low: float,
    mfe_timestamp: str,
    mae_timestamp: str,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "outcome_id": hashlib.sha256(f"{candidate_id}|{direction}|1".encode("utf-8")).hexdigest(),
        "direction": direction,
        "legal_entry": {
            "start": "2026-07-06T09:20:00+05:30",
            "end": "2026-07-06T09:21:00+05:30",
            "open": entry_open,
        },
        "terminal_reason": "MEASURED",
        "measured_horizon_count": 1,
        "horizons": {
            HORIZON: _horizon_payload(
                direction=direction,
                entry_open=entry_open,
                terminal_close=terminal_close,
                high=high,
                low=low,
                mfe_timestamp=mfe_timestamp,
                mae_timestamp=mae_timestamp,
            )
        },
    }


def valid_buy_call_record() -> dict[str, Any]:
    return _valid_record(
        candidate_id="S5_VALID_BUY_CALL",
        direction="BUY_CALL",
        entry_open=100.0,
        terminal_close=103.0,
        high=106.0,
        low=98.0,
        mfe_timestamp="2026-07-06T09:20:00+05:30",
        mae_timestamp="2026-07-06T09:21:00+05:30",
    )


def valid_buy_put_record() -> dict[str, Any]:
    return _valid_record(
        candidate_id="S5_VALID_BUY_PUT",
        direction="BUY_PUT",
        entry_open=200.0,
        terminal_close=194.0,
        high=202.0,
        low=190.0,
        mfe_timestamp="2026-07-06T09:22:00+05:30",
        mae_timestamp="2026-07-06T09:23:00+05:30",
    )


def valid_records() -> tuple[dict[str, Any], dict[str, Any]]:
    return valid_buy_call_record(), valid_buy_put_record()


def verify_math_record_failures(record: dict[str, Any]) -> tuple[str, ...]:
    failures: list[str] = []
    direction = record.get("direction")
    entry_open = record.get("legal_entry", {}).get("open")
    horizons = record.get("horizons", {})
    measured_horizons = [payload for payload in horizons.values() if payload.get("status") == "MEASURED"]
    if record.get("measured_horizon_count") != len(measured_horizons):
        failures.append("MEASURED_HORIZON_COUNT_MISMATCH")
    expected_outcome_id = hashlib.sha256(f"{record.get('candidate_id')}|{direction}|1".encode("utf-8")).hexdigest()
    if record.get("outcome_id") != expected_outcome_id:
        failures.append("OUTCOME_ID_MISMATCH")
    for payload in measured_horizons:
        terminal_close = payload.get("terminal_close")
        high = payload.get("high")
        low = payload.get("low")
        if not all(isinstance(value, (int, float)) for value in (entry_open, terminal_close, high, low)):
            failures.append("MATH_NUMERIC_FIELD_INVALID")
            continue
        unsigned = round((terminal_close - entry_open) / entry_open, 12)
        if payload.get("unsigned_underlying_return") != unsigned:
            failures.append("UNSIGNED_RETURN_MISMATCH")
        if direction == "BUY_CALL":
            directional = unsigned
            mfe = round((high - entry_open) / entry_open, 12)
            mae = round((low - entry_open) / entry_open, 12)
            if directional <= 0:
                failures.append("BUY_CALL_DIRECTION_SIGN_MISMATCH")
        elif direction == "BUY_PUT":
            directional = round(-unsigned, 12)
            mfe = round((entry_open - low) / entry_open, 12)
            mae = round((entry_open - high) / entry_open, 12)
            if directional <= 0:
                failures.append("BUY_PUT_DIRECTION_SIGN_MISMATCH")
        else:
            failures.append("DIRECTION_UNSUPPORTED")
            continue
        if payload.get("directional_underlying_return") != directional:
            failures.append("DIRECTIONAL_RETURN_MISMATCH")
        if payload.get("mfe") != mfe:
            failures.append("MFE_MISMATCH")
        if payload.get("mae") != mae:
            failures.append("MAE_MISMATCH")
        if payload.get("mfe_timestamp") == payload.get("mae_timestamp"):
            failures.append("EXTREMA_TIMESTAMP_MISMATCH")
    return tuple(dict.fromkeys(failures))


def _record_for_spec(spec: MutationSpec) -> dict[str, Any]:
    fixture = valid_buy_put_record() if spec.mutation_payload.get("fixture") == "BUY_PUT" else valid_buy_call_record()
    record = copy.deepcopy(fixture)
    kind = spec.mutation_kind
    horizon = record["horizons"][HORIZON]
    if kind == "entry_price":
        record["legal_entry"]["open"] += 1.0
    elif kind == "terminal_close":
        horizon["terminal_close"] += 1.0
    elif kind == "unsigned_return":
        horizon["unsigned_underlying_return"] += 0.01
    elif kind == "directional_return":
        horizon["directional_underlying_return"] *= -1
    elif kind == "buy_call_direction_sign":
        horizon["terminal_close"] = record["legal_entry"]["open"] - 3.0
        _recompute_horizon(record)
    elif kind == "buy_put_direction_sign":
        horizon["terminal_close"] = record["legal_entry"]["open"] + 6.0
        _recompute_horizon(record)
    elif kind == "mfe":
        horizon["mfe"] += 0.01
    elif kind == "mae":
        horizon["mae"] -= 0.01
    elif kind == "extrema_timestamp":
        horizon["mae_timestamp"] = horizon["mfe_timestamp"]
    elif kind == "measured_count":
        record["measured_horizon_count"] += 1
    elif kind == "outcome_id":
        record["outcome_id"] = "0" * 64
    else:
        raise ValueError(f"unsupported mutation kind: {kind}")
    return record


def execute_math_identity(spec: MutationSpec) -> RawExecution:
    before = valid_buy_put_record() if spec.mutation_payload.get("fixture") == "BUY_PUT" else valid_buy_call_record()
    after = _record_for_spec(spec)
    observed = verify_math_record_failures(after)
    return RawExecution(
        observed_failures=observed,
        target_invoked=True,
        mutation_applied=_canonical_hash(before) != _canonical_hash(after),
        fixture_hash_before=_canonical_hash(before),
        fixture_hash_after=_canonical_hash(after),
        target_output_hash=_canonical_hash(observed),
    )


def execute_duplicate_identity(spec: MutationSpec) -> RawExecution:
    before = [_with_all_conservation_horizons(valid_buy_call_record()), _with_all_conservation_horizons(valid_buy_put_record())]
    after = copy.deepcopy(before)
    after[1]["candidate_id"] = after[0]["candidate_id"]
    observed = tuple(ledger_conservation_failures(after, expected_candidate_count=2))
    return RawExecution(
        observed_failures=observed,
        target_invoked=True,
        mutation_applied=_canonical_hash(before) != _canonical_hash(after),
        fixture_hash_before=_canonical_hash(before),
        fixture_hash_after=_canonical_hash(after),
        target_output_hash=_canonical_hash(observed),
    )


def _recompute_horizon(record: dict[str, Any]) -> None:
    horizon = record["horizons"][HORIZON]
    horizon.update(
        _horizon_payload(
            direction=record["direction"],
            entry_open=record["legal_entry"]["open"],
            terminal_close=horizon["terminal_close"],
            high=horizon["high"],
            low=horizon["low"],
            mfe_timestamp=horizon["mfe_timestamp"],
            mae_timestamp=horizon["mae_timestamp"],
        )
    )


def _with_all_conservation_horizons(record: dict[str, Any]) -> dict[str, Any]:
    expanded = copy.deepcopy(record)
    for horizon in ("3", "5", "15", "30"):
        expanded["horizons"][horizon] = copy.deepcopy(expanded["horizons"][HORIZON])
        expanded["horizons"][horizon]["horizon_minutes"] = int(horizon)
    expanded["measured_horizon_count"] = 5
    return expanded


def _control(
    control_id: str,
    mutation_kind: str,
    expected_failures: str | tuple[str, ...],
    *,
    fixture: str = "BUY_CALL",
    target_function: str = "math_identity.verify_math_record_failures",
) -> MathIdentityControl:
    failures = (expected_failures,) if isinstance(expected_failures, str) else expected_failures
    return MathIdentityControl(
        spec=MutationSpec(
            control_id=control_id,
            category=CATEGORY,
            mutation_kind=mutation_kind,
            mutation_payload={"fixture": fixture},
            target_function=target_function,
        ),
        expectation=ControlExpectation(control_id=control_id, expected_failures=failures),
    )


MATH_IDENTITY_CONTROLS: tuple[MathIdentityControl, ...] = (
    _control(
        "MATH_ENTRY_PRICE_BUY_CALL",
        "entry_price",
        ("UNSIGNED_RETURN_MISMATCH", "DIRECTIONAL_RETURN_MISMATCH", "MFE_MISMATCH", "MAE_MISMATCH"),
    ),
    _control("MATH_TERMINAL_CLOSE_BUY_CALL", "terminal_close", ("UNSIGNED_RETURN_MISMATCH", "DIRECTIONAL_RETURN_MISMATCH")),
    _control("MATH_UNSIGNED_RETURN_BUY_CALL", "unsigned_return", "UNSIGNED_RETURN_MISMATCH"),
    _control("MATH_DIRECTIONAL_RETURN_BUY_CALL", "directional_return", "DIRECTIONAL_RETURN_MISMATCH"),
    _control("MATH_BUY_CALL_DIRECTION_SIGN", "buy_call_direction_sign", "BUY_CALL_DIRECTION_SIGN_MISMATCH"),
    _control("MATH_MFE_BUY_CALL", "mfe", "MFE_MISMATCH"),
    _control("MATH_MAE_BUY_CALL", "mae", "MAE_MISMATCH"),
    _control("MATH_EXTREMA_BUY_CALL", "extrema_timestamp", "EXTREMA_TIMESTAMP_MISMATCH"),
    _control("MATH_MEASURED_COUNT_BUY_CALL", "measured_count", "MEASURED_HORIZON_COUNT_MISMATCH"),
    _control("MATH_OUTCOME_ID_BUY_CALL", "outcome_id", "OUTCOME_ID_MISMATCH"),
    _control("MATH_UNSIGNED_RETURN_BUY_PUT", "unsigned_return", "UNSIGNED_RETURN_MISMATCH", fixture="BUY_PUT"),
    _control("MATH_DIRECTIONAL_RETURN_BUY_PUT", "directional_return", "DIRECTIONAL_RETURN_MISMATCH", fixture="BUY_PUT"),
    _control("MATH_BUY_PUT_DIRECTION_SIGN", "buy_put_direction_sign", "BUY_PUT_DIRECTION_SIGN_MISMATCH", fixture="BUY_PUT"),
    _control(
        "MATH_DUPLICATE_CANDIDATE_ID",
        "duplicate_candidate_id",
        "DUPLICATE_CANDIDATE_ID",
        target_function="oracle.ledger_conservation_failures",
    ),
)

MUTATION_SPECS = tuple(control.spec for control in MATH_IDENTITY_CONTROLS)
EXPECTATIONS = tuple(control.expectation for control in MATH_IDENTITY_CONTROLS)
EXECUTORS = {
    "math_identity.verify_math_record_failures": execute_math_identity,
    "oracle.ledger_conservation_failures": execute_duplicate_identity,
}
