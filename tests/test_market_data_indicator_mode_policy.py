from core.market_data import _apply_indicator_quote_policy


def test_sim_mode_allows_fallback_ltp_when_live_quotes_not_required():
    ok = _apply_indicator_quote_policy(
        indicators_ok=True,
        ltp=100.0,
        ltp_source="fallback",
        execution_mode="SIM",
        require_live_quotes=False,
    )
    assert ok is True


def test_live_mode_rejects_non_live_ltp_source():
    ok = _apply_indicator_quote_policy(
        indicators_ok=True,
        ltp=100.0,
        ltp_source="fallback",
        execution_mode="LIVE",
        require_live_quotes=False,
    )
    assert ok is False
