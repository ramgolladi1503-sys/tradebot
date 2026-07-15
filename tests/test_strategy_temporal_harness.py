from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from core.strategy_temporal_harness import (
    TemporalSetupConformanceCase,
    TemporalCandidateFingerprint,
    build_prefix_history_states,
    run_temporal_setup_conformance,
)
from strategies.movement._utils import SideEvidence, make_candidate


IST = ZoneInfo("Asia/Kolkata")


def _bars() -> tuple[dict[str, object], ...]:
    start = datetime(2026, 7, 14, 9, 15, tzinfo=IST)
    return tuple(
        {
            "ts": start + timedelta(minutes=index),
            "open": 100.0 + index,
            "high": 101.0 + index,
            "low": 99.0 + index,
            "close": 100.5 + index,
            "volume": 1000.0 + (index * 10.0),
        }
        for index in range(4)
    )


def _regime() -> MovementRegimeResult:
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


def _dummy_context(state) -> StrategyContext:
    latest = state.completed_bar_history[-1]
    return StrategyContext(
        symbol=state.symbol,
        ts_epoch=1719998100.0,
        spot_ltp=latest.close,
        vwap=latest.close - 0.25,
        minutes_since_open=12,
        metadata={
            "prefix_index": state.completed_bar_count,
            "history_hash": state.history_hash,
            "completed_bar_history": state.history_payload(),
        },
    )


def _dummy_evaluator(ctx: StrategyContext, regime: MovementRegimeResult):
    prefix_index = int((ctx.metadata or {}).get("prefix_index") or 0)
    if prefix_index < 3:
        return ()
    side = SideEvidence(
        direction="BUY_CALL",
        option_ltp=120.0,
        premium_change=12.0,
        spread_pct=0.8,
        depth=1200.0,
        blockers=(),
        warnings=(),
        option_confirmation_score=0.6,
        liquidity_score=0.7,
        freshness_score=0.8,
    )
    return (
        make_candidate(
            ctx=ctx,
            regime=regime,
            strategy_id="temporal_oracle_v1",
            movement_type="LEGACY_SIGNAL",
            direction="BUY_CALL",
            price_structure_score=0.42,
            side=side,
            entry_trigger="temporal_oracle_ready",
            invalid_if="temporal_oracle_not_ready",
            rank_reason="temporal oracle becomes ready after causal prefix threshold",
            evidence={"prefix_index": prefix_index},
            warnings=(),
            confluence_tags=("temporal",),
            strategy_version="v1",
            params_used={"MIN_PREFIX_INDEX": 3},
            params_hash="temporal-oracle-hash",
        ),
    )


def test_temporal_harness_walks_causal_prefixes_and_freezes_trace():
    case = TemporalSetupConformanceCase(
        case_id="oracle_prefix_case",
        strategy_id="temporal_oracle_v1",
        symbol="NIFTY",
        segment="NSE_FNO",
        completed_bars=_bars(),
        context_builder=_dummy_context,
        regime_builder=lambda _state: _regime(),
        evaluator=_dummy_evaluator,
    )

    states = build_prefix_history_states(
        symbol="NIFTY",
        segment="NSE_FNO",
        timeframe="1m",
        completed_bars=_bars(),
    )
    trace = run_temporal_setup_conformance(case)

    assert [state.completed_bar_count for state in states] == [1, 2, 3, 4]
    assert [step.completed_bar_count for step in trace.steps] == [1, 2, 3, 4]
    assert [step.candidate_fingerprints for step in trace.steps[:2]] == [(), ()]
    assert trace.steps[2].candidate_fingerprints == (
        TemporalCandidateFingerprint(
            strategy_id="temporal_oracle_v1",
            direction="BUY_CALL",
            status="RAW_CANDIDATE",
            raw_score=0.42,
            entry_trigger="temporal_oracle_ready",
            invalid_if="temporal_oracle_not_ready",
            rank_reason="temporal oracle becomes ready after causal prefix threshold",
        ),
    )
    assert trace.steps[3].candidate_fingerprints == trace.steps[2].candidate_fingerprints
    assert trace.steps[0].history_provenance["source_component"] == "core.strategy_temporal_harness"
    assert trace.steps[0].history_provenance["source_event_timestamp"] == trace.steps[0].latest_completed_timestamp
    assert trace.steps[0].history_provenance["receipt_timestamp"] == trace.steps[0].latest_completed_timestamp

    original_hashes = [step.history_hash for step in trace.steps]
    mutated_bars = list(_bars())
    mutated_bars[0]["volume"] = 9999.0
    mutated_trace = run_temporal_setup_conformance(
        TemporalSetupConformanceCase(
            case_id="oracle_prefix_case",
            strategy_id="temporal_oracle_v1",
            symbol="NIFTY",
            segment="NSE_FNO",
            completed_bars=tuple(mutated_bars),
            context_builder=_dummy_context,
            regime_builder=lambda _state: _regime(),
            evaluator=_dummy_evaluator,
        )
    )
    assert [step.history_hash for step in trace.steps] == original_hashes
    assert [step.history_hash for step in mutated_trace.steps] != original_hashes


def test_harness_rejects_empty_bar_sequences():
    case = TemporalSetupConformanceCase(
        case_id="empty_case",
        strategy_id="temporal_oracle_v1",
        symbol="NIFTY",
        segment="NSE_FNO",
        completed_bars=(),
        context_builder=_dummy_context,
        regime_builder=lambda _state: _regime(),
        evaluator=_dummy_evaluator,
    )

    trace = run_temporal_setup_conformance(case)
    assert trace.steps == ()
