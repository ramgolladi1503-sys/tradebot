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


def test_unstable_reasons_include_prob_and_entropy_reasons_when_unstable():
    reasons = _derive_unstable_reasons(
        regime_probs={"TREND": 0.40, "RANGE": 0.35, "EVENT": 0.25},
        regime_entropy=2.0,
        regime_transition_rate=0.0,
        indicators_ok=True,
        ohlc_bars_count=120,
        min_bars=30,
        missing_inputs=[],
        model_unstable_flag=False,
    )
    assert "prob_too_low" in reasons
    assert "entropy_too_high" in reasons
