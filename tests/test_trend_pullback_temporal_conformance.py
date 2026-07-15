from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from core.strategy_temporal_harness import (
    TemporalCandidateFingerprint,
    TemporalSetupConformanceCase,
    run_temporal_setup_conformance,
)
from strategies.movement.trend_pullback import generate_trend_pullback_candidates


IST = ZoneInfo("Asia/Kolkata")


def _bars() -> tuple[dict[str, object], ...]:
    start = datetime(2026, 7, 14, 9, 15, tzinfo=IST)
    return tuple(
        {
            "ts": start + timedelta(minutes=index),
            "open": 22500.0 + (index * 25.0),
            "high": 22520.0 + (index * 25.0),
            "low": 22480.0 + (index * 25.0),
            "close": 22510.0 + (index * 25.0),
            "volume": 1000.0 + (index * 100.0),
        }
        for index in range(4)
    )


def _trend_regime() -> MovementRegimeResult:
    return MovementRegimeResult(
        schema_version=1,
        primary_regime="TREND_UP",
        scores={
            "TREND_UP": 0.8,
            "TREND_DOWN": 0.0,
            "RANGE": 0.0,
            "CHOP": 0.0,
            "COMPRESSION": 0.0,
            "VOLATILITY_EXPANSION": 0.0,
            "TRAP_RISK": 0.0,
            "EXHAUSTION_RISK": 0.0,
            "EXPIRY_CONTEXT": 0.0,
            "INCONCLUSIVE": 0.0,
        },
    )


def _trend_pullback_context(state) -> StrategyContext:
    latest = state.completed_bar_history[-1]
    stable_context = {
        "symbol": state.symbol,
        "ts_epoch": 1721028600.0,
        "spot_ltp": 22620.0,
        "open_price": 22500.0,
        "vwap": 22540.0,
        "day_high": 22620.0,
        "day_low": 22460.0,
        "nearest_support": 22590.0 if state.completed_bar_count >= 3 else None,
        "nearest_resistance": 22600.0 if state.completed_bar_count >= 3 else None,
        "range_width_pct": 0.14,
        "atr": 70.0,
        "volume_z": 1.5,
        "vwap_slope": 0.03,
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
        "metadata": {
            "history_hash": state.history_hash,
            "prefix_completed_bar_count": state.completed_bar_count,
            "latest_completed_close": latest.close,
            "completed_bar_history": state.history_payload(),
            "completed_bar_history_provenance": state.provenance_payload(
                source_component="tests.test_trend_pullback_temporal_conformance"
            ),
        },
    }
    return StrategyContext(**stable_context)


def test_trend_pullback_temporal_setup_becomes_ready_on_causal_prefix_threshold():
    case = TemporalSetupConformanceCase(
        case_id="trend_pullback_prefix_threshold",
        strategy_id="trend_pullback_v1",
        symbol="NIFTY",
        segment="NSE_FNO",
        completed_bars=_bars(),
        context_builder=_trend_pullback_context,
        regime_builder=lambda _state: _trend_regime(),
        evaluator=generate_trend_pullback_candidates,
    )

    trace = run_temporal_setup_conformance(case)

    assert [step.completed_bar_count for step in trace.steps] == [1, 2, 3, 4]
    assert trace.steps[0].candidate_fingerprints == ()
    assert trace.steps[1].candidate_fingerprints == ()
    assert trace.steps[2].candidate_fingerprints == (
        TemporalCandidateFingerprint(
            strategy_id="trend_pullback_v1",
            direction="BUY_CALL",
            status="RAW_CANDIDATE",
            raw_score=0.648584,
            entry_trigger="trend_pullback_hold_resume",
            invalid_if="pullback_breaks_anchor",
            rank_reason="established trend resumed after a controlled pullback",
        ),
    )
    assert trace.steps[3].candidate_fingerprints == trace.steps[2].candidate_fingerprints
    assert trace.steps[2].history_provenance["source_field"] == "completed_bar_history"
    assert trace.steps[2].history_provenance["partial_session"] is True
    assert trace.steps[2].history_provenance["complete"] is False

    repeat = run_temporal_setup_conformance(case)
    assert trace == repeat
