from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.session_bar_history import (
    CompletedBarSnapshot,
    SessionBarHistoryState,
    build_session_bar_history_state,
)
from core.time_utils import IST_TZ


ContextBuilder = Callable[[SessionBarHistoryState], StrategyContext]
RegimeBuilder = Callable[[SessionBarHistoryState], MovementRegimeResult]
Evaluator = Callable[[StrategyContext, MovementRegimeResult], Iterable[StrategyCandidate]]
TemporalState = str
TemporalOracle = Callable[
    [TemporalState, SessionBarHistoryState, StrategyContext, MovementRegimeResult, tuple[StrategyCandidate, ...]],
    "TemporalTraceObservation",
]


@dataclass(frozen=True)
class TemporalSetupConformanceCase:
    """A causal completed-bar scenario for strategy setup conformance checks."""

    case_id: str
    strategy_id: str
    symbol: str
    segment: str
    completed_bars: tuple[CompletedBarSnapshot | Mapping[str, Any], ...]
    context_builder: ContextBuilder
    regime_builder: RegimeBuilder
    evaluator: Evaluator
    oracle: TemporalOracle | None = None
    session_id: str | None = None
    timeframe: str = "1m"
    source_component: str = "core.strategy_temporal_harness"


@dataclass(frozen=True)
class TemporalCandidateFingerprint:
    strategy_id: str
    direction: str
    status: str
    raw_score: float
    entry_trigger: str
    invalid_if: str
    rank_reason: str


@dataclass(frozen=True)
class TemporalTraceObservation:
    setup_state_before: TemporalState
    observed_conditions: tuple[str, ...]
    transition: str
    setup_state_after: TemporalState
    candidate_emitted: bool
    candidate_semantic_fingerprint: TemporalCandidateFingerprint | None
    invalidation_reason: str | None
    blocker_reason: str | None


@dataclass(frozen=True)
class TemporalSetupConformanceStep:
    strategy_id: str
    symbol: str
    session_id: str
    prefix_bar_count: int
    checkpoint_timestamp: str | None
    history_hash: str
    setup_state_before: TemporalState
    observed_conditions: tuple[str, ...]
    transition: str
    setup_state_after: TemporalState
    candidate_emitted: bool
    candidate_semantic_fingerprint: TemporalCandidateFingerprint | None
    invalidation_reason: str | None
    blocker_reason: str | None
    provenance: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_conditions", tuple(sorted(str(item) for item in self.observed_conditions if str(item).strip())))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidate_semantic_fingerprint"] = (
            asdict(self.candidate_semantic_fingerprint) if self.candidate_semantic_fingerprint is not None else None
        )
        payload["candidate_fingerprints"] = (
            [asdict(self.candidate_semantic_fingerprint)] if self.candidate_semantic_fingerprint is not None else []
        )
        return payload

    @property
    def prefix_index(self) -> int:
        return self.prefix_bar_count

    @property
    def completed_bar_count(self) -> int:
        return self.prefix_bar_count

    @property
    def latest_completed_timestamp(self) -> str | None:
        return self.checkpoint_timestamp

    @property
    def history_provenance(self) -> dict[str, Any]:
        return self.provenance

    @property
    def candidate_fingerprints(self) -> tuple[TemporalCandidateFingerprint, ...]:
        if self.candidate_semantic_fingerprint is None:
            return ()
        return (self.candidate_semantic_fingerprint,)


@dataclass(frozen=True)
class TemporalSetupConformanceTrace:
    case_id: str
    strategy_id: str
    symbol: str
    session_id: str
    segment: str
    timeframe: str
    steps: tuple[TemporalSetupConformanceStep, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["steps"] = [step.to_dict() for step in self.steps]
        return payload

    @property
    def emission_count(self) -> int:
        return sum(1 for step in self.steps if step.candidate_emitted)

    @property
    def first_emission_checkpoint(self) -> str | None:
        for step in self.steps:
            if step.candidate_emitted:
                return step.checkpoint_timestamp
        return None

    @property
    def repeated_semantic_fingerprint_count(self) -> int:
        fingerprints = [
            step.candidate_semantic_fingerprint
            for step in self.steps
            if step.candidate_emitted and step.candidate_semantic_fingerprint is not None
        ]
        counts = Counter(fingerprints)
        return sum(count - 1 for count in counts.values() if count > 1)

    @property
    def repeated_semantic_emission_count(self) -> int:
        return self.repeated_semantic_fingerprint_count


def _coerce_datetime(value: Any, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        out = value
    else:
        try:
            out = datetime.fromisoformat(str(value))
        except Exception as exc:  # pragma: no cover - defensive only
            raise ValueError(f"invalid_datetime:{field_name}") from exc
    if out.tzinfo is None:
        out = out.replace(tzinfo=IST_TZ)
    return out.astimezone(IST_TZ)


def _bar_start_timestamp(bar: CompletedBarSnapshot | Mapping[str, Any]) -> datetime:
    if isinstance(bar, CompletedBarSnapshot):
        return _coerce_datetime(bar.bar_start_timestamp, field_name="bar_start_timestamp")
    start = None
    if isinstance(bar, Mapping):
        start = bar.get("ts") or bar.get("date") or bar.get("bar_start_timestamp")
    if start is None:
        raise ValueError("missing_bar_timestamp")
    return _coerce_datetime(start, field_name="bar_start_timestamp")


def _bar_end_timestamp(bar: CompletedBarSnapshot | Mapping[str, Any]) -> datetime:
    if isinstance(bar, CompletedBarSnapshot):
        return _coerce_datetime(bar.bar_end_timestamp, field_name="bar_end_timestamp")
    if isinstance(bar, Mapping):
        end = bar.get("bar_end_timestamp")
        if end is not None:
            return _coerce_datetime(end, field_name="bar_end_timestamp")
    return _bar_start_timestamp(bar) + timedelta(minutes=1)


def _prefix_bar_payload(bar: CompletedBarSnapshot | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(bar, CompletedBarSnapshot):
        return {
            "ts": bar.bar_start_timestamp,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
    payload = dict(deepcopy(bar))
    if "ts" not in payload and "bar_start_timestamp" in payload:
        payload["ts"] = payload["bar_start_timestamp"]
    return payload


def build_prefix_history_states(
    *,
    symbol: str,
    segment: str,
    timeframe: str,
    completed_bars: Sequence[CompletedBarSnapshot | Mapping[str, Any]],
    source_component: str = "core.strategy_temporal_harness",
) -> tuple[SessionBarHistoryState, ...]:
    """Build causal prefix histories from a sequence of completed bars."""

    bars = tuple(deepcopy(bar) for bar in completed_bars)
    if not bars:
        return ()

    states: list[SessionBarHistoryState] = []
    for prefix_index in range(1, len(bars) + 1):
        prefix_bars = bars[:prefix_index]
        cutoff_timestamp = _bar_end_timestamp(prefix_bars[-1])
        state = build_session_bar_history_state(
            symbol=symbol,
            bars=[_prefix_bar_payload(bar) for bar in prefix_bars],
            cutoff_timestamp=cutoff_timestamp,
            segment=segment,
            source=source_component,
            timeframe=timeframe,
        )
        states.append(state)
    return tuple(states)


def _candidate_fingerprint(candidate: StrategyCandidate) -> TemporalCandidateFingerprint:
    return TemporalCandidateFingerprint(
        strategy_id=str(candidate.strategy_id),
        direction=str(candidate.direction),
        status=str(candidate.status),
        raw_score=round(float(candidate.raw_score), 6),
        entry_trigger=str(candidate.entry_trigger),
        invalid_if=str(candidate.invalid_if),
        rank_reason=str(candidate.rank_reason),
    )


def _default_trace_observation(
    previous_state: TemporalState,
    state: SessionBarHistoryState,
    generated: tuple[StrategyCandidate, ...],
) -> TemporalTraceObservation:
    candidate = generated[0] if generated else None
    if candidate is None:
        if previous_state == "IDLE":
            next_state = "SETUP_FORMING"
            transition = "IDLE->SETUP_FORMING"
        else:
            next_state = previous_state
            transition = f"{previous_state}->{previous_state}"
        return TemporalTraceObservation(
            setup_state_before=previous_state,
            observed_conditions=("causal_prefix",),
            transition=transition,
            setup_state_after=next_state,
            candidate_emitted=False,
            candidate_semantic_fingerprint=None,
            invalidation_reason=None,
            blocker_reason=None,
        )
    fingerprint = _candidate_fingerprint(candidate)
    return TemporalTraceObservation(
        setup_state_before=previous_state,
        observed_conditions=("candidate_emitted",),
        transition=f"{previous_state}->EMITTED",
        setup_state_after="EMITTED",
        candidate_emitted=True,
        candidate_semantic_fingerprint=fingerprint,
        invalidation_reason=None,
        blocker_reason=None,
    )


def run_temporal_setup_conformance(
    case: TemporalSetupConformanceCase,
) -> TemporalSetupConformanceTrace:
    """Run a strategy against every causal completed-bar prefix."""

    states = build_prefix_history_states(
        symbol=case.symbol,
        segment=case.segment,
        timeframe=case.timeframe,
        completed_bars=case.completed_bars,
        source_component=case.source_component,
    )
    steps: list[TemporalSetupConformanceStep] = []
    previous_state: TemporalState = "IDLE"
    session_id = str(case.session_id or "").strip() or f"{case.symbol}:{states[0].session_date if states else 'empty'}"
    for prefix_index, state in enumerate(states, start=1):
        ctx = case.context_builder(state)
        regime = case.regime_builder(state)
        generated = tuple(case.evaluator(ctx, regime) or ())
        observation = (
            case.oracle(previous_state, state, ctx, regime, generated)
            if case.oracle is not None
            else _default_trace_observation(previous_state, state, generated)
        )
        if observation.candidate_emitted and observation.candidate_semantic_fingerprint is None:
            raise ValueError("candidate_emitted_without_fingerprint")
        if not observation.candidate_emitted and observation.candidate_semantic_fingerprint is not None:
            raise ValueError("fingerprint_without_candidate_emission")
        provenance = state.provenance_payload(
            source_component=case.source_component,
            receipt_timestamp=state.latest_completed_timestamp,
        )
        steps.append(
            TemporalSetupConformanceStep(
                strategy_id=case.strategy_id,
                symbol=case.symbol,
                session_id=session_id,
                prefix_bar_count=state.completed_bar_count,
                checkpoint_timestamp=state.latest_completed_timestamp,
                history_hash=state.history_hash,
                setup_state_before=observation.setup_state_before,
                observed_conditions=observation.observed_conditions,
                transition=observation.transition,
                setup_state_after=observation.setup_state_after,
                candidate_emitted=observation.candidate_emitted,
                candidate_semantic_fingerprint=observation.candidate_semantic_fingerprint,
                invalidation_reason=observation.invalidation_reason,
                blocker_reason=observation.blocker_reason,
                provenance=provenance,
            )
        )
        previous_state = observation.setup_state_after
    return TemporalSetupConformanceTrace(
        case_id=case.case_id,
        strategy_id=case.strategy_id,
        symbol=case.symbol,
        session_id=session_id,
        segment=case.segment,
        timeframe=case.timeframe,
        steps=tuple(steps),
    )


__all__ = [
    "ContextBuilder",
    "Evaluator",
    "RegimeBuilder",
    "TemporalCandidateFingerprint",
    "TemporalSetupConformanceCase",
    "TemporalSetupConformanceStep",
    "TemporalSetupConformanceTrace",
    "TemporalTraceObservation",
    "build_prefix_history_states",
    "run_temporal_setup_conformance",
]
