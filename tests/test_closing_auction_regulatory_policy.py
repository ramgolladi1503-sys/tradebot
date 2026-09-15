from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from core.closing_auction_regulatory_policy import (
    CAS_MATCHING,
    CAS_ORDER_DISCOVERY,
    CAS_REFERENCE_TRANSITION,
    DERIVATIVE_CONVERGENCE,
    NORMAL_LATE_SESSION,
    OUTSIDE_CAS_STUDY,
    assert_no_consultation_runtime_override,
    classify_closing_auction_phase,
    closing_auction_observation_requires_quarantine,
    ordinary_continuous_training_eligible,
    regulatory_overlay,
)
from core.time_utils import IST_TZ


def _at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 9, 15, hour, minute, second, tzinfo=IST_TZ)


@pytest.mark.parametrize(
    ("observed", "expected"),
    [
        (_at(14, 44, 59), OUTSIDE_CAS_STUDY),
        (_at(14, 45, 0), NORMAL_LATE_SESSION),
        (_at(15, 14, 59), NORMAL_LATE_SESSION),
        (_at(15, 15, 0), CAS_REFERENCE_TRANSITION),
        (_at(15, 19, 59), CAS_REFERENCE_TRANSITION),
        (_at(15, 20, 0), CAS_ORDER_DISCOVERY),
        (_at(15, 29, 59), CAS_ORDER_DISCOVERY),
        (_at(15, 30, 0), CAS_MATCHING),
        (_at(15, 34, 59), CAS_MATCHING),
        (_at(15, 35, 0), DERIVATIVE_CONVERGENCE),
        (_at(15, 40, 0), DERIVATIVE_CONVERGENCE),
        (_at(15, 40, 1), OUTSIDE_CAS_STUDY),
    ],
)
def test_phase_boundaries_are_exact_and_non_overlapping(observed, expected):
    assert classify_closing_auction_phase(observed) == expected


def test_timezone_conversion_cannot_shift_phase_silently():
    utc = datetime(2026, 9, 15, 9, 45, 0, tzinfo=timezone.utc)  # 15:15 IST
    assert classify_closing_auction_phase(utc) == CAS_REFERENCE_TRANSITION


def test_naive_timestamp_is_treated_as_ist_fail_closed_contract():
    naive = datetime(2026, 9, 15, 15, 30, 0)
    assert classify_closing_auction_phase(naive) == CAS_MATCHING


def test_only_normal_late_session_is_ordinary_training_eligible():
    phases = (
        NORMAL_LATE_SESSION,
        CAS_REFERENCE_TRANSITION,
        CAS_ORDER_DISCOVERY,
        CAS_MATCHING,
        DERIVATIVE_CONVERGENCE,
        OUTSIDE_CAS_STUDY,
    )
    eligible = [phase for phase in phases if ordinary_continuous_training_eligible(phase)]
    assert eligible == [NORMAL_LATE_SESSION]


@pytest.mark.parametrize(
    "phase",
    [CAS_REFERENCE_TRANSITION, CAS_ORDER_DISCOVERY, CAS_MATCHING, DERIVATIVE_CONVERGENCE],
)
def test_auction_and_convergence_observations_are_quarantined(phase):
    assert closing_auction_observation_requires_quarantine(phase) is True


def test_normal_and_outside_observations_are_not_mislabeled_as_auction():
    assert closing_auction_observation_requires_quarantine(NORMAL_LATE_SESSION) is False
    assert closing_auction_observation_requires_quarantine(OUTSIDE_CAS_STUDY) is False


def test_sebi_consultation_is_metadata_not_runtime_authority():
    overlay = regulatory_overlay(as_of=date(2026, 9, 15))
    assert overlay.status == "CONSULTATION_ONLY_NOT_EFFECTIVE_RULE"
    assert overlay.execution_changes_active is False
    assert overlay.runtime_override_allowed is False
    assert overlay.settlement_method_override_active is False
    assert overlay.post_auction_window_override_active is False
    assert overlay.cancellation_rule_override_active is False
    assert overlay.indicative_index_rule_override_active is False
    assert len(overlay.proposals) == 5
    assert_no_consultation_runtime_override(overlay)


def test_pre_consultation_date_does_not_backfill_future_proposals():
    overlay = regulatory_overlay(as_of=date(2026, 9, 11))
    assert overlay.proposals == ()
    assert overlay.execution_changes_active is False


@pytest.mark.parametrize(
    "field",
    [
        "execution_changes_active",
        "runtime_override_allowed",
        "settlement_method_override_active",
        "post_auction_window_override_active",
        "cancellation_rule_override_active",
        "indicative_index_rule_override_active",
    ],
)
def test_attack_any_illegal_consultation_promotion_is_rejected(field):
    overlay = regulatory_overlay(as_of=date(2026, 9, 15))
    attacked = replace(overlay, **{field: True})
    with pytest.raises(RuntimeError, match="consultation_only_policy_cannot_override_runtime"):
        assert_no_consultation_runtime_override(attacked)
