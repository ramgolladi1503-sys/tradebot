import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "research" / "hypothesis_factory" / "hypothesis_factory.py"
spec = importlib.util.spec_from_file_location("hypothesis_factory", MODULE_PATH)
hf = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = hf
spec.loader.exec_module(hf)


def _rows(fallback=False):
    rows = []
    for day in range(1, 31):
        base = 100 + day
        for bar in range(12):
            close = base + bar * 0.4
            rows.append({
                "timestamp": f"2026-01-{day:02d}T09:{15+bar:02d}:00",
                "date": f"2026-01-{day:02d}",
                "instrument": "NIFTY",
                "open": str(close - 0.1),
                "high": str(close + 0.2),
                "low": str(close - 0.2),
                "close": str(close),
                "volume": str(1000 + bar * 100),
                "vwap": str(close - 0.1),
                "bid": str(close - 0.01),
                "ask": str(close + 0.01),
                "is_fallback": "true" if fallback else "false",
            })
    return rows


def test_generate_hypotheses_is_deterministic_and_safe():
    first = hf.generate_hypotheses(instruments=["NIFTY"], families=["opening_range_breakout"], windows=[5])
    second = hf.generate_hypotheses(instruments=["NIFTY"], families=["opening_range_breakout"], windows=[5])
    assert first == second
    assert len(first) == 16
    assert all(h["runtime_authority"] == "NONE" for h in first)
    assert all(h["broker_actions_allowed"] is False for h in first)


def test_fallback_rows_do_not_create_screen_trades():
    h = hf.generate_hypotheses(instruments=["NIFTY"], families=["opening_range_breakout"], windows=[5])[0]
    clean = hf.evaluate_hypothesis(h, _rows(False), hf.ScreenConfig(min_trades=1, cost_bps=0))
    fallback = hf.evaluate_hypothesis(h, _rows(True), hf.ScreenConfig(min_trades=1, cost_bps=0))
    assert clean["trades"] > 0
    assert fallback["trades"] == 0
    assert fallback["fallback_execution_data_used"] is False


def test_screen_outputs_not_certified_and_passport_blocks_integration():
    hypotheses = hf.generate_hypotheses(instruments=["NIFTY"], families=["opening_range_breakout"], windows=[5])
    results = hf.screen_hypotheses(hypotheses, _rows(False), hf.ScreenConfig(min_trades=1, cost_bps=0))
    assert results
    passport = hf.make_passport(hypotheses[0], results[0])
    assert passport["certification"] == "NOT_CERTIFIED"
    assert passport["integration"]["allowed_tradebot_mode"] == "RESEARCH_ONLY"
    assert passport["integration"]["broker_actions_allowed"] is False
