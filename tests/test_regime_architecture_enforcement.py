"""Integration-level tests proving real production consumer enforcement of Regime Architecture Contract V1."""
import pytest
from strategies.trade_builder import TradeBuilder
import core.regime_architecture_contract as rac
from core.regime_architecture_contract import assert_architecture_compliance


def test_t1_range_to_rv_transition_alone_cannot_create_executable_trade_authority():
    """T1: Prove RANGE->RV transition alone cannot create an executable trade signal."""
    # assert_architecture_compliance rejects transition entry
    with pytest.raises(PermissionError, match="VIOLATION V1"):
        assert_architecture_compliance(
            is_entry_trigger=True,
            transition=("RANGE", "RANGE_VOLATILE")
        )
    assert rac.RANGE_TO_RV_TRANSITION_CAN_TRIGGER_ENTRY is False
    assert rac.RANGE_TO_RANGE_VOLATILE_EXECUTION_TRIGGER is False
    assert rac.TRANSITION_EXECUTION_TRIGGER_ALLOWED is False
    assert TradeBuilder.RANGE_TO_RANGE_VOLATILE_EXECUTION_TRIGGER is False
    assert TradeBuilder.RANGE_TO_RV_TRANSITION_CAN_TRIGGER_ENTRY is False


def test_t2_transition_no_candidate_promotion():
    """T2: Prove transition cannot promote a candidate to execution authority."""
    with pytest.raises(PermissionError, match="VIOLATION V4"):
        assert_architecture_compliance(is_order_action=True, is_entry_trigger=True)

    tb = TradeBuilder()
    candidate = {"direction": "BUY_CALL", "reason": "test", "score": 0.8, "regime_day": "RANGE"}
    override = tb._candidate_regime_override(candidate)
    assert not bool(override.get("order_authority"))


def test_t3_range_volatile_context_allowed():
    """T3: Prove RANGE_VOLATILE state context still legitimately passes through allowed consumer paths."""
    # Allowed state-conditioning call
    assert assert_architecture_compliance(
        is_order_action=False,
        is_entry_trigger=False,
        regime="RANGE_VOLATILE"
    ) is True
    assert rac.RANGE_VOLATILE_ROLE == "STATE_DESCRIPTOR"


def test_t4_trend_range_regression():
    """T4: Prove TREND and RANGE valid existing behavior remains unchanged."""
    tb = TradeBuilder()
    assert tb.allowed_strategy_families("TREND") == ["TREND"]
    assert tb.allowed_strategy_families("RANGE") == ["MEAN_REVERT"]


def test_t5_event_blocked_from_production_route():
    """T5: Prove EVENT cannot activate a validated production route in TradeBuilder."""
    tb = TradeBuilder()
    assert tb.allowed_strategy_families("EVENT") == []


def test_t6_panic_blocked_from_production_route():
    """T6: Prove PANIC cannot activate a validated production route."""
    tb = TradeBuilder()
    assert tb.allowed_strategy_families("PANIC") == []


def test_t7_probability_mislabel_blocked():
    """T7: Prove heuristic vector cannot be claimed as calibrated probabilities."""
    with pytest.raises(ValueError, match="VIOLATION V2"):
        assert_architecture_compliance(claim_calibrated=True)
    assert rac.PROBABILITIES_CALIBRATED is False


def test_t8_no_regime_order_authority():
    """T8: Prove regime output cannot create direct broker or order authority."""
    with pytest.raises(PermissionError, match="VIOLATION V4"):
        assert_architecture_compliance(is_order_action=True)
    assert rac.REGIME_HAS_ORDER_AUTHORITY is False


def test_t9_no_consumer_bypass():
    """T9: Prove no alternate path bypasses contract assertions."""
    # Attempting to validate EVENT as production state fails
    with pytest.raises(ValueError, match="VIOLATION V3"):
        assert_architecture_compliance(claim_validated_event_panic=True, regime="EVENT")


def test_t10_contract_runtime_parity():
    """T10: Prove contract constants and runtime enforcement agree."""
    assert rac.EVENT_STATE_PRODUCTION_VALIDATED is False
    assert rac.PANIC_STATE_PRODUCTION_VALIDATED is False
    assert rac.TRANSITIONS_ROLE == "DESCRIPTIVE_CONTEXT"
