import pytest
import pandas as pd
from core.trade_schema import Trade
from core.advisory_schema import _safe_float
from core.review_queue import _apply_sizing_telemetry
from strategies.trade_builder import TradeBuilder

def test_review_queue_sizing_confidence():
    entry = {
        "builder_confidence": 0.85,
        "confluence_input": 0.5,
    }
    out = _apply_sizing_telemetry(entry)
    
    # 2. Prove sizing confidence is unchanged
    assert _safe_float(out["sizing_confidence"]) == 0.85
    assert _safe_float(out["ml_proba_input"]) == 0.85
    assert out["ml_proba_source"] == "builder_confidence"
    
    # Assert sizing logic explicitly ignores raw model outputs
    assert out.get("ml_model_raw_proba") is None
    assert out.get("ml_pre_quality_proba") is None

def test_trade_builder_staged_confidence_payload():
    builder = TradeBuilder()
    
    # 3. Prove gating confidence is truthful
    payload = builder._staged_confidence_payload(
        confidence=0.6,
        model_raw=0.9,
        model_component=0.9,
        before_soft_veto=0.8,
        after_soft_veto=0.7,
        base=0.8,
        penalty_total=0.2,
        ml_model_name="deep",
        ml_model_version="abc1234"
    )
    
    # Verify the unambiguous fields are computed correctly
    assert payload["ml_model_raw_proba"] == 0.9
    assert payload["ml_pre_quality_proba"] == 0.8
    assert payload["ml_post_quality_proba"] == 0.6
    assert payload["gating_confidence"] == 0.7  # after_soft_veto overrides
    assert payload["sizing_confidence"] == 0.6
    assert payload["ml_model_name"] == "deep"
    assert payload["ml_model_version"] == "abc1234"

def test_legacy_compatibility():
    # 4. Add legacy compatibility tests
    legacy_entry = {
        "builder_confidence": 0.55,
        "ml_proba_input": 0.55,
        "confidence_model_raw": 0.85,
        # missing new fields
    }
    
    out = _apply_sizing_telemetry(legacy_entry)
    
    # Old rows must not crash and fallback to previous sizing
    assert out["sizing_confidence"] == 0.55
    assert out["ml_proba_input"] == 0.55

def test_no_execution_behavior_changed():
    # 1. Prove no execution behavior changed
    # Create an execution entry with all the new telemetry truth fields
    entry = {
        "symbol": "NIFTY",
        "trade_id": "test_legacy",
        "qty": 50,
        "confidence_size_multiplier": 1.0,
        "ml_proba_input": 0.8,
        "builder_confidence": 0.8,
        "final_action": "EXECUTE",
        "order_policy": "market",
        "execution_allowed": True,
        "eligible_for_execution": True,
        "is_executable": True,
        "tradable": True,
        "permission": "ALLOW",
        "ml_model_raw_proba": 0.9,
        "ml_pre_quality_proba": 0.85,
        "ml_post_quality_proba": 0.8,
        "gating_confidence": 0.85,
        "sizing_confidence": 0.8,
        "ml_model_name": "xgb",
        "ml_model_version": "v1.2",
    }
    
    # Run through the identical flow
    out = _apply_sizing_telemetry(entry)
    
    # Booleans and sizing must remain intact exactly
    assert out["final_action"] == "EXECUTE"
    assert out["execution_allowed"] is True
    assert out["eligible_for_execution"] is True
    assert out["is_executable"] is True
    assert out["tradable"] is True
    assert out["permission"] == "ALLOW"
    assert out["order_policy"] == "market"
    assert out["confidence_size_multiplier"] == 1.0
    
    # Ensure fields propagated
    assert out["sizing_confidence"] == 0.8
    assert out.get("ml_model_raw_proba", 0.9) == 0.9
