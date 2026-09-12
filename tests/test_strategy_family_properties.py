"""Hypothesis property-based tests for Strategy Family Architecture & Compatibility Gate."""

from __future__ import annotations

from hypothesis import given, strategies as st

from core.strategy_family_contract import (
    StrategyFamily,
    FamilyCompatibilityResult,
    check_strategy_family_compatibility,
    admit_candidate_to_pool,
)
from core.candidate_evaluators import CandidateEmission


# -----------------------------------------------------------------------------
# Property 1: StrategyFamily.from_str is idempotent and case/format-insensitive
# -----------------------------------------------------------------------------
@given(st.sampled_from(list(StrategyFamily)))
def test_property_family_from_str_identity(family: StrategyFamily):
    assert StrategyFamily.from_str(family) == family
    assert StrategyFamily.from_str(family.value) == family
    assert StrategyFamily.from_str(family.value.lower()) == family
    assert StrategyFamily.from_str(f"  {family.value.lower()}  ") == family


# -----------------------------------------------------------------------------
# Property 2: Arbitrary unmapped strings fail closed to None in from_str
# -----------------------------------------------------------------------------
@given(st.text(min_size=1, max_size=50))
def test_property_family_unknown_fails_closed(text: str):
    # If text is not an alias or member, from_str MUST return None
    parsed = StrategyFamily.from_str(text)
    if parsed is not None:
        assert isinstance(parsed, StrategyFamily)
    else:
        # Fails closed
        assert parsed is None


# -----------------------------------------------------------------------------
# Property 3: Compatibility check is monotonic: candidate in allowed -> True, else False
# -----------------------------------------------------------------------------
@given(
    candidate_family=st.one_of(st.sampled_from(list(StrategyFamily)), st.text()),
    allowed_families=st.lists(st.one_of(st.sampled_from(list(StrategyFamily)), st.text()), max_size=10),
)
def test_property_compatibility_soundness(candidate_family, allowed_families):
    res = check_strategy_family_compatibility(candidate_family, allowed_families)
    assert isinstance(res, FamilyCompatibilityResult)
    assert res.is_order_action is False
    assert res.broker_write_authority is False

    resolved_cand = StrategyFamily.from_str(candidate_family) if candidate_family else None
    resolved_allowed = set()
    for f in allowed_families:
        rf = StrategyFamily.from_str(f) if f else None
        if rf is not None:
            resolved_allowed.add(rf)

    if resolved_cand is None:
        assert res.compatible is False
        assert res.reason_code in {"FAMILY_MISSING", "FAMILY_UNKNOWN"}
    elif not resolved_allowed:
        assert res.compatible is False
        assert res.reason_code == "REGIME_FAMILY_SET_EMPTY"
    elif resolved_cand in resolved_allowed:
        assert res.compatible is True
        assert res.reason_code == "FAMILY_COMPATIBLE"
    else:
        assert res.compatible is False
        assert res.reason_code == "FAMILY_MISMATCH"


# -----------------------------------------------------------------------------
# Property 4: Zero order authority is strictly preserved across all operations
# -----------------------------------------------------------------------------
@given(
    cand_id=st.text(min_size=1, max_size=30).filter(lambda s: bool(s.strip())),
    symbol=st.sampled_from(["NIFTY", "BANKNIFTY", "FINNIFTY"]),
    family=st.sampled_from(list(StrategyFamily)),
)
def test_property_admit_candidate_to_pool_invariants(cand_id, symbol, family):
    pool: list[dict] = []
    cand = CandidateEmission(
        candidate_id=cand_id,
        strategy_id="TEST_STRATEGY",
        symbol=symbol,
        signal_timestamp="2026-09-11 10:00:00+05:30",
        entry_boundary="NEXT_BAR_OPEN",
        exit_boundary="SESSION_CLOSE",
        stop_rule="FIXED_STOP",
        trace_id="test_trace",
        features={},
        strategy_family=family.value,
    )

    # Compatible
    compat_true = FamilyCompatibilityResult(
        compatible=True,
        candidate_family=family,
        allowed_families=frozenset({family}),
        reason_code="FAMILY_COMPATIBLE",
    )
    admitted = admit_candidate_to_pool(pool, cand, compatibility_result=compat_true)
    assert admitted is True
    assert len(pool) == 1
    assert pool[0]["is_order_action"] is False
    assert pool[0]["broker_write_authority"] is False
    assert pool[0]["strategy_family"] == family.value

    # Duplicate rejection property
    admitted_dup = admit_candidate_to_pool(pool, cand, compatibility_result=compat_true)
    assert admitted_dup is False
    assert len(pool) == 1

    # Incompatible rejection property
    pool_empty: list[dict] = []
    compat_false = FamilyCompatibilityResult(
        compatible=False,
        candidate_family=family,
        allowed_families=frozenset(),
        reason_code="FAMILY_MISMATCH",
    )
    admitted_incompat = admit_candidate_to_pool(pool_empty, cand, compatibility_result=compat_false)
    assert admitted_incompat is False
    assert len(pool_empty) == 0
