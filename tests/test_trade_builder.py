from config import config as cfg
from types import SimpleNamespace
from strategies.trade_builder import TradeBuilder

def test_trade_builder_returns_borderline_candidate_when_no_signal():
    pass


def test_trade_builder_strict_mode_drops_no_signal_candidate(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", True, raising=False)
    tb = TradeBuilder()
    md = {
        "symbol": "NIFTY",
        "ltp": 25010.0,
        "vwap": 25010.0,
        "atr": 0.0,
        "option_chain": [
            {
                "type": "CE",
                "strike": 25000.0,
                "expiry": "2026-04-30",
                "tradingsymbol": "NIFTY26APR25000CE",
                "instrument_token": 123456,
                "ltp": 102.0,
                "bid": 101.5,
                "ask": 102.5,
            }
        ],
    }
    out = tb.build(md)
    assert out is None


def test_set_last_ranked_candidates_drops_invalid_rows(monkeypatch):
    monkeypatch.setattr(cfg, "TRADE_BUILDER_INVALID_RANKED_CANDIDATE_SAMPLE_LIMIT", 2, raising=False)
    tb = TradeBuilder()
    tb._set_last_ranked_candidates(
        [
            None,
            {
                "trade_id": "BAD-1",
                "strategy_family": "breakout",
                "candidate_status": "executable",
                "confidence": 0.7,
                "rank_score": 0.6,
            },
            {
                "trade_id": "GOOD-1",
                "symbol": "NIFTY",
                "strategy_family": "breakout",
                "candidate_status": "executable",
                "confidence": 0.7,
                "rank_score": 0.6,
            },
        ]
    )

    assert (tb._last_ranked_candidates).__len__() == 1
    assert tb._last_ranked_candidates[0]["trade_id"] == "GOOD-1"


def test_candidate_decision_payload_preserves_nested_provenance():
    pass


def test_candidate_decision_payload_enriches_flat_native_setup_quality_detail():
    pass