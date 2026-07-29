from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement.market_event_graph_reversal import (
    FROZEN_GRAPH,
    generate_market_event_graph_reversal_candidates,
)


def _regime() -> MovementRegimeResult:
    return MovementRegimeResult(
        schema_version=1,
        primary_regime="TREND_UP",
        scores={
            "TREND_UP": 0.6,
            "TREND_DOWN": 0.2,
            "VOLATILITY_EXPANSION": 0.4,
            "COMPRESSION": 0.2,
            "TRAP_RISK": 0.1,
            "CHOP": 0.1,
        },
    )


def _context(labels=FROZEN_GRAPH, *, now=1_000.0) -> StrategyContext:
    history = [
        {
            "event_label": label,
            "ts_epoch": now - (3 - index) * 60.0,
            "market_event_graph_entry_bar_ts_epoch": now,
            "market_event_graph_triplet_id": "820.000000|880.000000|940.000000",
            "breadth_down_1": 0.8 if label.endswith(":HIGH") else 0.1,
            "index_breadth_divergence": -0.001,
        }
        for index, label in enumerate(labels)
    ]
    return StrategyContext(
        symbol="NIFTY",
        ts_epoch=now,
        spot_ltp=24_500.0,
        vwap=24_480.0,
        option_ce_ltp=120.0,
        option_pe_ltp=105.0,
        ce_premium_change=2.0,
        pe_premium_change=-1.0,
        ce_spread_pct=0.01,
        pe_spread_pct=0.01,
        ce_depth=1_500.0,
        pe_depth=1_300.0,
        quote_source="realtime",
        fallback_used=False,
        option_ltp_age_sec=1.0,
        metadata={"market_event_graph_history": history},
    )


def test_emits_advisory_buy_call_for_exact_frozen_graph():
    candidates = generate_market_event_graph_reversal_candidates(_context(), _regime())
    assert tuple(candidate.direction for candidate in candidates) == ("BUY_CALL",)
    candidate = candidates[0]
    assert candidate.strategy_id == "market_event_graph_reversal_v1"
    assert candidate.lineage["promotion_state"] == "ADVISORY_ONLY"
    assert "no_auto_execution" in candidate.suppression_tags
    assert "SHADOW_ADVISORY_ONLY" in candidate.warnings
    assert candidate.evidence["observed_graph"] == list(FROZEN_GRAPH)
    assert candidate.evidence["allowed_for_live_execution"] is False
    assert candidate.evidence["is_order_action"] is False
    assert candidate.evidence["broker_api_called"] is False


def test_refuses_non_matching_graph():
    ctx = _context((
        "breadth_down_1:LOW",
        "index_breadth_divergence:LOW",
        "breadth_down_1:LOW",
    ))
    assert generate_market_event_graph_reversal_candidates(ctx, _regime()) == ()


def test_refuses_missing_breadth_evidence():
    ctx = StrategyContext(symbol="NIFTY", ts_epoch=1_000.0, metadata={})
    assert generate_market_event_graph_reversal_candidates(ctx, _regime()) == ()


def test_refuses_stale_event_graph():
    ctx = _context(now=10_000.0)
    stale = [dict(row, ts_epoch=1_000.0) for row in ctx.metadata["market_event_graph_history"]]
    ctx = StrategyContext(symbol="NIFTY", ts_epoch=10_000.0, metadata={"market_event_graph_history": stale})
    assert generate_market_event_graph_reversal_candidates(ctx, _regime()) == ()


def test_refuses_same_bar_before_delayed_entry_completes():
    ctx = _context(now=1_000.0)
    ctx.metadata["market_event_graph_history"][-1]["ts_epoch"] = 1_000.0
    ctx.metadata["market_event_graph_history"][-1]["market_event_graph_entry_bar_ts_epoch"] = 1_060.0
    assert generate_market_event_graph_reversal_candidates(ctx, _regime()) == ()


def test_refuses_duplicate_triplet_signal():
    ctx = _context(now=1_000.0)
    ctx.metadata["market_event_graph_emitted_triplet_ids"] = ["820.000000|880.000000|940.000000"]
    assert generate_market_event_graph_reversal_candidates(ctx, _regime()) == ()
