"""Tests for Regime Architecture Contract V1 and Implementation Certification."""
import pytest
import core.regime_architecture_contract as rac
from core.regime_architecture_contract import assert_architecture_compliance


def test_architecture_constants():
    """Verify frozen architecture contract constants."""
    assert rac.REGIME_HAS_ORDER_AUTHORITY is False
    assert rac.RANGE_TO_RV_TRANSITION_CAN_TRIGGER_ENTRY is False
    assert rac.RANGE_TO_RANGE_VOLATILE_EXECUTION_TRIGGER is False
    assert rac.EVENT_STATE_PRODUCTION_VALIDATED is False
    assert rac.PANIC_STATE_PRODUCTION_VALIDATED is False
    assert rac.PROBABILITIES_CALIBRATED is False
    assert rac.RANGE_VOLATILE_ROLE == "STATE_DESCRIPTOR"
    assert rac.TRANSITIONS_ROLE == "DESCRIPTIVE_CONTEXT"


def test_v1_direct_transition_entry_trigger_blocked():
    """Prove RANGE -> RANGE_VOLATILE transition cannot trigger trade entry."""
    with pytest.raises(PermissionError, match="VIOLATION V1"):
        assert_architecture_compliance(
            is_entry_trigger=True,
            transition=("RANGE", "RANGE_VOLATILE")
        )


def test_v2_uncalibrated_probability_mislabel_blocked():
    """Prove uncalibrated heuristic probabilities cannot be claimed as calibrated."""
    with pytest.raises(ValueError, match="VIOLATION V2"):
        assert_architecture_compliance(claim_calibrated=True)


def test_v3_event_panic_used_as_validated_production_state_blocked():
    """Prove EVENT and PANIC are data blocked from production gating."""
    with pytest.raises(ValueError, match="VIOLATION V3"):
        assert_architecture_compliance(claim_validated_event_panic=True, regime="EVENT")
    with pytest.raises(ValueError, match="VIOLATION V3"):
        assert_architecture_compliance(claim_validated_event_panic=True, regime="PANIC")


def test_v4_regime_direct_order_authority_blocked():
    """Prove regime outputs have zero order authority."""
    with pytest.raises(PermissionError, match="VIOLATION V4"):
        assert_architecture_compliance(is_order_action=True)


def test_valid_state_context_consumption_allowed():
    """Prove RANGE_VOLATILE can still be legitimately consumed as descriptive state context."""
    # Normal state context consumption without direct order or entry trigger
    assert assert_architecture_compliance(
        is_order_action=False,
        is_entry_trigger=False,
        regime="RANGE_VOLATILE"
    ) is True


def test_trend_and_range_consumption_allowed():
    """Prove TREND and RANGE existing valid state-consumer behavior is preserved."""
    assert assert_architecture_compliance(regime="TREND") is True
    assert assert_architecture_compliance(regime="RANGE") is True
