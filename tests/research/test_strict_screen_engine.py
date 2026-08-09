import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "scripts" / "research" / "hypothesis_factory"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


hf = load("hypothesis_factory", SCRIPT_DIR / "hypothesis_factory.py")
strict = load("strict_screen_engine", SCRIPT_DIR / "strict_screen_engine.py")


def rows():
    out = []
    for day in range(1, 5):
        base = 100 + day
        for bar in range(30):
            # Persistent trend would trigger overlapping breakout entries in the old screen.
            close = base + bar * 0.5
            out.append({
                "timestamp": f"2026-01-{day:02d}T09:{15+bar:02d}:00",
                "date": f"2026-01-{day:02d}",
                "instrument": "NIFTY",
                "open": str(close - 0.1),
                "high": str(close + 0.2),
                "low": str(close - 0.2),
                "close": str(close),
                "volume": "1000",
                "vwap": str(close - 0.1),
                "bid": str(close - 0.01),
                "ask": str(close + 0.01),
                "is_fallback": "false",
            })
    return out


def test_unsupported_exit_rule_fails_closed():
    h = hf.generate_hypotheses(instruments=["NIFTY"], families=["opening_range_breakout"], windows=[5])[1]
    assert h["exit_rule"] == "rr_1_5_or_time_stop"
    result = strict.evaluate_hypothesis_strict(h, rows(), hf.ScreenConfig(min_trades=1, cost_bps=0, max_hold_bars=6))
    assert result["status"] == "REJECTED"
    assert result["screen_rejection_reason"] == "UNSUPPORTED_EXIT_RULE"
    assert result["trades"] == 0
    assert result["option_pnl_claimed"] is False


def test_strict_engine_prevents_overlapping_positions():
    h = hf.generate_hypotheses(instruments=["NIFTY"], families=["opening_range_breakout"], windows=[5])[0]
    assert h["exit_rule"] == "time_stop"
    cfg = hf.ScreenConfig(min_trades=1, cost_bps=0, max_hold_bars=6)
    loose = hf.evaluate_hypothesis(h, rows(), cfg)
    strict_result = strict.evaluate_hypothesis_strict(h, rows(), cfg)
    assert strict_result["trades"] > 0
    assert strict_result["trades"] < loose["trades"]
    assert strict_result["overlapping_trades_allowed"] is False
    assert strict_result["sessions_traded"] > 0
    assert "max_drawdown_per_100_trades_bps" in strict_result
    assert "top_session_trade_share" in strict_result
    assert strict_result["runtime_authority"] == "NONE"
    assert strict_result["broker_actions_allowed"] is False
