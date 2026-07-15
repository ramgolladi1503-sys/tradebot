from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from core.strategy_temporal_harness import (
    TemporalCandidateFingerprint,
    TemporalSetupConformanceCase,
    TemporalTraceObservation,
    build_prefix_history_states,
    run_temporal_setup_conformance,
)
from strategies.movement._utils import SideEvidence, make_candidate


IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class OracleStep:
    setup_state_after: str
    observed_conditions: tuple[str, ...]
    transition: str
    candidate_emitted: bool = False
    invalidation_reason: str | None = None
    blocker_reason: str | None = None


def _bars(*, base: float = 100.0, step: float = 1.0, volume_step: float = 10.0) -> tuple[dict[str, object], ...]:
    start = datetime(2026, 7, 14, 9, 15, tzinfo=IST)
    return tuple(
        {
            "ts": start + timedelta(minutes=index),
            "open": base + index * step,
            "high": base + 1.0 + index * step,
            "low": base - 1.0 + index * step,
            "close": base + 0.5 + index * step,
            "volume": 1000.0 + (index * volume_step),
        }
        for index in range(4)
    )


def _regime(*, primary: str = "TREND_UP", **scores: float) -> MovementRegimeResult:
    base_scores = {
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
    base_scores.update(scores)
    return MovementRegimeResult(schema_version=1, primary_regime=primary, scores=base_scores)


def _temporal_candidate(ctx: StrategyContext, regime: MovementRegimeResult, *, prefix_index: int) -> tuple:
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


def _oracle_factory(specs: Mapping[int, OracleStep]):
    def oracle(
        previous_state: str,
        state,
        ctx: StrategyContext,
        regime: MovementRegimeResult,
        generated,
    ) -> TemporalTraceObservation:
        prefix_index = int((ctx.metadata or {}).get("prefix_index") or state.completed_bar_count or 0)
        spec = specs.get(prefix_index)
        if spec is None:
            spec = OracleStep(
                setup_state_after=previous_state,
                observed_conditions=("causal_prefix",),
                transition=f"{previous_state}->{previous_state}",
                candidate_emitted=False,
            )
        emitted = bool(generated)
        if emitted != spec.candidate_emitted:
            raise AssertionError(f"candidate_emission_mismatch:{prefix_index}:{emitted}:{spec.candidate_emitted}")
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
        return TemporalTraceObservation(
            setup_state_before=previous_state,
            observed_conditions=spec.observed_conditions,
            transition=spec.transition,
            setup_state_after=spec.setup_state_after,
            candidate_emitted=spec.candidate_emitted,
            candidate_semantic_fingerprint=fingerprint,
            invalidation_reason=spec.invalidation_reason,
            blocker_reason=spec.blocker_reason,
        )

    return oracle


def _oracle_case(
    *,
    case_id: str,
    session_id: str,
    bars: tuple[dict[str, object], ...],
    emit_prefixes: tuple[int, ...] = (),
    specs: Mapping[int, OracleStep],
):
    emit_prefixes = tuple(sorted(set(int(item) for item in emit_prefixes)))

    def evaluator(ctx: StrategyContext, regime: MovementRegimeResult):
        prefix_index = int((ctx.metadata or {}).get("prefix_index") or 0)
        if prefix_index in emit_prefixes:
            return _temporal_candidate(ctx, regime, prefix_index=prefix_index)
        return ()

    return TemporalSetupConformanceCase(
        case_id=case_id,
        strategy_id="temporal_oracle_v1",
        symbol="NIFTY",
        segment="NSE_FNO",
        session_id=session_id,
        completed_bars=bars,
        context_builder=_oracle_context,
        regime_builder=lambda _state: _regime(),
        evaluator=evaluator,
        oracle=_oracle_factory(specs),
    )


def _oracle_context(state) -> StrategyContext:
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


def _trend_regime() -> MovementRegimeResult:
    return _regime(primary="TREND_UP", TREND_UP=0.8)


def test_temporal_harness_walks_causal_prefixes_and_freezes_trace():
    bars = _bars()
    case = _oracle_case(
        case_id="oracle_prefix_case",
        session_id="NIFTY:2026-07-14",
        bars=bars,
        emit_prefixes=(3, 4),
        specs={
            1: OracleStep("SETUP_FORMING", ("causal_prefix", "forming"), "IDLE->SETUP_FORMING"),
            2: OracleStep("SETUP_READY", ("causal_prefix", "ready"), "SETUP_FORMING->SETUP_READY"),
            3: OracleStep("EMITTED", ("causal_prefix", "trigger"), "SETUP_READY->EMITTED", candidate_emitted=True),
            4: OracleStep("EMITTED", ("causal_prefix", "post_trigger"), "EMITTED->EMITTED", candidate_emitted=True),
        },
    )

    states = build_prefix_history_states(
        symbol="NIFTY",
        segment="NSE_FNO",
        timeframe="1m",
        completed_bars=bars,
    )
    trace = run_temporal_setup_conformance(case)

    assert [state.completed_bar_count for state in states] == [1, 2, 3, 4]
    assert [step.completed_bar_count for step in trace.steps] == [1, 2, 3, 4]
    assert [step.candidate_fingerprints for step in trace.steps[:2]] == [(), ()]
    assert trace.steps[0].setup_state_before == "IDLE"
    assert trace.steps[1].setup_state_after == "SETUP_READY"
    assert trace.steps[2].setup_state_after == "EMITTED"
    assert trace.steps[2].candidate_emitted is True
    assert trace.steps[2].candidate_semantic_fingerprint == TemporalCandidateFingerprint(
        strategy_id="temporal_oracle_v1",
        direction="BUY_CALL",
        status="RAW_CANDIDATE",
        raw_score=0.42,
        entry_trigger="temporal_oracle_ready",
        invalid_if="temporal_oracle_not_ready",
        rank_reason="temporal oracle becomes ready after causal prefix threshold",
    )
    assert trace.steps[3].candidate_semantic_fingerprint == trace.steps[2].candidate_semantic_fingerprint
    assert trace.steps[0].history_provenance["source_component"] == "core.strategy_temporal_harness"
    assert trace.steps[0].history_provenance["source_event_timestamp"] == trace.steps[0].latest_completed_timestamp
    assert trace.steps[0].history_provenance["receipt_timestamp"] == trace.steps[0].latest_completed_timestamp
    assert trace.emission_count == 2
    assert trace.first_emission_checkpoint == trace.steps[2].checkpoint_timestamp
    assert trace.repeated_semantic_fingerprint_count == 1

    original_hashes = [step.history_hash for step in trace.steps]
    mutated_bars = list(bars)
    mutated_bars[3]["volume"] = 9999.0
    mutated_trace = run_temporal_setup_conformance(
        _oracle_case(
            case_id="oracle_prefix_case",
            session_id="NIFTY:2026-07-14",
            bars=tuple(mutated_bars),
            emit_prefixes=(3, 4),
            specs={
                1: OracleStep("SETUP_FORMING", ("causal_prefix", "forming"), "IDLE->SETUP_FORMING"),
                2: OracleStep("SETUP_READY", ("causal_prefix", "ready"), "SETUP_FORMING->SETUP_READY"),
                3: OracleStep("EMITTED", ("causal_prefix", "trigger"), "SETUP_READY->EMITTED", candidate_emitted=True),
                4: OracleStep("EMITTED", ("causal_prefix", "post_trigger"), "EMITTED->EMITTED", candidate_emitted=True),
            },
        )
    )
    assert [step.history_hash for step in trace.steps] == original_hashes
    assert [step.history_hash for step in mutated_trace.steps] != original_hashes
    assert trace.steps[:3] == mutated_trace.steps[:3]


def test_future_bar_mutation_cannot_change_earlier_temporal_checkpoint():
    bars = _bars()
    specs = {
        1: OracleStep("SETUP_FORMING", ("causal_prefix", "forming"), "IDLE->SETUP_FORMING"),
        2: OracleStep("SETUP_READY", ("causal_prefix", "ready"), "SETUP_FORMING->SETUP_READY"),
        3: OracleStep("TRIGGERED", ("causal_prefix", "trigger"), "SETUP_READY->TRIGGERED", candidate_emitted=True),
        4: OracleStep("EMITTED", ("causal_prefix", "post_trigger"), "TRIGGERED->EMITTED"),
    }
    case = _oracle_case(
        case_id="future_mutation_case",
        session_id="NIFTY:2026-07-14",
        bars=bars,
        emit_prefixes=(3,),
        specs=specs,
    )
    trace = run_temporal_setup_conformance(case)
    mutated = list(bars)
    mutated[3]["volume"] = 9999.0
    mutated_trace = run_temporal_setup_conformance(
        _oracle_case(
            case_id="future_mutation_case",
            session_id="NIFTY:2026-07-14",
            bars=tuple(mutated),
            emit_prefixes=(3,),
            specs=specs,
        )
    )
    assert trace.steps[0] == mutated_trace.steps[0]
    assert trace.steps[1] == mutated_trace.steps[1]
    assert trace.steps[2].history_hash == mutated_trace.steps[2].history_hash
    assert trace.steps[3].history_hash != mutated_trace.steps[3].history_hash


def test_full_source_cutoff_equals_physically_truncated_temporal_prefix():
    bars = _bars()
    specs = {
        1: OracleStep("SETUP_FORMING", ("causal_prefix", "forming"), "IDLE->SETUP_FORMING"),
        2: OracleStep("SETUP_READY", ("causal_prefix", "ready"), "SETUP_FORMING->SETUP_READY"),
        3: OracleStep("TRIGGERED", ("causal_prefix", "trigger"), "SETUP_READY->TRIGGERED", candidate_emitted=True),
    }
    full_trace = run_temporal_setup_conformance(
        _oracle_case(
            case_id="truncation_case",
            session_id="NIFTY:2026-07-14",
            bars=bars,
            emit_prefixes=(3,),
            specs=specs,
        )
    )
    truncated_trace = run_temporal_setup_conformance(
        _oracle_case(
            case_id="truncation_case",
            session_id="NIFTY:2026-07-14",
            bars=bars[:3],
            emit_prefixes=(3,),
            specs={k: v for k, v in specs.items() if k <= 3},
        )
    )
    assert full_trace.steps[:3] == truncated_trace.steps
    assert full_trace.steps[2].checkpoint_timestamp == truncated_trace.steps[2].checkpoint_timestamp


def test_temporal_trace_is_deterministic_for_same_prefix_sequence():
    bars = _bars()
    case = _oracle_case(
        case_id="determinism_case",
        session_id="NIFTY:2026-07-14",
        bars=bars,
        emit_prefixes=(3,),
        specs={
            1: OracleStep("SETUP_FORMING", ("causal_prefix", "forming"), "IDLE->SETUP_FORMING"),
            2: OracleStep("SETUP_READY", ("causal_prefix", "ready"), "SETUP_FORMING->SETUP_READY"),
            3: OracleStep("EMITTED", ("causal_prefix", "trigger"), "SETUP_READY->EMITTED", candidate_emitted=True),
            4: OracleStep("EMITTED", ("causal_prefix", "post_trigger"), "EMITTED->EMITTED"),
        },
    )
    trace = run_temporal_setup_conformance(case)
    repeat = run_temporal_setup_conformance(case)
    assert trace == repeat


def test_new_session_resets_unfinished_temporal_setup():
    session_a = run_temporal_setup_conformance(
        _oracle_case(
            case_id="session_a",
            session_id="SESSION-A",
            bars=_bars(),
            emit_prefixes=(),
            specs={
                1: OracleStep("SETUP_FORMING", ("causal_prefix", "forming"), "IDLE->SETUP_FORMING"),
                2: OracleStep("SETUP_READY", ("causal_prefix", "ready"), "SETUP_FORMING->SETUP_READY"),
                3: OracleStep("SETUP_READY", ("causal_prefix", "ready"), "SETUP_READY->SETUP_READY"),
                4: OracleStep("SETUP_READY", ("causal_prefix", "ready"), "SETUP_READY->SETUP_READY"),
            },
        )
    )
    session_b = run_temporal_setup_conformance(
        _oracle_case(
            case_id="session_b",
            session_id="SESSION-B",
            bars=_bars(base=200.0),
            emit_prefixes=(1,),
            specs={
                1: OracleStep("EMITTED", ("causal_prefix", "trigger"), "IDLE->EMITTED", candidate_emitted=True),
            },
        )
    )
    assert session_a.steps[-1].setup_state_after == "SETUP_READY"
    assert session_b.steps[0].setup_state_before == "IDLE"
    assert session_b.steps[0].setup_state_before != session_a.steps[-1].setup_state_after
    assert session_b.steps[0].candidate_emitted is True


def test_invalidation_prevents_later_trigger_emission():
    bars = _bars()
    invalidated_trace = run_temporal_setup_conformance(
        _oracle_case(
            case_id="invalidation_case",
            session_id="SESSION-INV",
            bars=bars,
            emit_prefixes=(),
            specs={
                1: OracleStep("SETUP_FORMING", ("causal_prefix", "forming"), "IDLE->SETUP_FORMING"),
                2: OracleStep("SETUP_READY", ("causal_prefix", "ready"), "SETUP_FORMING->SETUP_READY"),
                3: OracleStep(
                    "INVALIDATED",
                    ("causal_prefix", "invalidating_bar"),
                    "SETUP_READY->INVALIDATED",
                    blocker_reason="missing_required_confirmation",
                ),
                4: OracleStep("INVALIDATED", ("causal_prefix", "post_invalidated"), "INVALIDATED->INVALIDATED"),
            },
        )
    )
    recovered_trace = run_temporal_setup_conformance(
        _oracle_case(
            case_id="invalidation_case_recovered",
            session_id="SESSION-INV",
            bars=bars,
            emit_prefixes=(3,),
            specs={
                1: OracleStep("SETUP_FORMING", ("causal_prefix", "forming"), "IDLE->SETUP_FORMING"),
                2: OracleStep("SETUP_READY", ("causal_prefix", "ready"), "SETUP_FORMING->SETUP_READY"),
                3: OracleStep("EMITTED", ("causal_prefix", "trigger"), "SETUP_READY->EMITTED", candidate_emitted=True),
                4: OracleStep("EMITTED", ("causal_prefix", "post_trigger"), "EMITTED->EMITTED"),
            },
        )
    )
    assert invalidated_trace.steps[2].setup_state_after == "INVALIDATED"
    assert invalidated_trace.steps[2].blocker_reason == "missing_required_confirmation"
    assert invalidated_trace.steps[3].candidate_emitted is False
    assert recovered_trace.steps[2].candidate_emitted is True
    assert recovered_trace.steps[2].setup_state_after == "EMITTED"


def test_ready_setup_does_not_emit_before_trigger_transition():
    bars = _bars()
    trace = run_temporal_setup_conformance(
        _oracle_case(
            case_id="premature_case",
            session_id="SESSION-PRE",
            bars=bars,
            emit_prefixes=(3,),
            specs={
                1: OracleStep("SETUP_FORMING", ("causal_prefix", "forming"), "IDLE->SETUP_FORMING"),
                2: OracleStep("SETUP_READY", ("causal_prefix", "ready"), "SETUP_FORMING->SETUP_READY"),
                3: OracleStep("TRIGGERED", ("causal_prefix", "trigger"), "SETUP_READY->TRIGGERED", candidate_emitted=True),
                4: OracleStep("EMITTED", ("causal_prefix", "post_trigger"), "TRIGGERED->EMITTED"),
            },
        )
    )
    assert trace.steps[1].setup_state_after == "SETUP_READY"
    assert trace.steps[1].candidate_emitted is False
    assert trace.steps[2].setup_state_after == "TRIGGERED"
    assert trace.steps[2].candidate_emitted is True


def test_oracle_emits_once_for_one_setup():
    bars = _bars()
    trace = run_temporal_setup_conformance(
        _oracle_case(
            case_id="single_emit_case",
            session_id="SESSION-SINGLE",
            bars=bars,
            emit_prefixes=(3,),
            specs={
                1: OracleStep("SETUP_FORMING", ("causal_prefix", "forming"), "IDLE->SETUP_FORMING"),
                2: OracleStep("SETUP_READY", ("causal_prefix", "ready"), "SETUP_FORMING->SETUP_READY"),
                3: OracleStep("EMITTED", ("causal_prefix", "trigger"), "SETUP_READY->EMITTED", candidate_emitted=True),
                4: OracleStep("EMITTED", ("causal_prefix", "post_trigger"), "EMITTED->EMITTED"),
            },
        )
    )
    assert trace.emission_count == 1
    assert trace.first_emission_checkpoint == trace.steps[2].checkpoint_timestamp
    assert trace.repeated_semantic_fingerprint_count == 0
    assert trace.steps[3].candidate_emitted is False


def test_harness_detects_repeated_semantic_emission():
    bars = _bars()
    trace = run_temporal_setup_conformance(
        _oracle_case(
            case_id="repeat_case",
            session_id="SESSION-REPEAT",
            bars=bars,
            emit_prefixes=(3, 4),
            specs={
                1: OracleStep("SETUP_FORMING", ("causal_prefix", "forming"), "IDLE->SETUP_FORMING"),
                2: OracleStep("SETUP_READY", ("causal_prefix", "ready"), "SETUP_FORMING->SETUP_READY"),
                3: OracleStep("EMITTED", ("causal_prefix", "trigger"), "SETUP_READY->EMITTED", candidate_emitted=True),
                4: OracleStep("EMITTED", ("causal_prefix", "post_trigger"), "EMITTED->EMITTED", candidate_emitted=True),
            },
        )
    )
    assert trace.emission_count == 2
    assert trace.first_emission_checkpoint == trace.steps[2].checkpoint_timestamp
    assert trace.repeated_semantic_fingerprint_count == 1
    assert trace.steps[2].candidate_semantic_fingerprint == trace.steps[3].candidate_semantic_fingerprint


def test_harness_rejects_empty_bar_sequences():
    case = TemporalSetupConformanceCase(
        case_id="empty_case",
        strategy_id="temporal_oracle_v1",
        symbol="NIFTY",
        segment="NSE_FNO",
        completed_bars=(),
        context_builder=_oracle_context,
        regime_builder=lambda _state: _regime(),
        evaluator=lambda _ctx, _regime: (),
        oracle=lambda previous_state, state, ctx, regime, generated: TemporalTraceObservation(
            setup_state_before=previous_state,
            observed_conditions=("causal_prefix",),
            transition=f"{previous_state}->{previous_state}",
            setup_state_after=previous_state,
            candidate_emitted=False,
            candidate_semantic_fingerprint=None,
            invalidation_reason=None,
            blocker_reason=None,
        ),
        session_id="EMPTY",
    )

    trace = run_temporal_setup_conformance(case)
    assert trace.steps == ()
