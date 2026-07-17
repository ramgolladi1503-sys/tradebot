from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from core.runtime_snapshot_producer import _strategy_context_from_market_symbol
from strategies.movement.vwap_reclaim import generate_vwap_reclaim_rejection_candidates


IST = ZoneInfo("Asia/Kolkata")


def _regime(*, primary: str = "TREND_UP", **scores: float) -> MovementRegimeResult:
    base = {
        "TREND_UP": 0.0,
        "TREND_DOWN": 0.0,
        "RANGE": 0.0,
        "CHOP": 0.0,
        "COMPRESSION": 0.0,
        "VOLATILITY_EXPANSION": 0.0,
        "TRAP_RISK": 0.0,
        "EXHAUSTION_RISK": 0.0,
        "EXPIRY_CONTEXT": 0.0,
        "INCONCLUSIVE": 0.0,
    }
    base.update(scores)
    return MovementRegimeResult(schema_version=1, primary_regime=primary, scores=base)


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


def _fingerprint(candidates):
    return [
        (
            candidate.strategy_id,
            round(float(candidate.raw_score), 6),
            candidate.direction,
            candidate.status,
            candidate.entry_trigger,
            candidate.invalid_if,
            candidate.rank_reason,
        )
        for candidate in candidates
    ]


def _direct_context(*, include_history: bool = False) -> StrategyContext:
    payload = {
        "symbol": "NIFTY",
        "ts_epoch": 1721028600.0,
        "spot_ltp": 22610.0,
        "vwap": 22540.0,
        "vwap_slope": 0.04,
        "day_high": 22680.0,
        "day_low": 22480.0,
        "orb_high": 22660.0,
        "orb_low": 22490.0,
        "nearest_resistance": 22670.0,
        "nearest_support": 22580.0,
        "range_width_pct": 0.45,
        "volume_z": 1.2,
        "option_ce_ltp": 125.0,
        "option_pe_ltp": 92.0,
        "ce_premium_change": 10.0,
        "pe_premium_change": 0.0,
        "ce_spread_pct": 0.8,
        "pe_spread_pct": 0.8,
        "ce_depth": 1200.0,
        "pe_depth": 1200.0,
        "option_ltp_age_sec": 0.4,
        "quote_source": "live_option_tick",
        "fallback_used": False,
        "minutes_since_open": 65,
        "metadata": {"previous_spot_ltp": 22535.0, "vwap_reclaim_up_confirmed": True},
    }
    if include_history:
        payload["completed_bar_history"] = _completed_history()
    return StrategyContext(**payload)


def _runtime_context() -> StrategyContext:
    return _strategy_context_from_market_symbol(
        "NIFTY",
        {
            "spot": 22610.0,
            "ltp": 22610.0,
            "metadata": {
                "previous_spot_ltp": 22535.0,
                "vwap_reclaim_up_confirmed": True,
                "strategy_context_truth": {
                    "vwap": 22540.0,
                    "vwap_slope": 0.04,
                    "day_high": 22680.0,
                    "day_low": 22480.0,
                    "orb_high": 22660.0,
                    "orb_low": 22490.0,
                    "nearest_resistance": 22670.0,
                    "nearest_support": 22580.0,
                    "range_width_pct": 0.45,
                    "volume_z": 1.2,
                    "option_ce_ltp": 125.0,
                    "option_pe_ltp": 92.0,
                    "ce_premium_change": 10.0,
                    "pe_premium_change": 0.0,
                    "ce_spread_pct": 0.8,
                    "pe_spread_pct": 0.8,
                    "ce_depth": 1200.0,
                    "pe_depth": 1200.0,
                    "option_ltp_age_sec": 0.4,
                    "quote_source": "live_option_tick",
                    "fallback_used": False,
                    "minutes_since_open": 65,
                },
                "strategy_context_provenance": {"vwap": {"source_field": "vwap"}},
                "strategy_context_missing": {},
            },
        },
    )


def test_vwap_reclaim_runtime_and_direct_fingerprints_match_for_truthful_snapshot():
    regime = _regime(TREND_UP=0.6, CHOP=0.1)

    runtime = _runtime_context()
    direct = _direct_context()

    runtime_candidates = generate_vwap_reclaim_rejection_candidates(runtime, regime)
    direct_candidates = generate_vwap_reclaim_rejection_candidates(direct, regime)

    assert runtime.metadata["previous_spot_ltp"] == 22535.0
    assert _fingerprint(runtime_candidates) == _fingerprint(direct_candidates)
    assert _fingerprint(runtime_candidates) == [
        (
            "vwap_reclaim_rejection_v1",
            0.392377,
            "BUY_CALL",
            "RAW_CANDIDATE",
            "confirmed_vwap_reclaim_or_rejection",
            "price_crosses_back_through_vwap",
            "confirmed VWAP reclaim/rejection in a non-chop regime",
        )
    ]


def test_vwap_reclaim_completed_history_does_not_change_the_current_contract():
    regime = _regime(TREND_UP=0.6, CHOP=0.1)

    with_history = generate_vwap_reclaim_rejection_candidates(_direct_context(include_history=True), regime)
    without_history = generate_vwap_reclaim_rejection_candidates(_direct_context(include_history=False), regime)

    assert _fingerprint(with_history) == _fingerprint(without_history)


def test_vwap_reclaim_snapshot_confirmation_blocks_closed_without_required_context():
    regime = _regime(TREND_UP=0.6, CHOP=0.1)

    blocked = generate_vwap_reclaim_rejection_candidates(
        StrategyContext(
            symbol="NIFTY",
            spot_ltp=22610.0,
            vwap=22540.0,
            vwap_slope=0.04,
            minutes_since_open=65,
            metadata={},
        ),
        regime,
    )

    assert blocked == ()
