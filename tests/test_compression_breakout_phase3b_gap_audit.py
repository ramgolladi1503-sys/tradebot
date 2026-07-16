from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.orchestrator import _strategy_context_snapshot_metadata
from core.ranking_orchestrator import build_ranked_opportunity_report
from core.runtime_snapshot_producer import _strategy_context_from_market_symbol
from strategies.movement.compression_breakout import generate_compression_breakout_candidates
from tests.test_candidate_phase2_ownership import _full_context, _regime


IST = ZoneInfo("Asia/Kolkata")


def _completed_history() -> list[dict[str, object]]:
    start = datetime(2026, 7, 14, 9, 15, tzinfo=IST)
    closes = (22590.0, 22630.0, 22615.0, 22635.0)
    bars: list[dict[str, object]] = []
    for index, close in enumerate(closes):
        bar_start = start + timedelta(minutes=index)
        bar_end = bar_start + timedelta(minutes=1)
        bars.append(
            {
                "symbol": "NIFTY",
                "session_date": "2026-07-14",
                "timeframe": "1m",
                "bar_start_timestamp": bar_start.isoformat(),
                "bar_end_timestamp": bar_end.isoformat(),
                "open": close - 5.0,
                "high": close + 10.0,
                "low": close - 10.0,
                "close": close,
                "volume": 1000.0 + (index * 100.0),
                "source": "unit_test",
                "source_timestamp": bar_end.isoformat(),
                "receipt_timestamp": (bar_end + timedelta(seconds=1)).isoformat(),
                "is_complete": True,
            }
        )
    return bars


def _runtime_market_data(*, range_width_pct: float | None) -> dict[str, object]:
    return {
        "symbol": "NIFTY",
        "spot": 22620.0,
        "ltp": 22620.0,
        "prev_ltp": 22590.0,
        "open_price": 22500.0,
        "vwap": 22540.0,
        "atr": 70.0,
        "atr_short": 35.0,
        "atr_long": 100.0,
        "volume_z": 1.5,
        "vwap_slope": 0.03,
        "day_high": 22620.0,
        "day_low": 22460.0,
        "nearest_support": 22590.0,
        "nearest_resistance": 22600.0,
        "orb_high": 22600.0,
        "orb_low": 22460.0,
        "range_width_pct": range_width_pct,
        "option_ce_ltp": 120.0,
        "option_pe_ltp": 90.0,
        "ce_premium_change": 12.0,
        "pe_premium_change": 0.0,
        "ce_spread_pct": 0.8,
        "pe_spread_pct": 0.8,
        "ce_depth": 1200.0,
        "pe_depth": 1200.0,
        "option_ltp_age_sec": 0.4,
        "quote_source": "live_option_tick",
        "fallback_used": False,
        "minutes_since_open": 35,
        "minutes_to_close": 280,
        "completed_bar_history": _completed_history(),
    }


def _fingerprint(report) -> list[tuple[str, float, str, str]]:
    return [
        (candidate.strategy_id, round(candidate.raw_score, 6), candidate.direction, candidate.status)
        for candidate in report.candidate_pool.candidates
        if candidate.direction in {"BUY_CALL", "BUY_PUT"}
    ]


def _runtime_context(*, range_width_pct: float | None):
    market_data = _runtime_market_data(range_width_pct=range_width_pct)
    market_data["metadata"] = _strategy_context_snapshot_metadata(market_data)
    return _strategy_context_from_market_symbol("NIFTY", market_data)


def test_compression_breakout_runtime_path_blocks_when_range_width_is_missing():
    runtime_ctx = _runtime_context(range_width_pct=None)
    report = build_ranked_opportunity_report(
        runtime_ctx,
        _regime(),
        candidate_generators=(generate_compression_breakout_candidates,),
        include_no_trade_candidate=False,
    )

    assert runtime_ctx.range_width_pct is None
    assert runtime_ctx.metadata["strategy_context_missing"]["range_width_pct"]["status"] == "MISSING_SOURCE"
    assert report.candidate_pool.candidates == ()
    assert report.candidate_pool.candidate_count == 0
    assert report.ranked_candidate_count == 0
    assert report.top_rank_strategy_id is None


def test_compression_breakout_runtime_path_matches_direct_fingerprint_when_truth_is_present():
    direct_report = build_ranked_opportunity_report(
        _full_context(),
        _regime(),
        candidate_generators=(generate_compression_breakout_candidates,),
        include_no_trade_candidate=False,
    )
    runtime_report = build_ranked_opportunity_report(
        _runtime_context(range_width_pct=0.14),
        _regime(),
        candidate_generators=(generate_compression_breakout_candidates,),
        include_no_trade_candidate=False,
    )

    assert _fingerprint(direct_report) == [
        ("compression_breakout_v1", 0.470676, "BUY_CALL", "VALIDATED_CANDIDATE"),
    ]
    assert _fingerprint(runtime_report) == _fingerprint(direct_report)
    assert runtime_report.top_rank_strategy_id == "compression_breakout_v1"
    assert runtime_report.ranked_candidate_count == 1
