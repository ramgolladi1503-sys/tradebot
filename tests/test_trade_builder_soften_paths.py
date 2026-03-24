from __future__ import annotations

from core import orchestrator as orch
from strategies.trade_builder import TradeBuilder


def _market_data(symbol: str = "NIFTY") -> dict:
    return {
        "symbol": symbol,
        "execution_mode": "SIM",
        "market_context": {"execution_mode": "SIM", "market_open": False},
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
    assert cand["execution_status"] == "advisory_only"
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
    assert cand["execution_status"] == "advisory_only"


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
    assert ranked[0]["execution_status"] == "advisory_only"
