from core.freshness_evaluator import evaluate_quote_freshness, freshness_public_fields


def test_quote_age_below_threshold_is_fresh():
    decision = evaluate_quote_freshness(
        symbol="NIFTY",
        instrument_token=123,
        quote_epoch=100.0,
        candle_epoch=None,
        threshold_sec=8.0,
        market_open=True,
        now_epoch=102.1,
    )

    assert decision.fresh is True
    assert decision.blocker is False
    assert decision.freshness_reason == "quote_within_threshold"
    assert abs(float(decision.quote_age_sec or 0.0) - 2.1) < 1e-6
    assert float(decision.evaluated_at_epoch) == 102.1


def test_quote_age_above_threshold_is_stale():
    decision = evaluate_quote_freshness(
        symbol="NIFTY",
        instrument_token=123,
        quote_epoch=100.0,
        candle_epoch=None,
        threshold_sec=8.0,
        market_open=True,
        now_epoch=118.4,
    )

    assert decision.fresh is False
    assert decision.blocker is True
    assert decision.freshness_reason == "quote_exceeds_threshold"
    assert abs(float(decision.quote_age_sec or 0.0) - 18.4) < 1e-6


def test_market_closed_interaction_is_predictable():
    decision = evaluate_quote_freshness(
        symbol="NIFTY",
        instrument_token=123,
        quote_epoch=100.0,
        candle_epoch=None,
        threshold_sec=2.5,
        market_open=False,
        now_epoch=120.0,
    )

    assert decision.fresh is True
    assert decision.blocker is False
    assert decision.freshness_reason == "market_closed_skip_strict_stale"
    payload = freshness_public_fields(decision)
    assert payload["freshness_market_open"] is False
    assert float(payload["freshness_threshold_sec"]) == 2.5


def test_freshness_output_preserves_numeric_evidence():
    decision = evaluate_quote_freshness(
        symbol="BANKNIFTY",
        instrument_token=456,
        quote_epoch=None,
        candle_epoch=100.0,
        threshold_sec=8.0,
        market_open=True,
        now_epoch=106.0,
        allow_candle_fallback=True,
    )

    assert decision.selected_source == "candle"
    assert decision.quote_epoch is None
    assert float(decision.candle_epoch or 0.0) == 100.0
    assert abs(float(decision.candle_age_sec or 0.0) - 6.0) < 1e-6
    assert abs(float(decision.selected_age_sec or 0.0) - 6.0) < 1e-6
    assert decision.freshness_reason == "fallback_to_candle_within_threshold"
