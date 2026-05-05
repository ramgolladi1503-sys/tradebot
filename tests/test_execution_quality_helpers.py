from __future__ import annotations

from config import config as cfg
from core.execution_quality import evaluate_pretrade_execution_quality
from core.opportunity_engine import annotate_ranked_opportunities
from core.slippage_model import estimate_slippage


def _candidate(
    *,
    trade_id: str,
    bid: float,
    ask: float,
    execution_entry: float | None,
    execution_entry_status: str,
    volume: float,
    qty: int,
    confidence: float = 0.78,
    symbol: str = "NIFTY",
) -> dict:
    return {
        "trade_id": trade_id,
        "symbol": symbol,
        "strategy": "UNIT",
        "side": "BUY",
        "confidence": confidence,
        "builder_confidence": confidence,
        "permission_confidence": confidence,
        "gating_final_confidence": confidence,
        "sizing_confluence_score": confidence,
        "execution_allowed": True,
        "tradable": True,
        "best_bid": bid,
        "best_ask": ask,
        "opt_bid": bid,
        "opt_ask": ask,
        "current_ltp": (bid + ask) / 2.0,
        "opt_ltp": (bid + ask) / 2.0,
        "volume": volume,
        "qty": qty,
        "execution_entry": execution_entry,
        "execution_entry_status": execution_entry_status,
        "display_entry": execution_entry if execution_entry is not None else (bid + ask) / 2.0,
        "display_entry_status": "displayable",
        "quote_ok": True,
    }


def test_wider_spread_implies_higher_estimated_slippage():
    tight = estimate_slippage(
        side="BUY",
        bid=100.0,
        ask=100.1,
        execution_entry=100.1,
        qty=10,
        volume=10000,
    )
    wide = estimate_slippage(
        side="BUY",
        bid=100.0,
        ask=101.5,
        execution_entry=101.5,
        qty=10,
        volume=10000,
    )

    assert wide.expected_slippage > tight.expected_slippage
    assert (wide.expected_slippage_bps or 0.0) > (tight.expected_slippage_bps or 0.0)


def test_illiquid_candidate_is_rejected_and_not_selected_for_execution(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_QUALITY_MAX_SLIPPAGE_BPS", 25.0, raising=False)
    candidate = _candidate(
        trade_id="T-ILLIQUID",
        bid=100.0,
        ask=104.5,
        execution_entry=104.5,
        execution_entry_status="executable",
        volume=40,
        qty=150,
    )

    quality = evaluate_pretrade_execution_quality(candidate)
    ranked = annotate_ranked_opportunities([candidate], scope="unit:execution_quality", top_n=1)

    assert quality.execution_ok is False
    assert quality.order_policy == "reject"
    assert ranked[0]["selected_for_execution"] is False


def test_tight_spread_liquid_candidate_remains_executable():
    candidate = _candidate(
        trade_id="T-LIQUID",
        bid=100.0,
        ask=100.08,
        execution_entry=100.08,
        execution_entry_status="executable",
        volume=25000,
        qty=5,
        confidence=0.82,
    )

    quality = evaluate_pretrade_execution_quality(candidate)
    ranked = annotate_ranked_opportunities([candidate], scope="unit:execution_quality", top_n=1)

    assert quality.execution_ok is True
    assert quality.order_policy in {"market", "limit"}
    assert 0.0 <= float(quality.slippage_risk or 0.0) <= 1.0
    assert 0.0 <= float(quality.depth_score or 0.0) <= 1.0
    assert 0.0 <= float(quality.fill_probability or 0.0) <= 1.0
    assert 0.0 <= float(quality.execution_quality_score or 0.0) <= 1.0
    assert ranked[0]["executable_price_estimate"] is not None


def test_execution_quality_components_favor_liquid_over_illiquid():
    liquid = _candidate(
        trade_id="T-LIQ-GOOD",
        bid=100.0,
        ask=100.05,
        execution_entry=100.05,
        execution_entry_status="executable",
        volume=25000,
        qty=5,
        confidence=0.80,
    )
    illiquid = _candidate(
        trade_id="T-LIQ-BAD",
        bid=100.0,
        ask=103.5,
        execution_entry=103.5,
        execution_entry_status="executable",
        volume=50,
        qty=150,
        confidence=0.80,
    )

    liquid_quality = evaluate_pretrade_execution_quality(liquid)
    illiquid_quality = evaluate_pretrade_execution_quality(illiquid)

    assert float(liquid_quality.spread_penalty) < float(illiquid_quality.spread_penalty)
    assert float(liquid_quality.slippage_risk or 0.0) < float(illiquid_quality.slippage_risk or 1.0)
    assert float(liquid_quality.depth_score or 0.0) > float(illiquid_quality.depth_score or 0.0)
    assert float(liquid_quality.fill_probability or 0.0) > float(illiquid_quality.fill_probability or 0.0)
    assert float(liquid_quality.execution_quality_score or 0.0) > float(illiquid_quality.execution_quality_score or 0.0)
    assert float(liquid_quality.liquidity_quality or 0.0) > float(illiquid_quality.liquidity_quality or 0.0)
