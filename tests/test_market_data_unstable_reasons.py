from core.market_data import _derive_unstable_reasons


def test_unstable_reasons_empty_for_confident_regime_with_sufficient_bars():
    reasons = _derive_unstable_reasons(
        regime_probs={"TREND": 1.0},
        regime_entropy=0.0,
        regime_transition_rate=0.0,
        indicators_ok=True,
        ohlc_bars_count=120,
        min_bars=30,
        missing_inputs=[],
        model_unstable_flag=False,
    )
    assert reasons == []


def test_unstable_reasons_include_warmup_when_bars_insufficient():
    reasons = _derive_unstable_reasons(
        regime_probs={"TREND": 1.0},
        regime_entropy=0.0,
        regime_transition_rate=0.0,
        indicators_ok=True,
        ohlc_bars_count=5,
        min_bars=30,
        missing_inputs=["ohlc_buffer_insufficient"],
        model_unstable_flag=False,
    )
    assert "warmup_incomplete" in reasons
    assert "bars_insufficient" in reasons

