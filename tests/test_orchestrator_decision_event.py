from types import SimpleNamespace

from core.orchestrator import Orchestrator


def test_build_decision_event_includes_shadow_fields():
    orch = Orchestrator.__new__(Orchestrator)
    orch.portfolio = {
        "capital": 100000.0,
        "equity_high": 102000.0,
        "daily_pnl": 1200.0,
        "daily_pnl_pct": 0.0117647059,
        "open_risk": 500.0,
        "open_risk_pct": 0.0049019607,
    }
    orch.loss_streak = {"NIFTY": 1}
    orch.risk_state = SimpleNamespace(daily_max_drawdown=0.02)
    orch._open_risk = lambda: 500.0

    trade = SimpleNamespace(
        trade_id="NIFTY-25600-CE-123",
        symbol="NIFTY",
        strategy="TEST_STRAT",
        regime="TREND",
        side="BUY",
        instrument="OPT",
        instrument_type="OPT",
        expiry="2026-02-12",
        strike=25600,
        option_type="CE",
        right="CE",
        qty_lots=1,
        qty_units=50,
        instrument_token=111,
        model_type="xgb",
        confidence=0.71,
        shadow_confidence=0.66,
        alpha_confidence=0.69,
        alpha_uncertainty=0.12,
        model_version="champ_xgb_v2",
        shadow_model_version="chall_xgb_v3",
    )
    market_data = {
        "symbol": "NIFTY",
        "regime": "TREND",
        "regime_probs": {"TREND": 0.7, "RANGE": 0.3},
        "shock_score": 0.1,
        "depth_imbalance": 0.05,
        "option_chain": [
            {
                "instrument_token": 111,
                "strike": 25600,
                "type": "CE",
                "ltp": 145.0,
                "bid": 144.5,
                "ask": 145.5,
                "bid_qty": 200,
                "ask_qty": 220,
            }
        ],
    }

    event = orch._build_decision_event(trade, market_data, gatekeeper_allowed=True, veto_reasons=[])

    assert event["champion_proba"] == 0.71
    assert event["challenger_proba"] == 0.66
    assert event["champion_model_id"] == "champ_xgb_v2"
    assert event["challenger_model_id"] == "chall_xgb_v3"
    assert event["xgb_proba"] == 0.71
    assert event["instrument_id"] is not None
    assert event["instrument_type"] == "OPT"
    assert event["right"] == "CE"
    assert event["qty_lots"] == 1
    assert event["qty_units"] == 50
    assert event["quote_age_sec"] is not None
