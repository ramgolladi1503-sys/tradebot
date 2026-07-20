from __future__ import annotations

import inspect

import pytest

from research.opening_range_retest_outcomes_v2.control_cases import math_identity
from research.opening_range_retest_outcomes_v2.control_protocol import (
    ControlExpectation,
    MutationSpec,
    RawExecution,
)


@pytest.mark.parametrize("control", math_identity.MATH_IDENTITY_CONTROLS, ids=lambda control: control.spec.control_id)
def test_math_identity_control_emits_exact_failure(control: math_identity.MathIdentityControl) -> None:
    if control.spec.mutation_kind == "duplicate_candidate_id":
        raw = math_identity.execute_duplicate_identity(control.spec)
    else:
        raw = math_identity.execute_math_identity(control.spec)

    assert isinstance(control.spec, MutationSpec)
    assert isinstance(control.expectation, ControlExpectation)
    assert isinstance(raw, RawExecution)
    assert raw.target_invoked is True
    assert raw.mutation_applied is True
    assert raw.fixture_hash_before != raw.fixture_hash_after
    assert set(raw.observed_failures) == set(control.expectation.expected_failures)


def test_valid_buy_call_and_buy_put_records_are_distinct_and_clean() -> None:
    buy_call, buy_put = math_identity.valid_records()

    assert buy_call["candidate_id"] != buy_put["candidate_id"]
    assert buy_call["outcome_id"] != buy_put["outcome_id"]
    assert buy_call["direction"] == "BUY_CALL"
    assert buy_put["direction"] == "BUY_PUT"
    assert math_identity.verify_math_record_failures(buy_call) == ()
    assert math_identity.verify_math_record_failures(buy_put) == ()
    assert buy_call["horizons"]["1"]["directional_underlying_return"] > 0
    assert buy_put["horizons"]["1"]["directional_underlying_return"] > 0
    assert buy_call["horizons"]["1"]["unsigned_underlying_return"] > 0
    assert buy_put["horizons"]["1"]["unsigned_underlying_return"] < 0


def test_math_identity_controls_cover_required_s5_surface() -> None:
    covered_kinds = {control.spec.mutation_kind for control in math_identity.MATH_IDENTITY_CONTROLS}

    assert {
        "entry_price",
        "terminal_close",
        "unsigned_return",
        "directional_return",
        "buy_call_direction_sign",
        "buy_put_direction_sign",
        "mfe",
        "mae",
        "extrema_timestamp",
        "measured_count",
        "outcome_id",
        "duplicate_candidate_id",
    } <= covered_kinds
    assert {control.spec.mutation_payload["fixture"] for control in math_identity.MATH_IDENTITY_CONTROLS} == {
        "BUY_CALL",
        "BUY_PUT",
    }


def test_math_identity_executors_do_not_access_expectations() -> None:
    executor_sources = "\n".join(
        inspect.getsource(function)
        for function in (math_identity.execute_math_identity, math_identity.execute_duplicate_identity)
    )

    assert "ControlExpectation" not in executor_sources
    assert "expected_failure" not in executor_sources
    assert "expected_failures" not in executor_sources
    assert ".expectation" not in executor_sources
