from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core import runtime_snapshot_producer
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
            "open": close - 5.0,
            "high": close + 10.0,
            "low": close - 10.0,
            "close": close,
            "volume": 1000.0 + (index * 100.0),
        }
        for index, close in enumerate((22590.0, 22630.0, 22615.0, 22635.0))
    )


def _trend_pullback_history() -> tuple[dict[str, object], ...]:
    start = datetime(2026, 7, 14, 9, 15, tzinfo=IST)
    closes = (22590.0, 22630.0, 22615.0, 22635.0)
    bars = []
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
    return tuple(bars)


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
        "previous_completed_close": state.previous_completed_close,
        "completed_bar_history": state.history_payload(),
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
        "previous_completed_close": state.previous_completed_close,
        "completed_bar_history": state.history_payload(),
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
            observed_conditions=("atruthful_snapshot", "trend_establishment"),
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
            observed_conditions=("atruthful_snapshot", "trend_continues"),
            transition="SETUP_FORMING->SETUP_FORMING",
            setup_state_after="SETUP_FORMING",
            candidate_emitted=emitted,
            candidate_semantic_fingerprint=fingerprint,
            invalidation_reason=None,
            blocker_reason=None,
        )
    if prefix_index == 3:
        return TemporalTraceObservation(
            setup_state_before=previous_state,
            observed_conditions=("atruthful_snapshot", "pullback_ready"),
            transition="SETUP_FORMING->SETUP_READY",
            setup_state_after="SETUP_READY",
            candidate_emitted=emitted,
            candidate_semantic_fingerprint=fingerprint,
            invalidation_reason=None,
            blocker_reason=None,
        )
    return TemporalTraceObservation(
        setup_state_before=previous_state,
        observed_conditions=("atruthful_snapshot", "continuation_trigger"),
        transition="SETUP_READY->TRIGGERED",
        setup_state_after="TRIGGERED",
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
    assert trace.steps[2].candidate_emitted is False
    assert trace.steps[3].candidate_emitted is True
    assert trace.steps[3].candidate_semantic_fingerprint == TemporalCandidateFingerprint(
        strategy_id="trend_pullback_v1",
        direction="BUY_CALL",
        status="RAW_CANDIDATE",
        raw_score=0.648584,
        entry_trigger="trend_pullback_hold_resume",
        invalid_if="pullback_breaks_anchor",
        rank_reason="established trend resumed after a controlled pullback",
    )
    assert trace.steps[3].history_provenance["source_field"] == "completed_bar_history"
    assert trace.steps[3].history_provenance["partial_session"] is True
    assert trace.steps[3].history_provenance["complete"] is False


def test_trend_pullback_temporal_semantics_require_previous_close_transition():
    case = TemporalSetupConformanceCase(
        case_id="trend_pullback_temporal",
        strategy_id="trend_pullback_v1",
        symbol="NIFTY",
        segment="NSE_FNO",
        session_id="NIFTY:2026-07-14",
        completed_bars=_bars(),
        context_builder=_context_with_gating,
        regime_builder=lambda _state: _trend_regime(),
        evaluator=generate_trend_pullback_candidates,
        oracle=_trend_pullback_oracle,
    )

    trace = run_temporal_setup_conformance(case)

    assert trace.steps[0].setup_state_before == "IDLE"
    assert trace.steps[0].setup_state_after == "SETUP_FORMING"
    assert trace.steps[1].setup_state_after == "SETUP_FORMING"
    assert trace.steps[2].setup_state_after == "SETUP_READY"
    assert trace.steps[3].setup_state_after == "TRIGGERED"
    assert trace.steps[0].candidate_emitted is False
    assert trace.steps[1].candidate_emitted is False
    assert trace.steps[2].candidate_emitted is False
    assert trace.steps[3].candidate_emitted is True
    assert trace.emission_count == 1
    assert trace.first_emission_checkpoint == trace.steps[3].checkpoint_timestamp
    assert trace.repeated_semantic_fingerprint_count == 0
    assert trace.steps[3].candidate_semantic_fingerprint == TemporalCandidateFingerprint(
        strategy_id="trend_pullback_v1",
        direction="BUY_CALL",
        status="RAW_CANDIDATE",
        raw_score=0.648584,
        entry_trigger="trend_pullback_hold_resume",
        invalid_if="pullback_breaks_anchor",
        rank_reason="established trend resumed after a controlled pullback",
    )

    classification = "CAUSAL_PREFIX_SINGLE_EMIT"
    assert classification == "CAUSAL_PREFIX_SINGLE_EMIT"


def test_runtime_snapshot_producer_preserves_completed_history_for_trend_pullback(
    monkeypatch,
    tmp_path,
):
    history = _trend_pullback_history()
    provenance = {
        "status": "TRUTHFUL",
        "source_component": "tests.test_trend_pullback_temporal_conformance",
        "source_field": "completed_bar_history",
        "source_event_timestamp": "2026-07-14T09:19:00+05:30",
        "receipt_timestamp": "2026-07-14T09:19:01+05:30",
        "scope": "session_completed_bar_history",
        "complete": True,
        "timeframe": "1m",
        "symbol": "NIFTY",
        "session_date": "2026-07-14",
    }
    runtime_truth = {
        "spot_ltp": 22620.0,
        "open_price": 22500.0,
        "vwap": 22540.0,
        "day_high": 22620.0,
        "day_low": 22460.0,
        "nearest_support": 22590.0,
        "nearest_resistance": 22600.0,
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
        "regime_scores": {
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
        "completed_bar_history": history,
    }
    market_snapshot = {
        "symbols": {
            "NIFTY": {
                "symbol": "NIFTY",
                "ohlc": {"close": 22620.0},
                "metadata": {
                    "strategy_context_truth": runtime_truth,
                    "strategy_context_provenance": {"completed_bar_history": provenance},
                },
            }
        }
    }

    owner_db = tmp_path / "opening_range_retest_owner.sqlite"
    monkeypatch.setattr(runtime_snapshot_producer, "default_owner_db_path", lambda: owner_db)
    runtime_snapshot_producer._opening_range_retest_owner_store.cache_clear()

    captured: dict[str, object] = {}
    real_build = runtime_snapshot_producer.build_ranked_opportunity_report

    def wrapped_build_ranked_opportunity_report(*args, **kwargs):
        captured["ctx"] = kwargs["ctx"]
        report = real_build(*args, **kwargs)
        captured["report"] = report
        return report

    monkeypatch.setattr(runtime_snapshot_producer, "build_ranked_opportunity_report", wrapped_build_ranked_opportunity_report)
    monkeypatch.setattr(runtime_snapshot_producer, "write_ranked_pipeline_snapshot", lambda **kwargs: None)
    monkeypatch.setattr(runtime_snapshot_producer, "write_ranked_vs_legacy_snapshot", lambda **kwargs: None)

    runtime_snapshot_producer._build_and_write_canonical_ranked_snapshot(market_snapshot, "unit-test", {"rows": []})

    ctx = captured["ctx"]
    report = captured["report"]
    assert isinstance(ctx.completed_bar_history, tuple)
    assert ctx.completed_bar_history == tuple(history)
    assert ctx.metadata["completed_bar_history_provenance"]["source_field"] == "completed_bar_history"

    trend_pullback = [
        candidate
        for candidate in report.candidate_pool.candidates
        if candidate.strategy_id == "trend_pullback_v1"
    ]
    assert len(trend_pullback) == 1
    direct_candidates = generate_trend_pullback_candidates(ctx, report.candidate_pool.regime)
    assert len(direct_candidates) == 1
    assert trend_pullback[0].direction == direct_candidates[0].direction == "BUY_CALL"
    assert trend_pullback[0].status == "VALIDATED_CANDIDATE"
    assert direct_candidates[0].status == "RAW_CANDIDATE"
    assert round(trend_pullback[0].raw_score, 6) == round(direct_candidates[0].raw_score, 6)
    assert trend_pullback[0].evidence["setup_identity"] == direct_candidates[0].evidence["setup_identity"]
    assert report.candidate_pool.metadata["raw_candidate_count_before_phase2_enrichment"] == len(direct_candidates)
