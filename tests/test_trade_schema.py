from datetime import datetime, timezone

from core.trade_schema import Trade


def test_trade_hydrates_live_decision_telemetry_from_source_flags():
    trade = Trade(
        trade_id="T-1",
        timestamp=datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc),
        symbol="SENSEX",
        instrument="OPT",
        instrument_token=12345,
        strike=76900,
        expiry="2026-05-07",
        side="BUY",
        entry_price=100.0,
        stop_loss=95.0,
        target=110.0,
        qty=1,
        capital_at_risk=100.0,
        expected_slippage=0.5,
        confidence=0.7,
        strategy="breakout",
        regime="TREND",
        source_flags={
            "liquidity_score": 0.8125,
            "quote_consistency_score": 0.91,
            "quote_validation_status": "OK",
            "raw_rank_score": 0.746802,
            "terminal_rank_score": 0.578174,
        },
    )

    assert trade.liquidity_score == 0.8125
    assert trade.quote_consistency_score == 0.91
    assert trade.quote_validation_status == "OK"
    assert getattr(trade, "raw_rank_score", None) == 0.746802
    assert getattr(trade, "terminal_rank_score", None) == 0.578174
