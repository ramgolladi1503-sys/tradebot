from core.execution_engine import ExecutionEngine
from core.trade_scoring import compute_trade_score


def test_adaptive_limit_price_spread_increases_buy_limit():
    engine = ExecutionEngine()
    engine.slippage_bps = 0
    limit_low, _ = engine.adaptive_limit_price(
        "BUY", bid=100, ask=101, spread_pct=0.005, depth_imbalance=0.0, vol_z=0.0
    )
    limit_high, _ = engine.adaptive_limit_price(
        "BUY", bid=100, ask=101, spread_pct=0.02, depth_imbalance=0.0, vol_z=0.0
    )
    assert limit_high >= limit_low


def test_exec_quality_blocks_score():
    md = {
        "ltp": 100,
        "vwap": 100,
        "regime": "TREND",
        "primary_regime": "TREND",
        "regime_probs": {"TREND": 0.9},
        "regime_entropy": 0.1,
        "execution_quality_score": 0.0,
        "shock_score": 0.0,
        "uncertainty_index": 0.0,
    }
    opt = {"strike": 100, "type": "CE"}
    res = compute_trade_score(md, opt, direction="BUY_CALL", rr=2.0, strategy_name="TEST")
    assert res["score"] == 0.0
    assert "exec_quality_block" in res["issues"]
