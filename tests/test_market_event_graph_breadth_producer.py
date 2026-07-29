from core.market_event_graph_breadth_producer import (
    attach_completed_constituent_breadth_snapshots,
    produce_completed_constituent_breadth_snapshots,
)
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement.market_event_graph_reversal import (
    generate_market_event_graph_reversal_candidates,
)


def _returns(negative_count: int, total: int = 50, value: float = 0.001):
    return [-value] * negative_count + [value] * (total - negative_count)


def _metadata():
    return {
        "market_event_graph_thresholds": {
            "breadth_high": 0.70,
            "breadth_low": 0.30,
            "divergence_low": -0.002,
            "min_constituents": 40,
        },
        "completed_constituent_bars": [
            {"ts_epoch": 100.0, "index_ret1": -0.001, "constituent_ret1": _returns(40), "completed": True},
            {"ts_epoch": 160.0, "index_ret1": -0.004, "constituent_ret1": _returns(25), "completed": True},
            {"ts_epoch": 220.0, "index_ret1": 0.001, "constituent_ret1": _returns(10), "completed": True},
        ],
    }


def _regime():
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


def test_produces_exact_consecutive_causal_graph_from_completed_returns():
    rows = produce_completed_constituent_breadth_snapshots(_metadata())
    assert tuple(row["event_label"] for row in rows) == (
        "breadth_down_1:HIGH",
        "index_breadth_divergence:LOW",
        "breadth_down_1:LOW",
    )
    assert tuple(row["ts_epoch"] for row in rows) == (100.0, 160.0, 220.0)
    assert tuple(row["participation_count"] for row in rows) == (50, 50, 50)


def test_does_not_match_open_ended_sequence_with_intervening_row():
    metadata = _metadata()
    metadata["completed_constituent_bars"] = [
        metadata["completed_constituent_bars"][0],
        {"ts_epoch": 130.0, "index_ret1": 0.001, "constituent_ret1": _returns(25), "completed": True},
        metadata["completed_constituent_bars"][1],
        metadata["completed_constituent_bars"][2],
    ]
    assert produce_completed_constituent_breadth_snapshots(metadata) == []


def test_fails_closed_without_frozen_thresholds_or_sufficient_coverage():
    assert produce_completed_constituent_breadth_snapshots({"completed_constituent_bars": []}) == []
    metadata = _metadata()
    metadata["completed_constituent_bars"][0]["constituent_ret1"] = _returns(10, total=20)
    assert produce_completed_constituent_breadth_snapshots(metadata) == []


def test_incomplete_bar_breaks_consecutive_graph_and_reports_invalid():
    metadata = _metadata()
    metadata["completed_constituent_bars"][1]["completed"] = False
    enriched = attach_completed_constituent_breadth_snapshots(metadata)
    assert enriched["constituent_breadth_producer_status"] == "MISSING_OR_INVALID"
    assert enriched["constituent_breadth_event_count"] == 0
    assert "completed_constituent_breadth_snapshots" not in enriched


def test_strategy_can_emit_from_raw_completed_constituent_bars():
    ctx = StrategyContext(
        symbol="NIFTY",
        ts_epoch=220.0,
        option_ce_ltp=120.0,
        option_pe_ltp=105.0,
        ce_premium_change=2.0,
        pe_premium_change=-1.0,
        ce_spread_pct=0.01,
        pe_spread_pct=0.01,
        ce_depth=1500.0,
        pe_depth=1300.0,
        quote_source="realtime",
        fallback_used=False,
        option_ltp_age_sec=1.0,
        metadata=_metadata(),
    )
    candidates = generate_market_event_graph_reversal_candidates(ctx, _regime())
    assert tuple(candidate.direction for candidate in candidates) == ("BUY_CALL",)
    assert candidates[0].lineage["promotion_state"] == "ADVISORY_ONLY"


def test_strategy_does_not_emit_when_graph_has_a_gap():
    metadata = _metadata()
    metadata["completed_constituent_bars"].insert(
        1,
        {"ts_epoch": 130.0, "index_ret1": 0.001, "constituent_ret1": _returns(25), "completed": True},
    )
    ctx = StrategyContext(
        symbol="NIFTY",
        ts_epoch=220.0,
        option_ce_ltp=120.0,
        option_pe_ltp=105.0,
        ce_premium_change=2.0,
        pe_premium_change=-1.0,
        ce_spread_pct=0.01,
        pe_spread_pct=0.01,
        ce_depth=1500.0,
        pe_depth=1300.0,
        quote_source="realtime",
        fallback_used=False,
        option_ltp_age_sec=1.0,
        metadata=metadata,
    )
    assert generate_market_event_graph_reversal_candidates(ctx, _regime()) == ()
