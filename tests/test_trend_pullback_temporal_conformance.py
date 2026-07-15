from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from core.strategy_temporal_harness import (
    TemporalCandidateFingerprint,
    TemporalSetupConformanceCase,
    TemporalTraceObservation,
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


def _context_with_gating(state) -> StrategyContext:
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


def _context_with_full_snapshot(state) -> StrategyContext:
    latest = state.completed_bar_history[-1]
    stable_context = {
        "symbol": state.symbol,
        "ts_epoch": 1721028600.0,
        "spot_ltp": 22620.0,
        "open_price": 22500.0,
        "vwap": 22540.0,
        "day_high": 22620.0,
        "day_low": 22460.0,
        "nearest_support": 22590.0,
        "nearest_resistance": 22600.0,
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


def _trend_pullback_oracle(previous_state: str, state, ctx: StrategyContext, regime: MovementRegimeResult, generated):
    prefix_index = int((ctx.metadata or {}).get("prefix_completed_bar_count") or 0)
    emitted = bool(generated)
    fingerprint = None
    if emitted:
        candidate = generated[0]
        fingerprint = TemporalCandidateFingerprint(
            strategy_id=str(candidate.strategy_id),
            direction=str(candidate.direction),
            status=str(candidate.status),
            raw_score=round(float(candidate.raw_score), 6),
            entry_trigger=str(candidate.entry_trigger),
            invalid_if=str(candidate.invalid_if),
            rank_reason=str(candidate.rank_reason),
        )
    if prefix_index == 1:
        return TemporalTraceObservation(
            setup_state_before=previous_state,
            observed_conditions=("atruthful_snapshot", "trend_without_pullback"),
            transition="IDLE->SETUP_FORMING",
            setup_state_after="SETUP_FORMING",
            candidate_emitted=emitted,
            candidate_semantic_fingerprint=fingerprint,
            invalidation_reason=None,
            blocker_reason=None,
        )
    if prefix_index == 2:
        return TemporalTraceObservation(
            setup_state_before=previous_state,
            observed_conditions=("atruthful_snapshot", "pullback_without_trigger"),
            transition="SETUP_FORMING->SETUP_READY",
            setup_state_after="SETUP_READY",
            candidate_emitted=emitted,
            candidate_semantic_fingerprint=fingerprint,
            invalidation_reason=None,
            blocker_reason=None,
        )
    if prefix_index == 3:
        return TemporalTraceObservation(
            setup_state_before=previous_state,
            observed_conditions=("atruthful_snapshot", "trigger_like_condition"),
            transition="SETUP_READY->TRIGGERED",
            setup_state_after="TRIGGERED",
            candidate_emitted=emitted,
            candidate_semantic_fingerprint=fingerprint,
            invalidation_reason=None,
            blocker_reason=None,
        )
    return TemporalTraceObservation(
        setup_state_before=previous_state,
        observed_conditions=("atruthful_snapshot", "post_emission_repeat"),
        transition="TRIGGERED->EMITTED",
        setup_state_after="EMITTED",
        candidate_emitted=emitted,
        candidate_semantic_fingerprint=fingerprint,
        invalidation_reason=None,
        blocker_reason=None,
    )


def test_trend_pullback_context_readiness_gating():
    case = TemporalSetupConformanceCase(
        case_id="trend_pullback_prefix_threshold",
        strategy_id="trend_pullback_v1",
        symbol="NIFTY",
        segment="NSE_FNO",
        session_id="NIFTY:2026-07-14",
        completed_bars=_bars(),
        context_builder=_context_with_gating,
        regime_builder=lambda _state: _trend_regime(),
        evaluator=generate_trend_pullback_candidates,
    )

    trace = run_temporal_setup_conformance(case)

    assert [step.completed_bar_count for step in trace.steps] == [1, 2, 3, 4]
    assert trace.steps[0].candidate_emitted is False
    assert trace.steps[1].candidate_emitted is False
    assert trace.steps[2].candidate_emitted is True
    assert trace.steps[3].candidate_emitted is True
    assert trace.steps[2].candidate_semantic_fingerprint == TemporalCandidateFingerprint(
        strategy_id="trend_pullback_v1",
        direction="BUY_CALL",
        status="RAW_CANDIDATE",
        raw_score=0.648584,
        entry_trigger="trend_pullback_hold_resume",
        invalid_if="pullback_breaks_anchor",
        rank_reason="established trend resumed after a controlled pullback",
    )
    assert trace.steps[2].history_provenance["source_field"] == "completed_bar_history"
    assert trace.steps[2].history_provenance["partial_session"] is True
    assert trace.steps[2].history_provenance["complete"] is False


def test_trend_pullback_temporal_semantics_show_snapshot_false_positive():
    case = TemporalSetupConformanceCase(
        case_id="trend_pullback_temporal",
        strategy_id="trend_pullback_v1",
        symbol="NIFTY",
        segment="NSE_FNO",
        session_id="NIFTY:2026-07-14",
        completed_bars=_bars(),
        context_builder=_context_with_full_snapshot,
        regime_builder=lambda _state: _trend_regime(),
        evaluator=generate_trend_pullback_candidates,
        oracle=_trend_pullback_oracle,
    )

    trace = run_temporal_setup_conformance(case)

    assert trace.steps[0].setup_state_before == "IDLE"
    assert trace.steps[0].setup_state_after == "SETUP_FORMING"
    assert trace.steps[1].setup_state_after == "SETUP_READY"
    assert trace.steps[2].setup_state_after == "TRIGGERED"
    assert trace.steps[3].setup_state_after == "EMITTED"
    assert trace.steps[0].candidate_emitted is True
    assert trace.steps[1].candidate_emitted is True
    assert trace.steps[2].candidate_emitted is True
    assert trace.steps[3].candidate_emitted is True
    assert trace.emission_count == 4
    assert trace.first_emission_checkpoint == trace.steps[0].checkpoint_timestamp
    assert trace.repeated_semantic_fingerprint_count == 3
    assert trace.steps[0].candidate_semantic_fingerprint == trace.steps[1].candidate_semantic_fingerprint
    assert trace.steps[1].candidate_semantic_fingerprint == trace.steps[2].candidate_semantic_fingerprint
    assert trace.steps[2].candidate_semantic_fingerprint == trace.steps[3].candidate_semantic_fingerprint

    classification = "SNAPSHOT_FALSE_POSITIVE"
    assert classification == "SNAPSHOT_FALSE_POSITIVE"
