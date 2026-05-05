import pytest

from strategies.pro_layer.alpha_validation import require_promotable_alpha, validate_alpha_edge
from strategies.pro_layer.pro_decision_adapter import best_pro_strategy_decision
from strategies.pro_layer.pro_strategy_engine import ProStrategyEngine


def test_alpha_validation_blocks_insufficient_sample():
    rows = [{"strategy": "vol_expansion", "r_multiple": 1.0} for _ in range(5)]
    report = validate_alpha_edge(rows, strategy="vol_expansion", min_trades=30)
    assert report.status == "INSUFFICIENT_DATA"
    assert "insufficient_sample_size" in report.reasons


def test_alpha_validation_promotes_positive_expectancy():
    rows = []
    rows += [{"strategy": "vol_expansion", "r_multiple": 1.0} for _ in range(22)]
    rows += [{"strategy": "vol_expansion", "r_multiple": -0.5} for _ in range(8)]
    report = validate_alpha_edge(rows, strategy="vol_expansion", min_trades=30)
    assert report.status == "PROMOTE"
    assert report.expectancy_r > 0
    assert report.profit_factor > 1.15


def test_alpha_validation_rejects_negative_expectancy():
    rows = []
    rows += [{"strategy": "vol_expansion", "r_multiple": 0.4} for _ in range(10)]
    rows += [{"strategy": "vol_expansion", "r_multiple": -1.0} for _ in range(20)]
    report = validate_alpha_edge(rows, strategy="vol_expansion", min_trades=30)
    assert report.status == "PAPER_ONLY"
    assert "expectancy_below_threshold" in report.reasons


def test_require_promotable_alpha_raises_for_bad_edge():
    rows = [{"strategy": "x", "r_multiple": -1.0} for _ in range(30)]
    with pytest.raises(RuntimeError):
        require_promotable_alpha(rows, strategy="x", min_trades=30)


def test_pro_engine_conflict_filter_rejects_balanced_conflict():
    engine = ProStrategyEngine()
    market_data = {
        "regime": "VOLATILE",
        "atr": 10,
        "ltp_change_window": 9,
        "vol_z": 1.0,
        "bid_qty": 1000,
        "ask_qty": 3000,
        "spread_pct": 0.01,
    }
    signals = engine.run(market_data)
    assert signals == []


def test_pro_decision_adapter_returns_ranked_decision_when_market_data_clean():
    decision = best_pro_strategy_decision(
        {
            "symbol": "NIFTY",
            "regime": "TREND",
            "atr": 10,
            "ltp_change_window": 12,
            "vol_z": 2.0,
            "quote_ok": True,
            "liquidity_ok": True,
            "spread_ok": True,
            "execution_allowed": True,
            "tradable": True,
            "quote_age_sec": 0.3,
            "spread_pct": 0.005,
            "best_bid": 100,
            "best_ask": 101,
            "ltp": 100,
            "entry_price": 100,
            "execution_entry": 100,
            "stop_loss": 90,
            "target": 120,
            "volume": 100000,
            "data_confidence": 1.0,
        }
    )
    assert decision is not None
    assert decision["source_flags"]["strategy_layer"] == "pro"
    assert float(decision.get("final_score") or 0) > 0
