from types import SimpleNamespace

from core.review_packet import build_review_packet, format_review_packet


def _candidate():
    return SimpleNamespace(
        strategy="TREND_BREAKOUT",
        symbol="NIFTY",
        side="BUY",
        entry_type="LIMIT",
        entry_price=102.5,
        stop_loss=98.0,
        target=109.0,
        qty=10,
        qty_units=10,
        qty_lots=1,
        max_loss=45.0,
        validity_sec=180,
        max_hold_sec=900,
        entry_reason="breakout_above_vwap",
        pattern_flags=["trend_confirmed", "volume_expansion"],
        trade_score_detail={"confluence": 0.82, "momentum": 0.76},
        reason_codes=["risk_checks_passed", "liquidity_ok"],
        quote_ok=True,
        opt_bid=102.4,
        opt_ask=102.6,
        open_interest=120000,
        volume=45000,
        regime="TREND",
    )


def _market():
    return {
        "symbol": "NIFTY",
        "regime": "TREND",
        "spread_pct": 0.00195,
        "volume": 45000,
        "oi": 120000,
        "vwap": 102.1,
        "trend_state": "UP",
        "vol_state": "NORMAL",
        "depth_imbalance": 0.21,
        "shock_score": 0.02,
    }


def test_review_packet_is_deterministic_for_fixed_input():
    candidate = _candidate()
    market_data = _market()
    risk_policy = {
        "position_sizing_cap": 20,
        "time_window_validity_sec": 180,
        "allow_reason": "risk_checks_passed",
    }
    packet_one = build_review_packet(candidate, market_data=market_data, risk_policy=risk_policy)
    packet_two = build_review_packet(candidate, market_data=market_data, risk_policy=risk_policy)
    assert packet_one == packet_two
    assert format_review_packet(packet_one) == format_review_packet(packet_two)


def test_review_packet_contains_required_sections_and_fields():
    packet = build_review_packet(
        _candidate(),
        market_data=_market(),
        risk_policy={"position_sizing_cap": 25, "time_window_validity_sec": 240, "allow_reason": "manual_review"},
    )
    assert "summary" in packet
    assert "risk" in packet
    assert "liquidity" in packet
    assert "context" in packet
    assert "guardrails" in packet
    assert packet["summary"]["strategy_name"] == "TREND_BREAKOUT"
    assert packet["summary"]["symbol"] == "NIFTY"
    assert packet["summary"]["direction"] == "BUY"
    assert packet["risk"]["max_loss"] > 0
    assert packet["liquidity"]["spread_pct"] >= 0
    assert packet["liquidity"]["oi"] > 0
    assert isinstance(packet["context"]["key_features_used"], dict)
    assert len(packet["context"]["top_reasons"]) <= 3
    assert packet["guardrails"]["position_sizing_cap"] == 25.0
    assert packet["guardrails"]["time_window_validity_sec"] == 240
    assert packet["guardrails"]["risk_policy_allow_reason"] == "manual_review"
