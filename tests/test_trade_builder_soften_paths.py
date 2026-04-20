from __future__ import annotations

from config import config as cfg
from core import orchestrator as orch
from strategies.trade_builder import TradeBuilder


def _market_data(symbol: str = "NIFTY") -> dict:
    return {
        "symbol": symbol,
        "ltp": 25000.0,
        "underlying_spot": 25000.0,
        "execution_mode": "SIM",
        "market_context": {"execution_mode": "SIM", "market_open": False},
        "option_chain": [
            {
                "type": "CE",
                "strike": 25000.0,
                "expiry": "2026-04-30",
                "tradingsymbol": "NIFTY26APR25000CE",
                "instrument_token": 900001,
                "ltp": 100.0,
                "bid": 99.5,
                "ask": 100.5,
            },
            {
                "type": "PE",
                "strike": 25000.0,
                "expiry": "2026-04-30",
                "tradingsymbol": "NIFTY26APR25000PE",
                "instrument_token": 900002,
                "ltp": 105.0,
                "bid": 104.5,
                "ask": 105.5,
            },
        ],
    }


def test_premium_band_fail_softens_to_candidate():
    tb = TradeBuilder()
    reject_ctx = {
        "symbol": "NIFTY",
        "reason": "no_viable_candidates",
        "gate_reasons": ["premium_band_fail"],
    }
    cand = tb._soften_reject_to_candidate(
        market_data=_market_data(),
        reject_ctx=reject_ctx,
        strategy_tag="CORE",
        direction="BUY_CALL",
    )

    assert cand is not None
    assert cand["reject_reason"] == "premium_band_fail"
    assert cand["execution_status"] == "scored"
    assert cand["candidate_status"] == "near_executable"
    assert cand["execution_entry_status"] == "non_executable"
    assert cand["rank_score"] is not None


def test_weak_momentum_softens_to_candidate():
    tb = TradeBuilder()
    reject_ctx = {
        "symbol": "NIFTY",
        "reason": "weak_momentum",
        "gate_reasons": ["weak_momentum"],
    }
    cand = tb._soften_reject_to_candidate(
        market_data=_market_data(),
        reject_ctx=reject_ctx,
        strategy_tag="ZERO_TO_HERO",
        direction="BUY_CALL",
    )

    assert cand is not None
    assert cand["reject_reason"] == "weak_momentum"
    assert cand["execution_status"] == "scored"
    assert cand["candidate_status"] == "near_executable"


def test_malformed_option_row_still_hard_fails():
    tb = TradeBuilder()
    reject_ctx = {
        "symbol": "NIFTY",
        "reason": "malformed_option_row",
        "gate_reasons": ["malformed_option_row"],
    }
    cand = tb._soften_reject_to_candidate(
        market_data=_market_data(),
        reject_ctx=reject_ctx,
        strategy_tag="CORE",
        direction="BUY_CALL",
    )

    assert cand is None


def test_softened_candidate_enters_ranked_pool():
    tb = TradeBuilder()
    reject_ctx = {
        "symbol": "NIFTY",
        "reason": "no_viable_candidates",
        "gate_reasons": ["spread_pct"],
    }
    cand = tb._soften_reject_to_candidate(
        market_data=_market_data(),
        reject_ctx=reject_ctx,
        strategy_tag="CORE",
        direction="BUY_CALL",
    )

    assert cand is not None
    ranked = orch._consume_trade_builder_ranked_candidates(tb)
    assert len(ranked) > 0
    assert ranked[0]["execution_status"] == "scored"


def test_no_signal_soften_builds_borderline_candidate():
    tb = TradeBuilder()
    cand = tb._soften_reject_to_candidate(
        market_data=_market_data(),
        reject_ctx={"symbol": "NIFTY", "reason": "no_signal", "gate_reasons": ["no_signal"]},
        strategy_tag="CORE",
        direction="BUY_CALL",
    )
    assert cand is not None
    assert cand["execution_status"] == "advisory_only"
    assert cand["candidate_status"] == "advisory_only"
    assert cand["eligible_for_execution"] is False
    assert cand["execution_blocked"] is False
    assert cand["execution_block_reason"] is None
    assert cand["rank_score"] is None
    assert cand["score_origin"] == "soft_reject_seed"


def test_no_signal_softened_candidate_does_not_enter_ranked_pool():
    tb = TradeBuilder()
    _ = tb._soften_reject_to_candidate(
        market_data=_market_data(),
        reject_ctx={"symbol": "NIFTY", "reason": "no_signal", "gate_reasons": ["no_signal"]},
        strategy_tag="CORE",
        direction="BUY_CALL",
    )
    ranked = orch._consume_trade_builder_ranked_candidates(tb)
    assert ranked == []


def test_live_no_signal_without_live_fallback_returns_none_and_skips_borderline(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False, raising=False)
    monkeypatch.setattr(cfg, "LIVE_NO_SIGNAL_FALLBACK_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "LIVE_ALLOW_WEAK_SIGNAL_BORDERLINE_CANDIDATE", False, raising=False)
    monkeypatch.setattr(tb, "_signal_for_symbol", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tb, "_resolve_index_bid_ask", lambda md, _mode: dict(md, quote_ok=True, bid=1.0, ask=1.1))
    monkeypatch.setattr(tb, "_resolve_underlying_spot", lambda *_args, **_kwargs: (25000.0, "live", True, None))
    monkeypatch.setattr(tb, "_reject_exit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tb, "_log_blocked_candidate", lambda *_args, **_kwargs: None)

    trade = tb.build(
        {
            **_market_data(),
            "execution_mode": "LIVE",
            "market_context": {"execution_mode": "LIVE", "market_open": True},
            "market_open": True,
            "chain_source": "live",
            "quote_ok": True,
            "bid": 1.0,
            "ask": 1.1,
        }
    )

    assert trade is None
    ranked = orch._consume_trade_builder_ranked_candidates(tb)
    assert ranked == []


def test_borderline_candidate_not_marked_execution_blocked():
    tb = TradeBuilder()
    cand = tb._build_borderline_candidate(
        market_data=_market_data(),
        reason="weak_signal",
        confidence=0.19,
        strategy_tag="CORE",
        direction="BUY_CALL",
    )
    assert cand is not None
    assert cand["execution_status"] == "advisory_only"
    assert cand["candidate_status"] == "advisory_only"
    assert cand["execution_allowed"] is False
    assert cand["execution_blocked"] is False
    assert cand["execution_block_reason"] is None
    assert cand["rank_score"] is None


def test_borderline_candidate_resolves_contract_from_chain():
    tb = TradeBuilder()
    md = _market_data()
    md.update(
        {
            "ltp": 25010.0,
            "underlying_spot": 25010.0,
            "option_chain": [
                {
                    "type": "CE",
                    "strike": 25000.0,
                    "expiry": "2026-04-30",
                    "tradingsymbol": "NIFTY26APR25000CE",
                    "instrument_token": 987654,
                    "ltp": 110.0,
                    "bid": 109.5,
                    "ask": 110.5,
                }
            ],
        }
    )
    cand = tb._build_borderline_candidate(
        market_data=md,
        reason="weak_signal",
        confidence=0.2,
        strategy_tag="CORE",
        direction="BUY_CALL",
    )
    assert cand is not None
    assert cand.get("instrument_token") == 987654
    assert cand.get("tradingsymbol") == "NIFTY26APR25000CE"
    assert cand.get("expiry") == "2026-04-30"
    assert cand.get("unresolved_contract") is False
    assert cand["execution_status"] == "advisory_only"
    assert cand["candidate_status"] == "advisory_only"
    assert cand["rank_score"] is None


def test_borderline_candidate_downgrades_when_contract_unresolved(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(tb, "_resolve_expiry_for_symbol", lambda *_args, **_kwargs: "2026-04-30")
    monkeypatch.setattr(
        tb,
        "_resolve_option_contract",
        lambda *_args, **_kwargs: {
            "expiry": "2026-04-30",
            "expiry_date": "2026-04-30",
            "tradingsymbol": None,
            "instrument_token": None,
            "instrument_id": None,
        },
    )
    md = _market_data()
    md.update({"ltp": 25010.0, "underlying_spot": 25010.0, "option_chain": []})
    cand = tb._build_borderline_candidate(
        market_data=md,
        reason="weak_signal",
        confidence=0.2,
        strategy_tag="CORE",
        direction="BUY_CALL",
    )
    assert cand is not None
    assert cand.get("unresolved_contract") is True
    assert cand["execution_status"] == "advisory_only"
    assert cand["candidate_status"] == "advisory_only"
    assert cand["eligible_for_execution"] is False
    assert cand["execution_block_reason"] == "unresolved_contract"


def test_soften_reject_disabled_in_strict_mode(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", True, raising=False)
    tb = TradeBuilder()
    cand = tb._soften_reject_to_candidate(
        market_data=_market_data(),
        reject_ctx={"symbol": "NIFTY", "reason": "weak_momentum", "gate_reasons": ["weak_momentum"]},
        strategy_tag="CORE",
        direction="BUY_CALL",
    )
    assert cand is None


def test_borderline_candidate_disabled_in_strict_mode(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", True, raising=False)
    tb = TradeBuilder()
    cand = tb._build_borderline_candidate(
        market_data=_market_data(),
        reason="weak_signal",
        confidence=0.2,
        strategy_tag="CORE",
        direction="BUY_CALL",
    )
    assert cand is None
