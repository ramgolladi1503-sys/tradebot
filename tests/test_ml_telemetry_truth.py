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
    assert _safe_float(out["sizing_confidence"]) == 0.85
    assert _safe_float(out["ml_proba_input"]) == 0.85
    assert out["ml_proba_source"] == "builder_confidence"

def test_trade_builder_staged_confidence_payload():
    builder = TradeBuilder()
    
    # Mock some values that would come out of the decay logic
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
    assert payload["gating_confidence"] == 0.7
    assert payload["sizing_confidence"] == 0.6
    assert payload["ml_model_name"] == "deep"
    assert payload["ml_model_version"] == "abc1234"
