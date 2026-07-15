from __future__ import annotations

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
class TemporalSetupConformanceStep:
    prefix_index: int
    completed_bar_count: int
    history_hash: str
    latest_completed_timestamp: str | None
    history_provenance: dict[str, Any]
    candidate_fingerprints: tuple[TemporalCandidateFingerprint, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidate_fingerprints"] = [asdict(item) for item in self.candidate_fingerprints]
        return payload


@dataclass(frozen=True)
class TemporalSetupConformanceTrace:
    case_id: str
    strategy_id: str
    symbol: str
    segment: str
    timeframe: str
    steps: tuple[TemporalSetupConformanceStep, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["steps"] = [step.to_dict() for step in self.steps]
        return payload


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
    for prefix_index, state in enumerate(states, start=1):
        ctx = case.context_builder(state)
        regime = case.regime_builder(state)
        generated = tuple(case.evaluator(ctx, regime) or ())
        fingerprints = tuple(
            _candidate_fingerprint(candidate)
            for candidate in generated
            if isinstance(candidate, StrategyCandidate)
        )
        provenance = state.provenance_payload(
            source_component=case.source_component,
            receipt_timestamp=state.latest_completed_timestamp,
        )
        steps.append(
            TemporalSetupConformanceStep(
                prefix_index=prefix_index,
                completed_bar_count=state.completed_bar_count,
                history_hash=state.history_hash,
                latest_completed_timestamp=state.latest_completed_timestamp,
                history_provenance=provenance,
                candidate_fingerprints=fingerprints,
            )
        )
    return TemporalSetupConformanceTrace(
        case_id=case.case_id,
        strategy_id=case.strategy_id,
        symbol=case.symbol,
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
    "build_prefix_history_states",
    "run_temporal_setup_conformance",
]
